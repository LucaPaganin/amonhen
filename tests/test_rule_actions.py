"""Rules that delete or record a transfer, rules narrowed by conditions, and the
batch writes beside them: deleting an account, a page of movements at once."""
import datetime as dt
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from amonhen.api import create_app
from amonhen.db import connect
from amonhen.ledger import Ledger
from amonhen.merchants import RuleBook, categorize, rule_usage
from amonhen.models import Account, IncomingTransaction
from amonhen.transfers import link_transfers


def make_txn(ledger, account_id, date, amount, description):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(date),
        amount=Decimal(amount),
        description=description,
        status="BOOK",
        source="psd2",
        balancing_account_id=ledger.uncategorized(),
        raw={},
    )


def record(ledger, account_id, date, amount, description) -> int:
    return ledger.record(make_txn(ledger, account_id, date, amount, description))[0]


def remaining(ledger) -> set[str]:
    return {row["description"] for row in ledger.conn.execute("SELECT description FROM transactions")}


# -- conditions ---------------------------------------------------------------


def test_a_rule_narrowed_to_an_account_leaves_the_other_accounts_alone(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    on_revolut = record(ledger, revolut, "2026-08-03", "-10.00", "AMAZON EU")
    on_fineco = record(ledger, fineco, "2026-08-03", "-10.00", "AMAZON EU")

    RuleBook(ledger.conn).set_rule("amazon", "Casa", ledger, account_id=revolut)

    assert ledger.category_of(on_revolut) == "Casa"
    assert ledger.category_of(on_fineco) == "Uncategorized"


def test_an_amount_range_reads_the_size_and_a_narrower_rule_wins_the_tie(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    small = record(ledger, revolut, "2026-08-03", "-4.99", "APPLE.COM/BILL")
    large = record(ledger, revolut, "2026-08-04", "-1299.00", "APPLE.COM/BILL")
    book = RuleBook(ledger.conn)

    book.set_rule("apple.com", "Elettronica", ledger)
    book.set_rule("apple.com", "Abbonamenti", ledger, amount_max=Decimal("20"))

    # Same text: the rule with a condition is the narrower statement.
    assert ledger.category_of(small) == "Abbonamenti"
    assert ledger.category_of(large) == "Elettronica"
    assert len(book.rules()) == 2


def test_the_same_text_and_conditions_are_one_rule(ledger):
    book = RuleBook(ledger.conn)
    book.set_rule("ekom", "Spesa", ledger, amount_min=Decimal("5"))
    book.set_rule("ekom", "Casa", ledger, amount_min=Decimal("5"))

    [rule] = book.rules()
    assert rule.target == "Casa"


def test_a_minimum_above_the_maximum_is_refused(ledger):
    with pytest.raises(ValueError):
        RuleBook(ledger.conn).set_rule(
            "ekom", "Spesa", ledger, amount_min=Decimal("10"), amount_max=Decimal("5")
        )


# -- deleting -----------------------------------------------------------------


def test_a_deleting_rule_empties_what_it_matches_now_and_at_the_next_sync(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    record(ledger, revolut, "2026-08-03", "-1.00", "Arrotondamento salvadanaio")
    record(ledger, revolut, "2026-08-04", "-12.00", "EKOM")
    book = RuleBook(ledger.conn)

    book.set_rule("salvadanaio", None, ledger, action="delete")

    assert remaining(ledger) == {"EKOM"}
    [tombstone] = ledger.deleted_transactions()
    assert tombstone["description"] == "Arrotondamento salvadanaio"

    # A new one arrives with the next sync, and the rules pass takes it too.
    record(ledger, revolut, "2026-08-05", "-0.40", "Arrotondamento salvadanaio")
    assert categorize(ledger, book) == 1
    assert remaining(ledger) == {"EKOM"}
    assert rule_usage(ledger, book.rules()) == {book.rules()[0].id: 2}


def test_a_deleted_movement_does_not_come_back_with_the_same_sync(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    record(ledger, revolut, "2026-08-03", "-1.00", "Arrotondamento salvadanaio")
    RuleBook(ledger.conn).set_rule("salvadanaio", None, ledger, action="delete")

    # The bank sends the same movement again: the tombstone suppresses it.
    _, action = ledger.record(
        make_txn(ledger, revolut, "2026-08-03", "-1.00", "Arrotondamento salvadanaio")
    )

    assert action != "inserted"
    assert remaining(ledger) == set()


# -- transfers ----------------------------------------------------------------


def test_a_transfer_rule_records_a_leg_and_lets_it_go_when_removed(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    leg = record(ledger, revolut, "2026-08-03", "-250.00", "To Conto deposito")
    book = RuleBook(ledger.conn)
    book.set_rule("conto deposito", "Deposito", ledger, action="transfer")

    assert ledger.transfer_target(leg) == "Deposito"
    assert ledger.spend_between(dt.date(2026, 8, 1), dt.date(2026, 8, 31)) == Decimal(0)

    book.remove(book.rules()[0].id, ledger)

    assert ledger.transfer_target(leg) is None
    assert ledger.category_of(leg) == "Uncategorized"


def test_a_transfer_rule_wins_over_a_category_rule_of_the_same_text(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    leg = record(ledger, revolut, "2026-08-03", "-250.00", "To Conto deposito")
    book = RuleBook(ledger.conn)
    book.set_rule("conto deposito", "Risparmio", ledger)
    book.set_rule("deposito", "Deposito", ledger, action="transfer")

    assert ledger.transfer_target(leg) == "Deposito"


def test_a_transfer_rule_cannot_name_a_category(ledger):
    ledger.category("Spesa")
    with pytest.raises(ValueError):
        RuleBook(ledger.conn).set_rule("ekom", "Spesa", ledger, action="transfer")


# -- deleting an account ------------------------------------------------------


def test_deleting_an_account_takes_its_movements_and_frees_the_other_leg(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    record(ledger, revolut, "2026-08-03", "-12.00", "EKOM")
    record(ledger, revolut, "2026-08-15", "-840.00", "Bonifico")
    other_leg = record(ledger, fineco, "2026-08-15", "840.00", "Bonifico")
    link_transfers(ledger)
    assert ledger.transfer_link(other_leg) is not None

    assert ledger.delete_account(revolut) == 2

    assert ledger.find_account(name="Revolut") is None
    assert ledger.transfer_link(other_leg) is None
    assert ledger.category_of(other_leg) == "Uncategorized"
    assert ledger.unbalanced() == []


def test_only_a_real_account_is_deleted_this_way(ledger):
    with pytest.raises(ValueError):
        ledger.delete_account(ledger.category("Spesa"))


# -- through the API ----------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    config = tmp_path / "accounts.json"
    config.write_text(
        json.dumps(
            {
                "application_id": "app-under-test",
                "pem_path": "private.pem",
                "redirect_url": "http://localhost:8000/callback",
                "account_holder_name": "",
                "accounts": [
                    {
                        "session_id": "s-1",
                        "account_uid": "uid-fineco",
                        "bank_name": "FinecoBank",
                        "notes": "Fineco",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "ledger.db"
    app = TestClient(create_app(db_path, web_dist=tmp_path / "missing", config_path=config))
    conn = connect(db_path)
    ledger = Ledger(conn)
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    record(ledger, revolut, "2026-08-03", "-1.00", "Arrotondamento salvadanaio")
    record(ledger, revolut, "2026-08-04", "-0.50", "Arrotondamento salvadanaio")
    record(ledger, revolut, "2026-08-05", "-42.50", "EKOM | Cart")
    record(ledger, fineco, "2026-08-06", "-9.00", "Arrotondamento salvadanaio")
    conn.close()
    yield app, config
    app.close()


def test_the_preview_says_what_a_rule_would_take_and_writes_nothing(client):
    app, _ = client

    found = app.post(
        "/api/rules/preview", json={"pattern": "salvadanaio", "action": "delete"}
    ).json()

    assert found["count"] == 3
    assert {item["account"] for item in found["items"]} == {"Revolut", "Fineco"}
    assert app.get("/api/rules").json() == []
    assert app.get("/api/transactions").json()["total"] == 4


def test_a_deleting_rule_through_the_api_and_the_restore_it_refuses(client):
    app, _ = client
    revolut = next(a for a in app.get("/api/accounts").json() if a["name"] == "Revolut")

    saved = app.post(
        "/api/rules",
        json={"pattern": "salvadanaio", "action": "delete", "account_id": revolut["id"]},
    )

    assert saved.status_code == 201
    assert saved.json()["action"] == "delete"
    assert saved.json()["account"] == "Revolut"
    assert saved.json()["count"] == 2
    assert app.get("/api/transactions").json()["total"] == 2
    deleted = app.get("/api/deleted").json()
    refused = app.post(f"/api/deleted/{deleted[0]['id']}/restore")
    assert refused.status_code == 409
    assert "salvadanaio" in refused.json()["detail"]

    removed = app.post("/api/rules/remove", json={"id": saved.json()["id"]})
    assert removed.json()["held"] == 2
    assert app.post(f"/api/deleted/{deleted[0]['id']}/restore").status_code == 200


def test_a_page_of_movements_is_deleted_or_categorized_at_once(client):
    app, _ = client
    ids = [item["id"] for item in app.get("/api/transactions").json()["items"]]

    categorized = app.post("/api/transactions/category", json={"ids": ids[:2], "category": "Varie"})
    assert categorized.json() == {"categorized": 2, "skipped": 0}

    deleted = app.post("/api/transactions/delete", json={"ids": ids[:3]})
    assert deleted.json()["deleted"] == 3
    assert app.get("/api/transactions").json()["total"] == 1

    stale = app.post("/api/transactions/delete", json={"ids": [ids[3], 99999]})
    assert stale.status_code == 404
    assert app.get("/api/transactions").json()["total"] == 1


def test_deleting_an_account_through_the_api_also_stops_its_sync(client):
    app, config = client
    fineco = next(a for a in app.get("/api/accounts").json() if a["name"] == "Fineco")

    answer = app.delete(f"/api/accounts/{fineco['id']}")

    assert answer.json() == {"name": "Fineco", "movements": 1, "disconnected": True}
    assert {a["name"] for a in app.get("/api/accounts").json()} == {"Revolut"}
    assert json.loads(config.read_text(encoding="utf-8"))["accounts"] == []
    assert app.delete(f"/api/accounts/{fineco['id']}").status_code == 404
