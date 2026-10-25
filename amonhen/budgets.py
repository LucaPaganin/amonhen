"""Monthly budgets: a ceiling per category and month, and the items planned inside it.

Desiderata 5.12. A category's ceiling is a default that holds from a month
onwards — changing it while looking at November leaves October with what it had,
because a budget rewritten backwards erases the history it was meant to keep —
and one month may override it for itself. Inside the ceiling a person writes the
expenses they already know about; the priority orders them, and the ceiling says
which of them still fit. Spending stays per category: an item never learns
whether it was paid, the category's outflows are what the ceiling is held to.
"""
import calendar
import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from amonhen.ledger import Ledger
from amonhen.models import format_decimal, parse_decimal
from amonhen.settings import UNCATEGORIZED

# Read in this order: what cannot be skipped first, what can wait last.
PRIORITIES = ("essential", "important", "deferrable")
_PRIORITY_RANK = {name: rank for rank, name in enumerate(PRIORITIES)}

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class ItemFields:
    """What a person writes on a planned expense."""

    category_id: int
    month: str
    description: str
    amount: Decimal
    date: dt.date | None
    priority: str
    note: str | None


def parse_month(value: str) -> str:
    """A YYYY-MM month, refused when it is anything else."""
    if not _MONTH.match(value.strip()):
        raise ValueError(f"{value!r} is not a YYYY-MM month")
    return value.strip()


