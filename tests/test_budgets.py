"""Budgets planned by month (desiderata 5.12): a ceiling with a default, and items inside it."""
import datetime as dt
from decimal import Decimal

import pytest

from amonhen.budgets import (
    ItemFields,
    add_item,
    budget_month,
    budget_status,
    copy_items,
    delete_item,
    move_day,
    set_default,
    set_month_override,
    update_item,
)
from amonhen.db import connect, initialize
from amonhen.ledger import Ledger
from amonhen.models import Account, IncomingTransaction


def make_txn(ledger, account_id, date, amount, description):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(date),
        amount=Decimal(amount),
        description=description,
        status="BOOK",
        source="psd2",
        balancing_account_id=ledger.uncategorized(),
        raw={"description": description},
    )


def status_of(ledger, month, category="Groceries"):
    return next(row for row in budget_status(ledger, month) if row["category"] == category)


def fields(category_id, month="2026-11", description="Regalo", amount="80.00", *,
           date=None, priority="important", note=None):
    return ItemFields(
        category_id=category_id,
        month=month,
        description=description,
        amount=Decimal(amount),
        date=None if date is None else dt.date.fromisoformat(date),
        priority=priority,
        note=note,
    )


def test_budget_status_reports_spent_and_remaining(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "EKOM"))
    ledger.set_category(1, groceries)
    set_default(ledger, groceries, "2026-01", Decimal("100.00"))

    status = status_of(ledger, "2026-01")

    assert status["budget"] == "100.00"
    assert status["spent"] == "42.50"
    assert status["remaining"] == "57.50"


def test_a_default_holds_from_its_month_and_leaves_the_months_before_alone(ledger):
    groceries = ledger.category("Groceries")
    set_default(ledger, groceries, "2026-01", Decimal("400.00"))

    set_default(ledger, groceries, "2026-11", Decimal("300.00"))

    assert status_of(ledger, "2025-12")["budget"] is None
    assert status_of(ledger, "2026-10")["budget"] == "400.00"
    assert status_of(ledger, "2026-11")["budget"] == "300.00"
    assert status_of(ledger, "2027-03")["budget"] == "300.00"


def test_a_default_from_a_month_replaces_the_later_changes(ledger):
    groceries = ledger.category("Groceries")
    set_default(ledger, groceries, "2027-01", Decimal("500.00"))

    set_default(ledger, groceries, "2026-11", Decimal("300.00"))

    assert status_of(ledger, "2027-02")["budget"] == "300.00"


def test_clearing_a_default_clears_it_from_that_month_only(ledger):
    groceries = ledger.category("Groceries")
    set_default(ledger, groceries, "2026-01", Decimal("400.00"))

    set_default(ledger, groceries, "2026-11", None)

    assert status_of(ledger, "2026-10")["budget"] == "400.00"
    assert status_of(ledger, "2026-11")["budget"] is None


def test_a_month_overrides_the_default_for_itself(ledger):
    gifts = ledger.category("Groceries")
    set_default(ledger, gifts, "2026-01", Decimal("50.00"))

    set_month_override(ledger, gifts, "2026-12", Decimal("300.00"))

    december = status_of(ledger, "2026-12")
    assert (december["budget"], december["default"], december["override"]) == ("300.00", "50.00", "300.00")
    assert status_of(ledger, "2027-01")["budget"] == "50.00"

    set_month_override(ledger, gifts, "2026-12", None)

    assert status_of(ledger, "2026-12")["budget"] == "50.00"


