"""Desiderata 5.18: the offline bundle and the way back, decided against the ledger."""
import datetime as dt
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from amonhen.api import create_app
from amonhen.db import connect
from amonhen.ledger import Ledger
from amonhen.models import Account, IncomingTransaction
from amonhen.services import offline
from amonhen.transfers import link_transfers

MINIMAL_CONFIG = Path(__file__).resolve().parent / "fixtures" / "config" / "minimal.json"


def movement(ledger, account_id, date, amount, description, status="BOOK"):
    transaction_id, _ = ledger.record(
        IncomingTransaction(
            account_id=account_id,
            date=dt.date.fromisoformat(date),
            amount=Decimal(amount),
            description=description,
            status=status,
            source="psd2",
            balancing_account_id=ledger.uncategorized(),
            raw={},
        )
    )
    return transaction_id


class Phone:
    """The ledger a server holds, the client that talks to it, and the ids of what the
    tests act on."""

    def __init__(self, tmp_path):
        self.db_path = tmp_path / "ledger.db"
        self.client = TestClient(
            create_app(self.db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG)
        )
        conn = connect(self.db_path)
        ledger = Ledger(conn)
        revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
        fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
        self.groceries = ledger.category("Spesa")
        ledger.category("Svago")
        ledger.tag("viaggio")
        self.coffee = movement(ledger, revolut, "2026-08-03", "-3.00", "Bar Centrale")
        self.shop = movement(ledger, revolut, "2026-08-07", "-42.50", "Supermercato")
        self.old = movement(ledger, revolut, "2026-06-01", "-10.00", "Vecchio")
        self.out = movement(ledger, revolut, "2026-08-20", "-200.00", "Bonifico")
        self.into = movement(ledger, fineco, "2026-08-21", "200.00", "Bonifico")
        self.other_out = movement(ledger, revolut, "2026-08-22", "-80.00", "Giro")
        self.other_in = movement(ledger, fineco, "2026-08-22", "80.00", "Giro")
        self.same_account_in = movement(ledger, revolut, "2026-08-22", "80.00", "Altro")
        conn.close()

    def server(self, sql: str, *params) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(sql, params)
        conn.commit()
        conn.close()

    def bundle(self, first="2026-08-01", last="2026-08-31") -> dict:
        reply = self.client.get("/api/offline/bundle", params={"from": first, "to": last})
        assert reply.status_code == 200, reply.text
        return reply.json()

    def send(self, route, operations, resolutions=(), fmt=offline.FORMAT):
        body = {"format": fmt, "operations": list(operations), "resolutions": list(resolutions)}
        return self.client.post(f"/api/offline/{route}", json=body)

    def outcomes(self, route, operations, resolutions=()):
        reply = self.send(route, operations, resolutions)
        assert reply.status_code == 200, reply.text
        return {o["id"]: o for o in reply.json()["outcomes"]}

    def transaction(self, transaction_id) -> dict:
        return self.client.get(f"/api/transactions/{transaction_id}").json()


@pytest.fixture
def phone(tmp_path):
    handle = Phone(tmp_path)
    yield handle
    handle.client.close()


def category(op_id, transaction_id, name, base):
    return {
        "id": op_id, "kind": "category", "transaction_id": transaction_id,
        "value": {"category": name}, "base": {"splits": base},
    }


def uncategorized(amount):
    return [{"category": "Uncategorized", "amount": amount}]


# -- the bundle ------------------------------------------------------------------------------


def test_the_bundle_holds_the_period_and_the_whole_queue(phone):
    bundle = phone.bundle()

    assert bundle["format"] == offline.FORMAT
    assert (bundle["from"], bundle["to"]) == ("2026-08-01", "2026-08-31")
    ids = {t["id"] for t in bundle["transactions"]}
    assert {phone.coffee, phone.shop, phone.out} <= ids
    # The queue comes whole, whatever its date: an old movement still waits for a decision.
    assert phone.old in ids
    assert phone.old in bundle["review"]["queue"]
    assert {c["name"] for c in bundle["categories"]} >= {"Spesa", "Svago"}
    assert [t["name"] for t in bundle["tags"]] == ["viaggio"]
    assert {a["name"] for a in bundle["accounts"]} == {"Revolut", "Fineco"}


