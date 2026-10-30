"""An investment account added by hand: its value, the return it books, and
Scalable's statements that say both.

The figures and the account numbers below are made up: the statements are
written as the PDF library extracts them, without anybody's data.
"""
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from amonhen import api as api_module
from amonhen.adapters.scalable_pdf import CashStatement, HoldingsStatement, Reading, parse_text
from amonhen.api import create_app
from amonhen.db import open_ledger_db
from amonhen.ledger import RETURNS_ACCOUNT, Ledger
from amonhen.metrics import compute_metrics, monthly_flows
from amonhen.models import Account, IncomingTransaction
from amonhen.scalable_import import plan
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


CASH_MARCH = """Estratto conto Periodo 01.03.2026 - 31.03.2026
Conto di regolamento DE00111111111111110001 (DEUTDEFFXXX)
Saldo a 01.03.2026 1,000.00 EUR
Saldo a 31.03.2026 1,950.00 EUR
Registrazione Data valuta Descrizione Importo
02.03.2026 04.03.2026 Acquisto di uno strumento finanziario
1.00 pz. Un ETF qualunque (IE0000000001)
-50.00 EUR
10.03.2026 10.03.2026 Bonifico +1,000.00 EUR
20.03.2026 20.03.2026 Bonifico +2,500.00 EUR
21.03.2026 21.03.2026 Prelievo dal saldo di cassa -2,500.00 EUR
"""

CASH_MARCH_OTHER = """Estratto conto Periodo 01.03.2026 - 31.03.2026
Conto di regolamento DE00222222222222220002 (DEUTDEFFXXX)
Saldo a 01.03.2026 0.00 EUR
Saldo a 31.03.2026 2,500.00 EUR
Registrazione Data valuta Descrizione Importo
21.03.2026 21.03.2026 Bonifico +2,500.00 EUR
"""

HOLDINGS_MARCH = """Estratto conto titoli al 31.03.2026 • Conto deposito titoli 0000000000
Panoramica
Exchange Traded Fund (ETF) 100,00 % 3,000.00 EUR
T otale 3,000.00 EUR
"""


def test_a_cash_statement_reads_its_bookings_and_both_balances():
    statement = parse_text(CASH_MARCH)

    assert isinstance(statement, CashStatement)
    assert (statement.account, statement.start, statement.end) == ("0001", "2026-03-01", "2026-03-31")
    assert (statement.opening, statement.closing) == (Decimal("1000.00"), Decimal("1950.00"))
    assert [(b.description, b.amount) for b in statement.bookings][0] == (
        "Acquisto di uno strumento finanziario", Decimal("-50.00")
    )
    assert statement.bookings[0].detail == "1.00 pz. Un ETF qualunque (IE0000000001)"
    assert parse_text(HOLDINGS_MARCH) == HoldingsStatement("2026-03-31", Decimal("3000.00"))


def test_securities_without_cash_statements_value_nothing(broker):
    ledger, account = broker

    planned = plan(ledger, account, Reading([], [parse_text(HOLDINGS_MARCH)], []))

    assert planned.valuations == []
    assert planned.unvalued and planned.unvalued[0].startswith("2026-03-31")


def test_the_statements_value_the_broker_and_name_the_transfers_the_ledger_lacks(broker):
    ledger, account = broker
    reading = Reading(
        cash=[parse_text(CASH_MARCH), parse_text(CASH_MARCH_OTHER)],
        holdings=[parse_text(HOLDINGS_MARCH)],
        unreadable=[],
    )

    planned = plan(ledger, account, reading)

    # Securities 3000 plus the cash of both accounts on the quarter's last day.
    [valuation] = planned.valuations
    assert valuation.value == Decimal("7450.00")
    assert valuation.balance == Decimal("6000.00")
    assert valuation.difference == Decimal("1450.00")
    # 2500 moved between the broker's own accounts never left it; the 2500 that
    # arrived on the first one and the 1000 of the 10th have no movement here.
    assert [(b.account, b.amount) for b in planned.internal] == [("0002", Decimal("2500.00")), ("0001", Decimal("-2500.00"))]
    assert sorted(b.amount for b in planned.unmatched) == [Decimal("1000.00"), Decimal("2500.00")]


def test_the_app_previews_then_writes_the_valuations(tmp_path, monkeypatch):
    db_path = tmp_path / "ledger.db"
    conn = open_ledger_db(db_path)
    ledger = Ledger(conn)
    account = ledger.ensure_account(Account(name="Broker", type="real"))
    ledger.set_investment(account, True)
    ledger.anchor_opening(account, dt.date(2026, 1, 1), Decimal("5500.00"), "available")
    conn.close()
    reading = Reading([parse_text(CASH_MARCH)], [parse_text(HOLDINGS_MARCH)], [])
    monkeypatch.setattr(api_module, "read_statements", lambda files: reading)
    client = TestClient(create_app(db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG))
    body = {"account": "Broker", "files": [{"name": "marzo.pdf", "content": "JVBERg=="}]}

    preview = client.post("/api/import/scalable/preview", json=body).json()
    assert [(v["date"], v["value"], v["difference"]) for v in preview["valuations"]] == [
        ("2026-03-31", "4950.00", "-550.00")
    ]
    assert client.get("/api/accounts").json()[0]["balance"] == "5500.00"

    written = client.post("/api/import/scalable", json=body).json()
    assert written["written"] == [{"date": "2026-03-31", "difference": "-550.00"}]
    assert written["account"]["verification"]["state"] == "verified"
    # Reading the same statements again books nothing new.
    again = client.post("/api/import/scalable", json=body).json()
    assert again["written"] == [{"date": "2026-03-31", "difference": "-550.00"}]
    rows = json.loads(json.dumps(client.get("/api/virtual-accounts").json()))
    assert [(row["name"], row["balance"]) for row in rows] == [(RETURNS_ACCOUNT, "550.00")]
    client.close()
