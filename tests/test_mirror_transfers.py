"""A transfer rule towards an account added by hand, and the net worth that reads
such an account from its postings.

The case is a Revolut deposit that Enable Banking does not expose: the transfers
to and from it reach the ledger on the personal account only, so the rule writes
the other half on the deposit and the deposit is worth what those halves add up to.
"""
import datetime as dt
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from amonhen.api import create_app
from amonhen.db import connect
from amonhen.ledger import Ledger
from amonhen.merchants import RuleBook, categorize, rule_usage
from amonhen.metrics import latest_balances, monthly_flows, net_worth_series
from amonhen.models import Account, IncomingTransaction

TEXT = "conto deposito senza vincoli"


def make_txn(ledger, account_id, date, amount, description, status="BOOK"):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(date),
        amount=Decimal(amount),
        description=description,
        status=status,
        source="psd2",
        balancing_account_id=ledger.uncategorized(),
        raw={},
    )


def record(ledger, account_id, date, amount, description, status="BOOK") -> int:
    return ledger.record(make_txn(ledger, account_id, date, amount, description, status))[0]


def setup(ledger):
    """Revolut, connected, and a deposit its own app shows but no bank reports."""
    revolut = ledger.ensure_account(Account(name="Revolut", type="real", external_uid="uid-r"))
    deposit = ledger.ensure_account(Account(name="Deposito", type="real"))
    out = record(ledger, revolut, "2026-08-03", "-250.00", "To Conto deposito senza vincoli")
    back = record(ledger, revolut, "2026-08-20", "100.00", "From Conto deposito senza vincoli")
    return revolut, deposit, out, back


def transfer_rule(ledger, **conditions) -> RuleBook:
    book = RuleBook(ledger.conn)
    book.set_rule(TEXT, "Deposito", ledger, action="transfer", **conditions)
    return book


def rows_on(ledger, account_id) -> int:
    return ledger.conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE account_id = ?", (account_id,)
    ).fetchone()[0]


