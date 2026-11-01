"""Money received towards every expense takes the total down, and no category."""
import datetime as dt
from pathlib import Path
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from amonhen.api import create_app
from amonhen.budgets import budget_status, set_default
from amonhen.db import open_ledger_db
from amonhen.ledger import Ledger
from amonhen.metrics import LedgerScope, compute_metrics, month_reading, monthly_flows, spend_by_category
from amonhen.models import Account, IncomingTransaction
from amonhen.settings import UNCATEGORIZED

MINIMAL_CONFIG = Path(__file__).parent / "fixtures" / "config" / "minimal.json"

TODAY = dt.date(2026, 9, 12)
MONTHS = ("2026-06-10", "2026-07-10", "2026-08-10")


def move(ledger, account_id, category_id, date, amount, description="movement"):
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


@pytest.fixture
def contribution(ledger):
    category = ledger.category("Contributi alle spese")
    ledger.set_category_flag(category, "contribution", True)
    return category


def month_of_spending(ledger, account, contribution):
    food = ledger.category("Alimentari")
    ledger.set_category_flag(food, "essential", True)
    leisure = ledger.category("Svago")
    for day in MONTHS:
        move(ledger, account, food, day, "-300", f"spesa {day}")
        move(ledger, account, leisure, day, "-200", f"svago {day}")
        move(ledger, account, contribution, day, "150", f"quota {day}")


def test_a_contribution_takes_the_typical_spending_down(ledger, account, contribution):
    month_of_spending(ledger, account, contribution)

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.recurring_burn == Decimal("350")
    assert metrics.expected_burn == Decimal("350")
    assert metrics.contributions_monthly == Decimal("150")


def test_the_runway_reads_the_spending_net_of_contributions(ledger, account, contribution):
    month_of_spending(ledger, account, contribution)
    ledger.conn.execute("UPDATE accounts SET opening_balance = '3000', opening_date = '2026-01-01'")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.runway_months == metrics.liquidity / Decimal("350")


def test_essential_and_cuttable_lose_the_same_share(ledger, account, contribution):
    month_of_spending(ledger, account, contribution)

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.essential_monthly == Decimal("210")
    assert metrics.discretionary_monthly == Decimal("140")


def test_a_contribution_covers_only_the_account_it_reached(ledger, account, contribution):
    other = ledger.ensure_account(Account(name="Altro", type="real"))
    food = ledger.category("Alimentari")
    ledger.set_category_flag(food, "essential", True)
    leisure = ledger.category("Svago")
    for day in MONTHS:
        move(ledger, account, food, day, "-100", f"comune {day}")
        move(ledger, account, contribution, day, "50", f"quota {day}")
        move(ledger, other, leisure, day, "-200", f"mio {day}")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.essential_monthly == Decimal("50")
    assert metrics.discretionary_monthly == Decimal("200")


def test_a_contribution_covers_at_most_all_of_it(ledger, account, contribution):
    food = ledger.category("Alimentari")
    ledger.set_category_flag(food, "essential", True)
    for day in MONTHS:
        move(ledger, account, food, day, "-100", f"spesa {day}")
        move(ledger, account, contribution, day, "300", f"quota {day}")

    assert compute_metrics(ledger, TODAY).essential_monthly == Decimal("0")


def test_a_contribution_leaves_the_rare_spending_alone(ledger, account, contribution):
    travel = ledger.category("Viaggi")
    ledger.set_category_flag(travel, "episodic", True)
    food = ledger.category("Alimentari")
    ledger.set_category_flag(food, "essential", True)
    for day in MONTHS:
        move(ledger, account, food, day, "-100", f"spesa {day}")
        move(ledger, account, travel, day, "-2400", f"viaggio {day}")
        move(ledger, account, contribution, day, "50", f"quota {day}")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.episodic_accrual == Decimal("300")
    assert metrics.essential_monthly == Decimal("50")


def test_a_rare_tag_does_not_move_a_contribution_into_the_reserve(ledger, account, contribution):
    month_of_spending(ledger, account, contribution)
    ledger.set_tag_flag(ledger.tag("Viaggio"), "episodic", True)
    paid = ledger.conn.execute(
        "SELECT id FROM transactions WHERE description LIKE 'quota%'"
    ).fetchall()
    for row in paid:
        ledger.add_tag(row["id"], "Viaggio")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.recurring_burn == Decimal("350")
    assert metrics.episodic_accrual is None or metrics.episodic_accrual == 0