def test_the_bundle_carries_what_the_phone_cannot_compute(phone):
    bundle = phone.bundle()

    candidates = bundle["candidates"]
    # The server's own search: an equal and opposite amount on another account.
    assert phone.into in candidates[str(phone.out)]
    assert phone.out in candidates[str(phone.into)]
    # Never a leg on the same account, which the same amount on Revolut would be.
    assert candidates[str(phone.other_out)] == [phone.other_in]


def test_the_bundle_holds_a_candidate_outside_the_period(phone):
    # The other half of a transfer may sit days away, across the edge of the period.
    bundle = phone.bundle("2026-08-22", "2026-08-31")

    ids = {t["id"] for t in bundle["transactions"]}
    assert phone.into in ids  # 21 August: outside, but the candidate of the movement on the 20th
    assert phone.out in ids


def test_a_period_that_ends_before_it_starts_is_refused(phone):
    reply = phone.client.get("/api/offline/bundle", params={"from": "2026-09-01", "to": "2026-08-01"})
    assert reply.status_code == 422


# -- preview and commit ------------------------------------------------------------------------


def test_a_preview_says_what_a_commit_would_do_and_writes_nothing(phone):
    op = category("a", phone.coffee, "Spesa", uncategorized("3.00"))

    result = phone.outcomes("preview", [op])

    assert result["a"]["state"] == offline.APPLICABLE
    assert result["a"]["applied"] is False
    assert phone.transaction(phone.coffee)["category"] == "Uncategorized"


def test_a_commit_writes_and_sending_it_again_changes_nothing(phone):
    op = category("a", phone.coffee, "Spesa", uncategorized("3.00"))

    first = phone.outcomes("commit", [op])
    second = phone.outcomes("commit", [op])

    assert first["a"]["applied"] is True
    assert phone.transaction(phone.coffee)["category"] == "Spesa"
    assert second["a"]["state"] == offline.ALREADY
    assert second["a"]["applied"] is False
    assert phone.transaction(phone.coffee)["category"] == "Spesa"


def test_a_split_is_one_operation(phone):
    op = {
        "id": "s", "kind": "splits", "transaction_id": phone.shop,
        "value": {"splits": [
            {"category": "Spesa", "amount": "30.00"}, {"category": "Svago", "amount": "12.50"},
        ]},
        "base": {"splits": uncategorized("42.50")},
    }

    assert phone.outcomes("commit", [op])["s"]["applied"] is True
    assert sorted((s["category"], s["amount"]) for s in phone.transaction(phone.shop)["splits"]) == [
        ("Spesa", "30.00"), ("Svago", "12.50"),
    ]


def test_a_category_changed_on_the_server_is_a_conflict_that_waits_for_an_answer(phone):
    op = category("a", phone.coffee, "Spesa", uncategorized("3.00"))
    phone.client.post(f"/api/transactions/{phone.coffee}/category", json={"category": "Svago"})

    shown = phone.outcomes("preview", [op])["a"]

    assert shown["state"] == offline.CONFLICT
    assert shown["current"] == [{"category": "Svago", "amount": "3.00"}]
    # No answer, no write.
    assert phone.outcomes("commit", [op])["a"]["applied"] is False
    assert phone.transaction(phone.coffee)["category"] == "Svago"


def test_a_conflict_is_written_only_for_the_value_the_person_saw(phone):
    op = category("a", phone.coffee, "Spesa", uncategorized("3.00"))
    phone.client.post(f"/api/transactions/{phone.coffee}/category", json={"category": "Svago"})
    seen = phone.outcomes("preview", [op])["a"]["token"]

    # The server changes again after the preview: the answer was to another value.
    phone.client.post(f"/api/transactions/{phone.coffee}/category", json={"category": "Spesa"})
    phone.client.put(f"/api/transactions/{phone.coffee}/splits", json={"splits": [
        {"category": "Svago", "amount": "1.00"}, {"category": "Spesa", "amount": "2.00"},
    ]})
    stale = phone.outcomes("commit", [op], [{"id": "a", "choice": "mine", "seen": seen}])["a"]
    assert stale["state"] == offline.CONFLICT and stale["applied"] is False

    fresh_token = phone.outcomes("preview", [op])["a"]["token"]
    answered = phone.outcomes("commit", [op], [{"id": "a", "choice": "mine", "seen": fresh_token}])
    assert answered["a"]["applied"] is True
    assert phone.transaction(phone.coffee)["category"] == "Spesa"