def exists(ledger, transaction_id) -> bool:
    return ledger.conn.execute(
        "SELECT 1 FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone() is not None


def test_the_rule_writes_the_other_half_and_pairs_the_two(ledger):
    revolut, deposit, out, back = setup(ledger)
    book = transfer_rule(ledger)

    for leg, amount in ((out, "250.00"), (back, "-100.00")):
        half = ledger.mirror_of(leg)
        assert half["account"] == "Deposito"
        assert half["amount"] == amount
        assert ledger.transfer_of(leg) == {
            "kind": "pair",
            "target": "Deposito",
            "state": "confirmed",
            "leg_id": half["id"],
            "by_rule": True,
        }
    # Neither spending nor income, and the deposit holds what moved into it.
    assert ledger.spend_between(dt.date(2026, 8, 1), dt.date(2026, 8, 31)) == Decimal(0)
    [august] = monthly_flows(ledger, dt.date(2026, 8, 1), dt.date(2026, 8, 31))
    assert (august.income, august.expenses) == (Decimal(0), Decimal(0))
    assert ledger.balance(deposit, dt.date(2026, 8, 31)) == Decimal("150.00")
    assert ledger.unbalanced() == []
    assert rule_usage(ledger, book.rules()) == {book.rules()[0].id: 2}

    # The rules have not changed: a second pass writes nothing twice.
    assert categorize(ledger, book) == 0
    assert rows_on(ledger, deposit) == 2


def test_a_new_movement_is_mirrored_once_the_bank_settles_it(ledger):
    revolut, deposit, out, back = setup(ledger)
    book = transfer_rule(ledger)
    pending = record(ledger, revolut, "2026-08-25", "-5.00", "To Conto deposito senza vincoli",
                     status="PDNG")

    categorize(ledger, book)
    # A pending row is rewritten when it is booked: no half for it yet.
    assert ledger.mirror_of(pending) is None

    booked = record(ledger, revolut, "2026-08-26", "-5.00", "To Conto deposito senza vincoli")
    categorize(ledger, book)
    assert ledger.mirror_of(booked)["amount"] == "5.00"
    assert ledger.balance(deposit, dt.date(2026, 8, 31)) == Decimal("155.00")


def test_removing_the_rule_takes_back_the_halves_it_wrote(ledger):
    revolut, deposit, out, back = setup(ledger)
    book = transfer_rule(ledger)

    book.remove(book.rules()[0].id, ledger)

    assert ledger.mirror_of(out) is None and ledger.mirror_of(back) is None
    assert ledger.transfer_link(out) is None
    assert ledger.category_of(out) == "Uncategorized"
    assert rows_on(ledger, deposit) == 0
    assert ledger.unbalanced() == []


def test_a_rule_moving_to_a_virtual_destination_takes_the_halves_back_first(ledger):
    revolut, deposit, out, back = setup(ledger)
    book = transfer_rule(ledger)
    [rule] = book.rules()

    book.set_rule(TEXT, "Altrove", ledger, action="transfer", rule_id=rule.id)

    assert rows_on(ledger, deposit) == 0
    assert ledger.transfer_target(out) == "Altrove"
    assert ledger.unbalanced() == []


def test_a_connected_account_or_the_movement_s_own_account_is_refused(ledger):
    revolut, deposit, out, back = setup(ledger)
    book = RuleBook(ledger.conn)
    # A connected account reports its own half, and the matcher pairs it.
    with pytest.raises(ValueError, match="connected"):
        book.set_rule(TEXT, "Revolut", ledger, action="transfer")
    with pytest.raises(ValueError, match="own account"):
        book.set_rule(TEXT, "Deposito", ledger, action="transfer", account_id=deposit)


def test_the_half_goes_with_its_movement_and_is_not_deleted_or_unlinked_alone(ledger):
    revolut, deposit, out, back = setup(ledger)
    transfer_rule(ledger)
    out_half = ledger.mirror_of(out)["id"]
    back_half = ledger.mirror_of(back)["id"]

    with pytest.raises(ValueError, match="change the rule"):
        ledger.delete_transaction(out_half)
    with pytest.raises(ValueError, match="transfer rule wrote"):
        ledger.unlink_transfer(out)

    # A page holding both halves deletes the movement once, and its half with it.
    assert len(ledger.delete_transactions([out, out_half])) == 1
    assert not exists(ledger, out_half)
    assert ledger.delete_transaction(back).unlinked_pair is False
    assert not exists(ledger, back_half)
    assert ledger.unbalanced() == []


def test_a_leg_whose_pair_was_rejected_is_still_the_rule_s_to_move(ledger):
    # The matcher paired the deposit transfer with a co-holder's payment of the
    # same amount and day; rejecting that pair must leave the leg to the rule.
    revolut, deposit, out, back = setup(ledger)
    shared = ledger.ensure_account(Account(name="Cointestato", type="real", external_uid="uid-c"))
    payment = record(ledger, shared, "2026-08-03", "250.00", "Pagamento da parte di Valentina")
    from amonhen.transfers import link_transfers
    link_transfers(ledger)
    assert ledger.transfer_of(out)["leg_id"] == payment
    ledger.unlink_transfer(out)

    transfer_rule(ledger)

    half = ledger.mirror_of(out)["id"]
    assert ledger.transfer_of(out) == {
        "kind": "pair",
        "target": "Deposito",
        "state": "confirmed",
        "leg_id": half,
        "by_rule": True,
    }
    assert ledger.transfer_of(payment) is None
    assert ledger.category_of(payment) == "Uncategorized"
    # Deleting the movement takes its half and leaves the rejected "no" alone.
    ledger.delete_transaction(out)
    assert not exists(ledger, half)
    assert ledger.unbalanced() == []


def test_deleting_the_account_takes_its_rule_and_frees_the_movements(ledger):
    revolut, deposit, out, back = setup(ledger)
    book = transfer_rule(ledger)

    assert ledger.delete_account(deposit) == 2

    # With the rule left behind the next sync would recreate it as a virtual account.
    assert book.rules() == []
    assert ledger.transfer_link(out) is None
    assert ledger.category_of(out) == "Uncategorized"
    assert ledger.unbalanced() == []


def test_the_opening_is_derived_from_today_through_the_halves(ledger):
    revolut, deposit, out, back = setup(ledger)
    transfer_rule(ledger)

    opening, opening_date = ledger.anchor_opening(
        deposit, dt.date(2026, 10, 26), Decimal("1000.00"), "available"
    )

    # The past transfers are kept: the opening is what was there before them.
    assert opening == Decimal("850.00")
    assert opening_date == dt.date(2026, 8, 2)
    assert ledger.balance(deposit, dt.date(2026, 8, 10)) == Decimal("1100.00")
    assert ledger.balance(deposit, dt.date(2026, 10, 26)) == Decimal("1000.00")


def test_the_net_worth_reads_the_postings_of_an_account_marked_computed(ledger):
    revolut, deposit, out, back = setup(ledger)
    transfer_rule(ledger)
    ledger.anchor_opening(deposit, dt.date(2026, 8, 31), Decimal("1000.00"), "available")
    ledger.record_declared_balance(revolut, dt.date(2026, 8, 10), Decimal("500.00"), "eb:ITAV")
    ledger.record_declared_balance(revolut, dt.date(2026, 8, 25), Decimal("600.00"), "eb:ITAV")
    ledger.record_declared_balance(
        deposit, dt.date(2026, 8, 25), Decimal("990.00"), "manual:available"
    )

    def series():
        return {point.date.isoformat(): point.total for point in net_worth_series(ledger)}

    # Unmarked, the deposit counts from the figure somebody typed for it.
    assert series() == {"2026-08-10": Decimal("500.00"), "2026-08-25": Decimal("1590.00")}

    ledger.set_computed_balance(deposit, True)

    # Marked, it is worth its postings at every point — 1100 after the first
    # transfer, 1000 after the second — and the typed figure is a check only.
    assert series() == {"2026-08-10": Decimal("1600.00"), "2026-08-25": Decimal("1600.00")}
    balances = {item.account: item.balance for item in latest_balances(ledger)}
    assert balances == {"Deposito": Decimal("1000.00"), "Revolut": Decimal("600.00")}


def test_only_a_real_account_takes_the_computed_flag(ledger):
    with pytest.raises(ValueError):
        ledger.set_computed_balance(ledger.category("Spesa"), True)


def test_the_api_offers_the_account_and_flips_its_flag(tmp_path):
    config = tmp_path / "accounts.json"
    config.write_text(
        json.dumps(
            {
                "application_id": "app-under-test",
                "pem_path": "private.pem",
                "redirect_url": "http://localhost:8000/callback",
                "account_holder_name": "",
                "accounts": [],
            }
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "ledger.db"
    client = TestClient(create_app(db_path, web_dist=tmp_path / "missing", config_path=config))
    conn = connect(db_path)
    ledger = Ledger(conn)
    revolut, deposit, out, back = setup(ledger)
    conn.close()

    assert client.get("/api/transfers/labels").json()["accounts"] == ["Deposito"]
    saved = client.post(
        "/api/rules", json={"pattern": TEXT, "action": "transfer", "target": "Deposito"}
    )
    assert saved.status_code == 201, saved.text
    leg = client.get("/api/transactions", params={"search": "To Conto"}).json()["items"]
    leg = next(item for item in leg if item["id"] == out)
    assert leg["transfer"]["by_rule"] is True
    assert leg["transfer"]["target"] == "Deposito"

    answer = client.patch(f"/api/accounts/{deposit}", json={"computed_balance": True})
    assert answer.status_code == 200
    assert answer.json()["computed_balance"] is True
    assert answer.json()["balance"] == "150.00"
    client.close()