def month_of(day: dt.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def month_bounds(month: str) -> tuple[dt.date, dt.date]:
    year, number = (int(part) for part in parse_month(month).split("-"))
    return dt.date(year, number, 1), dt.date(year, number, calendar.monthrange(year, number)[1])


def set_default(ledger: Ledger, category_id: int, month: str, amount: Decimal | None) -> None:
    """Set a category's default ceiling from ``month`` on; None removes it from then.

    "From this month on" replaces any later change too: a default written for
    January and then rewritten from November must not leave January's value
    surfacing again two months later.
    """
    _require_budget_category(ledger, category_id)
    month = parse_month(month)
    _require_ceiling(amount)
    with ledger.conn:
        ledger.conn.execute(
            "DELETE FROM budgets WHERE category_id = ? AND from_month >= ?", (category_id, month)
        )
        ledger.conn.execute(
            "INSERT INTO budgets (category_id, from_month, amount, updated_at) VALUES (?, ?, ?, ?)",
            (category_id, month, _text(amount), _now()),
        )


def set_month_override(ledger: Ledger, category_id: int, month: str, amount: Decimal | None) -> None:
    """Give one month its own ceiling; None hands it back to the default."""
    _require_budget_category(ledger, category_id)
    month = parse_month(month)
    _require_ceiling(amount)
    with ledger.conn:
        if amount is None:
            ledger.conn.execute(
                "DELETE FROM budget_months WHERE category_id = ? AND month = ?", (category_id, month)
            )
            return
        ledger.conn.execute(
            """INSERT INTO budget_months (category_id, month, amount, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT (category_id, month) DO UPDATE SET
                   amount = excluded.amount, updated_at = excluded.updated_at""",
            (category_id, month, format_decimal(amount), _now()),
        )


def budget_status(ledger: Ledger, month: str) -> list[dict]:
    """Per category, for one month: the ceiling, the items inside it, what was spent."""
    month = parse_month(month)
    defaults = _defaults(ledger, month)
    overrides = _overrides(ledger, month)
    spent = _spent(ledger, month)
    items = _items(ledger, month)
    status = []
    for row in ledger.conn.execute(
        "SELECT id, name FROM accounts WHERE type = 'category' AND name != ? ORDER BY name",
        (UNCATEGORIZED,),
    ):
        category_id = row["id"]
        default = defaults.get(category_id)
        override = overrides.get(category_id)
        ceiling = override if override is not None else default
        category_spent = spent.get(category_id, Decimal(0))
        planned_items = sorted(items.get(category_id, []), key=_reading_order)
        planned = sum((item["amount"] for item in planned_items), Decimal(0))
        fits = fitting(planned_items, ceiling)
        status.append(
            {
                "id": category_id,
                "category": row["name"],
                "budget": _text(ceiling),
                "default": _text(default),
                "override": _text(override),
                "spent": format_decimal(category_spent),
                "remaining": _text(None if ceiling is None else ceiling - category_spent),
                "planned": format_decimal(planned),
                "free": _text(None if ceiling is None else ceiling - planned),
                "over_plan": ceiling is not None and planned > ceiling,
                "items": [
                    {
                        "id": item["id"],
                        "description": item["description"],
                        "amount": format_decimal(item["amount"]),
                        "date": item["date"],
                        "priority": item["priority"],
                        "note": item["note"],
                        "fits": fit,
                    }
                    for item, fit in zip(planned_items, fits)
                ],
            }
        )
    return status


def fitting(items: Iterable[dict], ceiling: Decimal | None) -> list[bool | None]:
    """Whether each item, read in order, still fits under the ceiling.

    The running total decides: an item fits while it and every item before it
    stay within the ceiling. Without a ceiling there is nothing to fit under,
    which is not the same as fitting.
    """
    if ceiling is None:
        return [None for _ in items]
    total = Decimal(0)
    fits = []
    for item in items:
        total += item["amount"]
        fits.append(total <= ceiling)
    return fits


def add_item(ledger: Ledger, fields: ItemFields) -> int:
    values = _item_values(ledger, fields)
    with ledger.conn:
        cursor = ledger.conn.execute(
            """INSERT INTO budget_items
                   (category_id, month, description, amount, date, priority, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (*values, _now()),
        )
    return cursor.lastrowid


def update_item(ledger: Ledger, item_id: int, fields: ItemFields) -> None:
    """Rewrite an item whole: its month and its category may change too."""
    get_item(ledger, item_id)
    values = _item_values(ledger, fields)
    with ledger.conn:
        ledger.conn.execute(
            """UPDATE budget_items SET category_id = ?, month = ?, description = ?, amount = ?,
                   date = ?, priority = ?, note = ?
               WHERE id = ?""",
            (*values, item_id),
        )


def delete_item(ledger: Ledger, item_id: int) -> None:
    get_item(ledger, item_id)
    with ledger.conn:
        ledger.conn.execute("DELETE FROM budget_items WHERE id = ?", (item_id,))


def get_item(ledger: Ledger, item_id: int) -> dict:
    row = ledger.conn.execute("SELECT * FROM budget_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise KeyError(f"budget item {item_id} not found")
    return dict(row)


def copy_items(ledger: Ledger, category_id: int, from_month: str, to_month: str) -> int:
    """Copy a category's items from one month to another, and say how many arrived.

    A date keeps its day, moved into the target month (the 31st becomes the last
    day of a shorter one). An item the target already holds — same description,
    same amount — is not copied again, so pressing twice does not double a plan.
    """
    _require_budget_category(ledger, category_id)
    from_month, to_month = parse_month(from_month), parse_month(to_month)
    if from_month == to_month:
        raise ValueError("an item is copied into another month")
    present = {
        (row["description"], parse_decimal(row["amount"]))
        for row in ledger.conn.execute(
            "SELECT description, amount FROM budget_items WHERE category_id = ? AND month = ?",
            (category_id, to_month),
        )
    }
    copied = 0
    for row in ledger.conn.execute(
        "SELECT * FROM budget_items WHERE category_id = ? AND month = ? ORDER BY id",
        (category_id, from_month),
    ).fetchall():
        amount = parse_decimal(row["amount"])
        if (row["description"], amount) in present:
            continue
        add_item(
            ledger,
            ItemFields(
                category_id=category_id,
                month=to_month,
                description=row["description"],
                amount=amount,
                date=None if row["date"] is None else move_day(dt.date.fromisoformat(row["date"]), to_month),
                priority=row["priority"],
                note=row["note"],
            ),
        )
        copied += 1
    return copied


def move_day(day: dt.date, month: str) -> dt.date:
    """The same day of the month in another month, clipped to its last day."""
    start, end = month_bounds(month)
    return start.replace(day=min(day.day, end.day))


def _require_budget_category(ledger: Ledger, category_id: int) -> None:
    row = ledger.account(category_id)
    if row["type"] != "category" or row["name"] == UNCATEGORIZED:
        raise ValueError(f"account {category_id} is not a category with a budget")


def _require_ceiling(amount: Decimal | None) -> None:
    if amount is not None and amount < 0:
        raise ValueError("a budget cannot be negative")


def _item_values(ledger: Ledger, fields: ItemFields) -> tuple:
    _require_budget_category(ledger, fields.category_id)
    month = parse_month(fields.month)
    description = fields.description.strip()
    if not description:
        raise ValueError("a planned expense needs a description")
    if fields.amount <= 0:
        raise ValueError("a planned expense is a positive amount")
    if fields.priority not in _PRIORITY_RANK:
        raise ValueError(f"unknown priority {fields.priority!r}")
    if fields.date is not None and month_of(fields.date) != month:
        raise ValueError(f"{fields.date.isoformat()} is not in {month}")
    note = (fields.note or "").strip() or None
    return (
        fields.category_id,
        month,
        description,
        format_decimal(fields.amount),
        None if fields.date is None else fields.date.isoformat(),
        fields.priority,
        note,
    )


def _defaults(ledger: Ledger, month: str) -> dict[int, Decimal]:
    """The default each category holds in ``month``: its latest change up to it."""
    rows = ledger.conn.execute(
        """SELECT b.category_id, b.amount FROM budgets b
           WHERE b.from_month = (
               SELECT MAX(from_month) FROM budgets
               WHERE category_id = b.category_id AND from_month <= ?
           )""",
        (month,),
    )
    return {row["category_id"]: parse_decimal(row["amount"]) for row in rows if row["amount"] is not None}


def _overrides(ledger: Ledger, month: str) -> dict[int, Decimal]:
    rows = ledger.conn.execute(
        "SELECT category_id, amount FROM budget_months WHERE month = ?", (month,)
    )
    return {row["category_id"]: parse_decimal(row["amount"]) for row in rows}


def _spent(ledger: Ledger, month: str) -> dict[int, Decimal]:
    """Settled outflows per category in the month, as `spend_between` counts them."""
    start, end = month_bounds(month)
    spent: dict[int, Decimal] = {}
    for row in ledger.conn.execute(
        """SELECT p.account_id, p.amount FROM postings p
           JOIN transactions t ON t.id = p.transaction_id
           JOIN accounts a ON a.id = p.account_id
           WHERE a.type = 'category' AND t.status = 'BOOK'
             AND CAST(t.amount AS REAL) < 0
             AND t.date >= ? AND t.date <= ?""",
        (start.isoformat(), end.isoformat()),
    ):
        spent[row["account_id"]] = spent.get(row["account_id"], Decimal(0)) + parse_decimal(row["amount"])
    return spent


def _items(ledger: Ledger, month: str) -> dict[int, list[dict]]:
    items: dict[int, list[dict]] = {}
    for row in ledger.conn.execute("SELECT * FROM budget_items WHERE month = ?", (month,)):
        entry = dict(row)
        entry["amount"] = parse_decimal(row["amount"])
        items.setdefault(row["category_id"], []).append(entry)
    return items


def _reading_order(entry: dict) -> tuple:
    """Priority first, then the date (undated last), then the order they were written."""
    return (_PRIORITY_RANK[entry["priority"]], entry["date"] is None, entry["date"] or "", entry["id"])


def _text(amount: Decimal | None) -> str | None:
    return None if amount is None else format_decimal(amount)


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()