def test_keeping_the_servers_value_drops_the_operation_and_writes_nothing(phone):
    op = category("a", phone.coffee, "Spesa", uncategorized("3.00"))
    phone.client.post(f"/api/transactions/{phone.coffee}/category", json={"category": "Svago"})

    outcome = phone.outcomes("commit", [op], [{"id": "a", "choice": "server"}])["a"]

    assert outcome["dropped"] is True and outcome["applied"] is False
    assert phone.transaction(phone.coffee)["category"] == "Svago"


def test_a_category_cannot_land_on_a_movement_that_became_a_transfer_leg(phone):
    op = category("a", phone.out, "Spesa", uncategorized("200.00"))
    phone.client.post("/api/transfers/pair", json={"leg_a": phone.out, "leg_b": phone.into})

    assert phone.outcomes("preview", [op])["a"]["state"] == offline.INVALID


def test_a_category_that_no_longer_exists_is_invalid_and_is_not_created(phone):
    op = category("a", phone.coffee, "Inventata", uncategorized("3.00"))

    assert phone.outcomes("commit", [op])["a"]["state"] == offline.INVALID
    names = {c["name"] for c in phone.client.get("/api/categories").json()}
    assert "Inventata" not in names


def test_a_note_follows_the_same_rule(phone):
    op = {"id": "n", "kind": "note", "transaction_id": phone.coffee,
          "value": {"notes": "con Marco"}, "base": {"notes": None}}

    assert phone.outcomes("commit", [op])["n"]["applied"] is True
    assert phone.transaction(phone.coffee)["notes"] == "con Marco"

    phone.client.put(f"/api/transactions/{phone.shop}/notes", json={"notes": "già scritta"})
    clash = {"id": "m", "kind": "note", "transaction_id": phone.shop,
             "value": {"notes": "la mia"}, "base": {"notes": None}}
    shown = phone.outcomes("preview", [clash])["m"]
    assert shown["state"] == offline.CONFLICT
    assert shown["current"] == "già scritta"


def test_tags_merge_instead_of_conflicting(phone):
    add = {"id": "t", "kind": "tag_add", "transaction_id": phone.coffee,
           "value": {"tag": "viaggio"}, "base": {}}
    phone.client.put(f"/api/transactions/{phone.coffee}/tags", json={"tags": ["viaggio"]})

    assert phone.outcomes("preview", [add])["t"]["state"] == offline.ALREADY

    drop = {"id": "d", "kind": "tag_remove", "transaction_id": phone.coffee,
            "value": {"tag": "viaggio"}, "base": {}}
    assert phone.outcomes("commit", [drop])["d"]["applied"] is True
    assert phone.transaction(phone.coffee)["tags"] == []


def test_a_tag_that_does_not_exist_is_not_created(phone):
    add = {"id": "t", "kind": "tag_add", "transaction_id": phone.coffee,
           "value": {"tag": "nuovo"}, "base": {}}

    assert phone.outcomes("commit", [add])["t"]["state"] == offline.INVALID
    assert [t["name"] for t in phone.client.get("/api/tags").json()] == ["viaggio"]


def delete(transaction_id, date, amount, description, status="BOOK"):
    return {"id": f"x{transaction_id}", "kind": "delete", "transaction_id": transaction_id,
            "value": {}, "base": {"date": date, "amount": amount,
                                  "description": description, "status": status}}


def test_a_deletion_leaves_its_tombstone(phone):
    op = delete(phone.coffee, "2026-08-03", "-3.00", "Bar Centrale")

    assert phone.outcomes("commit", [op])[op["id"]]["applied"] is True

    assert phone.client.get(f"/api/transactions/{phone.coffee}").status_code == 404
    assert [d["description"] for d in phone.client.get("/api/deleted").json()] == ["Bar Centrale"]
    # Sending it again: the movement is gone, and nothing else moves.
    assert phone.outcomes("commit", [op])[op["id"]]["state"] == offline.GONE