def test_a_budget_must_be_a_category_and_not_negative(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")

    with pytest.raises(ValueError, match="not a category"):
        set_default(ledger, account, "2026-11", Decimal("10.00"))
    with pytest.raises(ValueError, match="not a category"):
        set_default(ledger, ledger.uncategorized(), "2026-11", Decimal("10.00"))
    with pytest.raises(ValueError, match="cannot be negative"):
        set_month_override(ledger, groceries, "2026-11", Decimal("-1.00"))
    with pytest.raises(ValueError, match="YYYY-MM"):
        set_default(ledger, groceries, "2026-13", Decimal("10.00"))


def test_items_take_part_of_the_ceiling_and_say_what_is_left(ledger):
    groceries = ledger.category("Groceries")
    set_default(ledger, groceries, "2026-11", Decimal("400.00"))

    add_item(ledger, fields(groceries, description="Cena", amount="70.00"))
    add_item(ledger, fields(groceries, description="Regalo", amount="50.00"))

    status = status_of(ledger, "2026-11")
    assert (status["planned"], status["free"], status["over_plan"]) == ("120.00", "280.00", False)
    assert status_of(ledger, "2026-12")["items"] == []


def test_items_read_by_priority_and_date_and_fit_while_the_running_total_does(ledger):
    groceries = ledger.category("Groceries")
    set_month_override(ledger, groceries, "2026-11", Decimal("100.00"))
    add_item(ledger, fields(groceries, description="Weekend", amount="60.00", priority="deferrable"))
    add_item(ledger, fields(groceries, description="Bolletta", amount="50.00", priority="essential"))
    add_item(ledger, fields(groceries, description="Libro", amount="20.00", date="2026-11-20"))
    add_item(ledger, fields(groceries, description="Cena", amount="40.00", date="2026-11-05"))

    status = status_of(ledger, "2026-11")

    assert [(item["description"], item["fits"]) for item in status["items"]] == [
        ("Bolletta", True),
        ("Cena", True),
        ("Libro", False),
        ("Weekend", False),
    ]
    assert status["over_plan"] is True
    assert status["free"] == "-70.00"


def test_without_a_ceiling_the_items_are_the_budget(ledger):
    groceries = ledger.category("Groceries")

    add_item(ledger, fields(groceries))
    add_item(ledger, fields(groceries, description="Cena", amount="20.00"))

    status = status_of(ledger, "2026-11")
    assert (status["budget"], status["source"]) == ("100.00", "items")
    assert [item["fits"] for item in status["items"]] == [True, True]
    assert (status["planned"], status["free"], status["over_plan"]) == ("100.00", "0.00", False)
    # A ceiling a person writes is theirs: the items no longer move it.
    set_default(ledger, groceries, "2026-11", Decimal("90"))
    status = status_of(ledger, "2026-11")
    assert (status["budget"], status["source"], status["over_plan"]) == ("90.00", "default", True)


def test_a_category_without_items_or_ceiling_has_no_budget(ledger):
    ledger.category("Groceries")
    status = status_of(ledger, "2026-11")
    assert (status["budget"], status["source"]) == (None, None)


def test_an_item_is_refused_when_it_does_not_describe_an_expense_of_its_month(ledger):
    groceries = ledger.category("Groceries")

    with pytest.raises(ValueError, match="description"):
        add_item(ledger, fields(groceries, description="  "))
    with pytest.raises(ValueError, match="positive"):
        add_item(ledger, fields(groceries, amount="0"))
    with pytest.raises(ValueError, match="priority"):
        add_item(ledger, fields(groceries, priority="urgent"))
    with pytest.raises(ValueError, match="not in 2026-11"):
        add_item(ledger, fields(groceries, date="2026-12-01"))


def test_an_item_can_move_to_another_month_and_category(ledger):
    groceries = ledger.category("Groceries")
    gifts = ledger.category("Gifts")
    item_id = add_item(ledger, fields(groceries, date="2026-11-12"))

    update_item(ledger, item_id, fields(gifts, month="2026-12", amount="90.00", priority="deferrable"))

    assert status_of(ledger, "2026-11")["items"] == []
    moved = status_of(ledger, "2026-12", "Gifts")["items"][0]
    assert (moved["amount"], moved["date"], moved["priority"]) == ("90.00", None, "deferrable")

    delete_item(ledger, item_id)

    assert status_of(ledger, "2026-12", "Gifts")["items"] == []
    with pytest.raises(KeyError):
        delete_item(ledger, item_id)


def test_copying_a_month_moves_the_days_and_does_not_double_a_plan(ledger):
    groceries = ledger.category("Groceries")
    add_item(ledger, fields(groceries, month="2027-01", description="Affitto box", amount="90.00",
                            date="2027-01-31", priority="essential", note="bonifico"))
    add_item(ledger, fields(groceries, month="2027-01", description="Cena", amount="40.00"))

    assert copy_items(ledger, groceries, "2027-01", "2027-02") == 2
    assert copy_items(ledger, groceries, "2027-01", "2027-02") == 0

    copied = status_of(ledger, "2027-02")["items"]
    assert [(item["description"], item["date"], item["note"]) for item in copied] == [
        ("Affitto box", "2027-02-28", "bonifico"),
        ("Cena", None, None),
    ]


def test_a_day_keeps_its_number_in_another_month_up_to_its_last_day():
    assert move_day(dt.date(2026, 10, 14), "2026-11") == dt.date(2026, 11, 14)
    assert move_day(dt.date(2026, 10, 31), "2026-11") == dt.date(2026, 11, 30)


def test_a_budget_written_before_months_existed_becomes_a_default_from_always(tmp_path):
    """The single amount per category kept covering every month after the upgrade."""
    conn = connect(tmp_path / "legacy-budgets.db")
    initialize(conn)
    category = conn.execute(
        "INSERT INTO accounts (name, type) VALUES ('Groceries', 'category')"
    ).lastrowid
    conn.executescript(
        """
        DROP TABLE budgets;
        CREATE TABLE budgets (
            category_id INTEGER PRIMARY KEY REFERENCES accounts(id),
            amount TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute("INSERT INTO budgets VALUES (?, '250.00', '2026-05-01T00:00:00+00:00')", (category,))
    conn.commit()

    initialize(conn)

    ledger = Ledger(conn)
    assert status_of(ledger, "2019-01")["budget"] == "250.00"
    assert status_of(ledger, "2026-11")["budget"] == "250.00"
    conn.close()


def test_a_row_says_what_the_category_usually_takes(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    for date, amount in (("2026-08-10", "-100"), ("2026-09-10", "-300"), ("2026-10-10", "-200")):
        ledger.record(
            IncomingTransaction(
                account_id=account,
                date=dt.date.fromisoformat(date),
                amount=Decimal(amount),
                description="spesa",
                status="BOOK",
                source="import",
                balancing_account_id=groceries,
            )
        )

    rows = budget_status(ledger, "2026-11", dt.date(2026, 11, 2))
    usual = {row["category"]: row["usual"] for row in rows}

    assert usual["Groceries"] == "200.00"
    assert budget_status(ledger, "2026-08", dt.date(2026, 11, 2))[0]["usual"] is None


def test_an_item_without_a_category_takes_the_one_a_rule_gives_or_waits(ledger):
    from amonhen.merchants import RuleBook

    groceries = ledger.category("Groceries")
    RuleBook(ledger.conn).set_rule("esselunga", "Groceries", ledger)

    add_item(ledger, fields(None, description="Spesa Esselunga grande", amount="120.00"))
    add_item(ledger, fields(None, description="Idraulico", amount="90.00"))

    month = budget_month(ledger, "2026-11", dt.date(2026, 11, 2))
    row = next(row for row in month["categories"] if row["id"] == groceries)
    assert [item["description"] for item in row["items"]] == ["Spesa Esselunga grande"]
    assert (row["budget"], row["source"]) == ("120.00", "items")
    assert [(item["description"], item["category_id"]) for item in month["unassigned"]] == [
        ("Idraulico", None)
    ]
    assert (month["total"]["budget"], month["total"]["unassigned"]) == ("120.00", "90.00")


def test_the_month_reads_its_budgets_against_the_months_before(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    trips = ledger.category("Trips")
    for date, amount, category in (
        ("2026-08-10", "-100", groceries),
        ("2026-09-10", "-300", groceries),
        ("2026-10-10", "-200", groceries),
        ("2026-09-20", "-900", trips),
    ):
        ledger.record(
            IncomingTransaction(
                account_id=account,
                date=dt.date.fromisoformat(date),
                amount=Decimal(amount),
                description="spesa",
                status="BOOK",
                source="import",
                balancing_account_id=category,
            )
        )
    set_default(ledger, groceries, "2026-11", Decimal("250"))

    month = budget_month(ledger, "2026-11", dt.date(2026, 11, 2))

    assert month["window"] == {"from": "2026-08", "to": "2026-10", "months": 3}
    row = next(row for row in month["categories"] if row["id"] == groceries)
    assert (row["usual"], row["usual_mean"]) == ("200.00", "200.00")
    total = month["total"]
    assert (total["budget"], total["categories"]) == ("250.00", 1)
    # The whole spending: 100, 1200, 200. The budgeted categories alone: 100, 300, 200.
    assert (total["usual"], total["usual_mean"]) == ("200.00", "500.00")
    assert (total["budgeted_usual"], total["budgeted_usual_mean"]) == ("200.00", "200.00")
