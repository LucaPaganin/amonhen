"""A refund takes spending down, in every reading of it."""
import datetime as dt
from decimal import Decimal

import pytest

from amonhen.budgets import budget_status, set_default
from amonhen.db import initialize, open_ledger_db
from amonhen.ledger import Ledger
from amonhen.metrics import compute_metrics, month_reading, monthly_flows, spend_by_category
from amonhen.models import Account, IncomingTransaction

TODAY = dt.date(2026, 9, 12)
MONTHS = ("2026-03-10", "2026-04-10", "2026-05-10", "2026-06-10", "2026-07-10", "2026-08-10")


def spend(ledger, account_id, category_id, date, amount, description="spend"):
    return ledger.record(
        IncomingTransaction(
            account_id=account_id,
            date=dt.date.fromisoformat(date),
            amount=Decimal(amount),
            description=description,
            status="BOOK",
            source="import",
            balancing_account_id=category_id,
        )
    )[0]


@pytest.fixture
def ledger(tmp_path):
    conn = open_ledger_db(tmp_path / "ledger.db")
    yield Ledger(conn)
    conn.close()


@pytest.fixture
def account(ledger):
    return ledger.ensure_account(Account(name="Conto", type="real"))


def test_a_refund_takes_its_category_down_in_the_month_it_arrived(ledger, account):
    food = ledger.category("Alimentari")
    spend(ledger, account, food, "2026-09-02", "-100", "spesa per tutti")
    spend(ledger, account, food, "2026-09-05", "30", "la loro parte")

    assert ledger.spend_between(dt.date(2026, 9, 1), dt.date(2026, 9, 30)) == Decimal("70")
    reading = month_reading(ledger, TODAY)
    assert reading.spent == Decimal("70")
    assert [(item.category, item.spent) for item in reading.categories] == [
        ("Alimentari", Decimal("70"))
    ]
    period = spend_by_category(ledger, dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert [(row.category, row.amount) for row in period] == [("Alimentari", Decimal("70"))]


def test_a_salary_and_a_credit_nobody_decided_take_nothing_down(ledger, account):
    salary = ledger.category("Stipendio")
    ledger.set_category_flag(salary, "income", True)
    food = ledger.category("Alimentari")
    spend(ledger, account, food, "2026-09-02", "-100", "spesa")
    spend(ledger, account, salary, "2026-09-03", "2000", "stipendio")
    spend(ledger, account, ledger.uncategorized(), "2026-09-04", "50", "chissà")

    assert ledger.spend_between(dt.date(2026, 9, 1), dt.date(2026, 9, 30)) == Decimal("100")


def test_a_refund_is_not_income(ledger, account):
    salary = ledger.category("Stipendio")
    ledger.set_category_flag(salary, "income", True)
    food = ledger.category("Alimentari")
    spend(ledger, account, food, "2026-09-02", "-100", "spesa")
    spend(ledger, account, food, "2026-09-05", "30", "rimborso")
    spend(ledger, account, salary, "2026-09-06", "2000", "stipendio")
    spend(ledger, account, ledger.uncategorized(), "2026-09-07", "50", "chissà")

    flows = monthly_flows(ledger, dt.date(2026, 9, 1), dt.date(2026, 9, 30))

    assert [(flow.income, flow.expenses) for flow in flows] == [
        (Decimal("2050"), Decimal("70"))
    ]


def test_a_refund_of_a_rare_spend_takes_the_reserve_down(ledger, account):
    travel = ledger.category("Viaggi")
    ledger.set_category_flag(travel, "episodic", True)
    spend(ledger, account, travel, MONTHS[0], "-2400", "viaggio")
    spend(ledger, account, travel, MONTHS[1], "1200", "la loro parte")

    assert compute_metrics(ledger, TODAY).episodic_accrual == Decimal("50")


def test_a_refund_of_a_rare_spend_is_on_the_rare_line_of_the_month(ledger, account):
    travel = ledger.category("Viaggi")
    ledger.set_category_flag(travel, "episodic", True)
    spend(ledger, account, travel, "2026-09-02", "500", "la loro parte")

    reading = month_reading(ledger, TODAY)

    assert reading.rare == Decimal("-500")
    assert reading.spent == Decimal("0")


def test_a_refund_counts_against_the_budget(ledger, account):
    food = ledger.category("Alimentari")
    set_default(ledger, food, "2026-09", Decimal("100"))
    spend(ledger, account, food, "2026-09-02", "-80", "spesa")
    spend(ledger, account, food, "2026-09-05", "30", "rimborso")

    row = next(item for item in budget_status(ledger, "2026-09") if item["category"] == "Alimentari")

    assert Decimal(str(row["spent"])) == Decimal("50")


def test_an_older_ledger_marks_as_income_what_only_ever_took_money_in(tmp_path):
    conn = open_ledger_db(tmp_path / "legacy.db")
    ledger = Ledger(conn)
    account = ledger.ensure_account(Account(name="Conto", type="real"))
    salary = ledger.category("Stipendio")
    mixed = ledger.category("Shopping")
    spend(ledger, account, salary, "2026-09-03", "2000", "stipendio")
    spend(ledger, account, mixed, "2026-09-04", "-90", "scarpe")
    spend(ledger, account, mixed, "2026-09-05", "10", "reso")
    spend(ledger, account, ledger.uncategorized(), "2026-09-06", "5", "chissà")
    conn.execute("ALTER TABLE accounts DROP COLUMN income")
    conn.commit()

    initialize(conn)

    flags = {
        row["name"]: row["income"]
        for row in conn.execute("SELECT name, income FROM accounts WHERE type = 'category'")
    }
    assert flags["Stipendio"] == 1
    assert flags["Shopping"] == 0
    assert flags[ledger.account(ledger.uncategorized())["name"]] == 0
    conn.close()