def test_a_month_without_contributions_counts_as_a_zero(ledger, account, contribution):
    food = ledger.category("Alimentari")
    for day in MONTHS:
        move(ledger, account, food, day, "-300", f"spesa {day}")
    move(ledger, account, contribution, MONTHS[2], "90", "una volta")

    assert compute_metrics(ledger, TODAY).contributions_monthly == Decimal("0")


def test_no_contribution_is_no_figure(ledger, account):
    move(ledger, account, ledger.category("Alimentari"), MONTHS[2], "-300")

    assert compute_metrics(ledger, TODAY).contributions_monthly is None


def test_the_month_stays_gross_and_says_what_is_left(ledger, account, contribution):
    food = ledger.category("Alimentari")
    move(ledger, account, food, "2026-09-02", "-500", "spesa")
    move(ledger, account, contribution, "2026-09-05", "200", "quota")

    reading = month_reading(ledger, TODAY)

    assert reading.spent == Decimal("500")
    assert reading.contributions == Decimal("200")
    assert reading.net == Decimal("300")
    assert [item.category for item in reading.categories] == ["Alimentari"]


def test_a_contribution_is_outside_the_usual_of_the_month(ledger, account, contribution):
    month_of_spending(ledger, account, contribution)
    ledger.conn.execute("UPDATE transactions SET date = replace(date, '-10', '-02')")
    ledger.conn.commit()

    assert month_reading(ledger, TODAY).usual == Decimal("500")


def test_a_contribution_on_another_account_is_outside_that_account(ledger, account, contribution):
    other = ledger.ensure_account(Account(name="Altro", type="real"))
    move(ledger, other, contribution, "2026-09-05", "200", "quota")

    assert month_reading(ledger, TODAY, LedgerScope(accounts=("Conto",))).contributions == 0
    assert month_reading(ledger, TODAY, LedgerScope(accounts=("Altro",))).contributions == 200


def test_a_contribution_is_neither_income_nor_a_category_nor_a_budget(ledger, account, contribution):
    salary = ledger.category("Stipendio")
    ledger.set_category_flag(salary, "income", True)
    food = ledger.category("Alimentari")
    set_default(ledger, contribution, "2026-09", Decimal("100"))
    move(ledger, account, salary, "2026-09-01", "2000", "stipendio")
    move(ledger, account, food, "2026-09-02", "-500", "spesa")
    move(ledger, account, contribution, "2026-09-05", "200", "quota")
    start, end = dt.date(2026, 9, 1), dt.date(2026, 9, 30)

    flows = monthly_flows(ledger, start, end)
    row = next(
        item for item in budget_status(ledger, "2026-09") if item["category"] == "Contributi alle spese"
    )

    assert [(flow.income, flow.expenses) for flow in flows] == [(Decimal("2000"), Decimal("300"))]
    assert [item.category for item in spend_by_category(ledger, start, end)] == ["Alimentari"]
    assert Decimal(str(row["spent"])) == 0


def test_a_contribution_is_a_kind_of_its_own(ledger, contribution):
    ledger.set_category_flag(contribution, "episodic", True)
    assert ledger.account(contribution)["contribution"] == 0

    ledger.set_category_flag(contribution, "contribution", True)
    row = ledger.account(contribution)
    assert (row["contribution"], row["episodic"], row["essential"], row["income"]) == (1, 0, 0, 0)


def test_the_review_category_cannot_hold_contributions(ledger):
    with pytest.raises(ValueError):
        ledger.set_category_flag(ledger.category(UNCATEGORIZED), "contribution", True)


def test_a_description_is_written_trimmed_and_removed_when_empty(ledger, contribution):
    ledger.set_category_description(contribution, "  I versamenti sul conto comune  ")
    assert ledger.account(contribution)["description"] == "I versamenti sul conto comune"

    ledger.set_category_description(contribution, "   ")
    assert ledger.account(contribution)["description"] is None


def test_the_api_writes_the_kind_and_the_description(tmp_path):
    db = tmp_path / "api.db"
    conn = open_ledger_db(db)
    category = Ledger(conn).category("Quote")
    conn.close()
    client = TestClient(create_app(db, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG))

    answer = client.patch(
        f"/api/categories/{category}", json={"contribution": True, "description": "Le quote"}
    )

    assert answer.status_code == 200
    assert answer.json()["contribution"] is True
    listed = next(item for item in client.get("/api/categories").json() if item["name"] == "Quote")
    assert listed["description"] == "Le quote"
    assert client.patch(f"/api/categories/{category}", json={}).status_code == 422