def test_a_movement_rewritten_by_the_bank_is_a_conflict_for_a_deletion(phone):
    # A pending movement promoted to booked comes back with other values.
    op = delete(phone.coffee, "2026-08-03", "-3.00", "Bar Centrale", status="PDNG")

    shown = phone.outcomes("preview", [op])[op["id"]]

    assert shown["state"] == offline.CONFLICT
    assert shown["current"]["status"] == "BOOK"
    assert phone.client.get(f"/api/transactions/{phone.coffee}").status_code == 200


def test_pairing_two_legs_and_pairing_them_again(phone):
    op = {"id": "p", "kind": "pair", "transaction_id": phone.out,
          "value": {"other_id": phone.into}, "base": {}}

    assert phone.outcomes("commit", [op])["p"]["applied"] is True
    assert phone.transaction(phone.out)["transfer"]["leg_id"] == phone.into
    assert phone.outcomes("commit", [op])["p"]["state"] == offline.ALREADY


def test_a_pairing_the_ledger_refuses_is_invalid_and_leaves_no_trace(phone):
    op = {"id": "p", "kind": "pair", "transaction_id": phone.other_out,
          "value": {"other_id": phone.same_account_in}, "base": {}}
    note = {"id": "n", "kind": "note", "transaction_id": phone.coffee,
            "value": {"notes": "ok"}, "base": {"notes": None}}

    result = phone.outcomes("commit", [op, note])

    assert result["p"]["state"] == offline.INVALID
    assert phone.transaction(phone.other_out)["transfer"] is None
    # The refusal of one operation does not take the others down.
    assert result["n"]["applied"] is True


def proposed_pair(phone):
    conn = connect(phone.db_path)
    link_transfers(Ledger(conn))
    conn.close()
    reviewed = phone.client.get("/api/review").json()["transfers"]
    return reviewed[0]["leg_a"]["id"], reviewed[0]["leg_b"]["id"]


def test_confirming_a_proposed_pair_and_a_decision_taken_elsewhere(phone):
    leg_a, leg_b = proposed_pair(phone)
    op = {"id": "r", "kind": "review", "transaction_id": leg_a,
          "value": {"other_id": leg_b, "decision": "confirm"}, "base": {"state": 0}}

    assert phone.outcomes("preview", [op])["r"]["state"] == offline.APPLICABLE

    phone.client.post(f"/api/transfers/{leg_a}/{leg_b}/review", json={"decision": "reject"})
    shown = phone.outcomes("preview", [op])["r"]
    assert shown["state"] == offline.CONFLICT
    assert shown["current"] == {"state": -1}


def test_a_commit_is_one_transaction_in_order(phone):
    # Two operations on one movement in one queue: the second sees the first.
    first = category("a", phone.coffee, "Spesa", uncategorized("3.00"))
    second = category("b", phone.coffee, "Svago", uncategorized("3.00"))

    result = phone.outcomes("commit", [first, second])

    assert result["a"]["applied"] is True
    assert result["b"]["state"] == offline.CONFLICT
    assert phone.transaction(phone.coffee)["category"] == "Spesa"


def test_a_preview_never_commits_even_what_it_deletes(phone):
    ops = [delete(phone.coffee, "2026-08-03", "-3.00", "Bar Centrale")]

    assert phone.outcomes("preview", ops)[ops[0]["id"]]["state"] == offline.APPLICABLE

    assert phone.client.get(f"/api/transactions/{phone.coffee}").status_code == 200
    assert phone.client.get("/api/deleted").json() == []


# -- what the server refuses whole ---------------------------------------------------------------


def test_a_format_the_server_does_not_know_refuses_the_queue(phone):
    reply = phone.send("preview", [], fmt=offline.FORMAT + 1)

    assert reply.status_code == 409
    assert str(offline.FORMAT) in reply.json()["detail"]


def test_a_malformed_operation_is_the_phones_bug_and_refuses_the_request(phone):
    broken = {"id": "a", "kind": "category", "transaction_id": phone.coffee, "value": {}, "base": {}}
    unknown = {"id": "b", "kind": "teleport", "transaction_id": phone.coffee}

    assert phone.send("preview", [broken]).status_code == 422
    assert phone.send("commit", [unknown]).status_code == 422
