"""What day it is is an input: the API and the command line read it from a clock.

Before the clock was a port, a test about "the month in progress" or "the
balance today" answered differently depending on the day it ran.
"""
import datetime as dt
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from amonhen.api import create_app
from amonhen.cli import main
from amonhen.db import connect, open_ledger_db
from amonhen.ledger import Ledger
from amonhen.models import Account, IncomingTransaction
from amonhen.ports.clock import Clock, SystemClock
from fixed_clock import FixedClock

MINIMAL_CONFIG = Path(__file__).resolve().parent / "fixtures" / "config" / "minimal.json"


def spend(ledger, account_id, date, amount, description, external_id):
    ledger.record(
        IncomingTransaction(
            account_id=account_id,
            date=dt.date.fromisoformat(date),
            amount=Decimal(amount),
            description=description,
            status="BOOK",
            source="psd2",
            balancing_account_id=ledger.uncategorized(),
            external_id=external_id,
        )
    )


def ledger_with_two_months(db_path) -> None:
    conn = connect(db_path)
    ledger = Ledger(conn)
    conto = ledger.ensure_account(Account(name="Conto", type="real"))
    spend(ledger, conto, "2026-03-10", "-30.00", "Marzo", "m-1")
    spend(ledger, conto, "2026-04-10", "-50.00", "Aprile", "a-1")
    conn.close()


def test_both_clocks_are_clocks():
    assert isinstance(SystemClock(), Clock)
    assert isinstance(FixedClock(dt.date(2026, 3, 15)), Clock)


def test_the_month_in_progress_is_the_clock_s(tmp_path):
    db_path = tmp_path / "ledger.db"
    app = create_app(
        db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG,
        clock=FixedClock(dt.date(2026, 3, 20)),
    )
    ledger_with_two_months(db_path)

    month = TestClient(app).get("/api/month").json()

    assert (month["month"], month["day"]) == ("2026-03", 20)


def test_a_balance_today_is_the_balance_on_the_clock_s_day(tmp_path):
    db_path = tmp_path / "ledger.db"
    app = create_app(
        db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG,
        clock=FixedClock(dt.date(2026, 3, 20)),
    )
    ledger_with_two_months(db_path)

    accounts = TestClient(app).get("/api/accounts").json()

    # April's movement has not happened yet on the twentieth of March.
    assert [(a["name"], a["balance"]) for a in accounts] == [("Conto", "-30.00")]


def test_the_command_line_spends_the_month_before_the_clock_s(tmp_path, capsys):
    db_path = tmp_path / "ledger.db"
    open_ledger_db(db_path).close()
    ledger_with_two_months(db_path)
    args = ["--db", str(db_path), "--config", str(MINIMAL_CONFIG), "spend"]

    assert main(args, clock=FixedClock(dt.date(2026, 4, 2))) == 0
    assert "spent 2026-03-01..2026-03-31: 30.00 EUR" in capsys.readouterr().out

    assert main(args, clock=FixedClock(dt.date(2026, 5, 2))) == 0
    assert "spent 2026-04-01..2026-04-30: 50.00 EUR" in capsys.readouterr().out
