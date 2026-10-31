"""An investment account added by hand: its value, and the return it books."""
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from amonhen.api import create_app
from amonhen.db import open_ledger_db
from amonhen.ledger import RETURNS_ACCOUNT, Ledger
from amonhen.metrics import compute_metrics, monthly_flows
from amonhen.models import Account, IncomingTransaction
from amonhen.transfers import link_transfers

MINIMAL_CONFIG = Path(__file__).resolve().parent / "fixtures" / "config" / "minimal.json"


def make_txn(ledger, account_id, date, amount, description):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(date),
        amount=Decimal(amount),
        description=description,
        status="BOOK",
        source="import",
        balancing_account_id=ledger.uncategorized(),
        raw={},
    )


@pytest.fixture
def broker(tmp_path):
    conn = open_ledger_db(tmp_path / "ledger.db")
    ledger = Ledger(conn)
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    broker = ledger.ensure_account(Account(name="Broker", type="real"))
    ledger.set_investment(broker, True)
    # One transfer to the broker, with its two halves, so the broker has a history.
    ledger.record(make_txn(ledger, bank, "2026-01-10", "-1000.00", "Bonifico al broker"))
    ledger.record(make_txn(ledger, broker, "2026-01-10", "1000.00", "Bonifico dalla banca"))
    link_transfers(ledger)
    ledger.set_transfer_review(*_pair(ledger), "confirm")
    ledger.anchor_opening(broker, dt.date(2026, 1, 1), Decimal("5000.00"), "available")
    yield ledger, broker
    conn.close()


def _pair(ledger):
    row = ledger.conn.execute("SELECT leg_a, leg_b FROM transfer_links").fetchone()
    return row["leg_a"], row["leg_b"]


def test_a_valuation_books_the_return_beside_the_movements(broker):
    ledger, account = broker

    difference, transaction_id = ledger.record_valuation(account, dt.date(2026, 3, 31), Decimal("6400.00"))

    # 5000 opening + 1000 transferred: the market added the other 400.
    assert difference == Decimal("400.00")
    assert ledger.balance(account, dt.date(2026, 3, 31)) == Decimal("6400.00")
    returns = ledger.find_account(name=RETURNS_ACCOUNT)
    assert returns["type"] == "virtual"
    assert ledger.transfer_of(transaction_id)["target"] == RETURNS_ACCOUNT
    # The value is also the declaration the check reads, and the check agrees.
    [check] = ledger.declared_checks(account)
    assert (check.declared, check.difference) == (Decimal("6400.00"), Decimal("0.00"))
    ledger.validate()


def test_a_second_valuation_on_the_same_day_replaces_the_first(broker):
    ledger, account = broker
    ledger.record_valuation(account, dt.date(2026, 3, 31), Decimal("6400.00"))

    difference, _ = ledger.record_valuation(account, dt.date(2026, 3, 31), Decimal("6350.00"))

    assert difference == Decimal("350.00")
    assert ledger.balance(account, dt.date(2026, 3, 31)) == Decimal("6350.00")


def test_a_return_is_neither_income_nor_savings_nor_a_transfer_candidate(broker):
    ledger, account = broker
    other = ledger.ensure_account(Account(name="Altra banca", type="real"))
    savings_before = compute_metrics(ledger, dt.date(2026, 4, 30)).savings_flow

    ledger.record_valuation(account, dt.date(2026, 3, 31), Decimal("6400.00"))
    # A movement of the opposite amount elsewhere must not be paired with it.
    ledger.record(make_txn(ledger, other, "2026-03-31", "-400.00", "Spesa qualunque"))
    link_transfers(ledger)

    assert compute_metrics(ledger, dt.date(2026, 4, 30)).savings_flow == savings_before
    march = next(m for m in monthly_flows(ledger, dt.date(2026, 1, 1), dt.date(2026, 4, 30)) if m.month == "2026-03")
    assert march.income == Decimal("0.00")
    assert ledger.conn.execute("SELECT COUNT(*) FROM transfer_links").fetchone()[0] == 1


def test_only_an_investment_account_added_by_hand_takes_a_valuation(broker):
    ledger, _ = broker
    bank = ledger.find_account(name="Banca")["id"]

    with pytest.raises(ValueError, match="not an investment account"):
        ledger.record_valuation(bank, dt.date(2026, 3, 31), Decimal("10.00"))


def test_the_app_records_a_valuation_and_answers_with_the_return(tmp_path):
    db_path = tmp_path / "ledger.db"
    conn = open_ledger_db(db_path)
    ledger = Ledger(conn)
    account = ledger.ensure_account(Account(name="Broker", type="real"))
    ledger.set_investment(account, True)
    ledger.anchor_opening(account, dt.date(2026, 1, 1), Decimal("5500.00"), "available")
    conn.close()
    client = TestClient(create_app(db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG))

    answer = client.post(f"/api/accounts/{account}/valuation", json={"date": "2026-03-31", "value": "4950.00"})

    assert answer.status_code == 200
    assert answer.json()["difference"] == "-550.00"
    assert answer.json()["account"]["verification"]["state"] == "verified"
    rows = client.get("/api/virtual-accounts").json()
    assert [(row["name"], row["balance"]) for row in rows] == [(RETURNS_ACCOUNT, "550.00")]
    assert client.post(f"/api/accounts/{account}/valuation", json={"date": "2026-03-31", "value": ""}).status_code == 422
    client.close()
