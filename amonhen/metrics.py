"""Ledger readings: the 5.6 metrics and the dashboard series.

Desiderata 5.6 asks for burn, episodic accrual, runway and savings flow; the
dashboard asks for what each category took, what came in and what went out per
month, and what the tracked accounts are worth over time. Both are a pure
reporting layer: they read the ledger through :class:`Ledger` and never write.
Every money value is a :class:`~decimal.Decimal`; a metric that cannot be
computed from the available history is ``None``, and the ``partial`` flags say
whether the window was shorter than the nominal one.
"""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from amonhen.ledger import Ledger
from amonhen.models import parse_decimal

__all__ = [
    "AccountBalance",
    "CategorySpend",
    "LedgerScope",
    "Metrics",
    "MonthlyFlow",
    "NetWorthPoint",
    "compute_metrics",
    "latest_balances",
    "monthly_flows",
    "net_worth_series",
    "spend_by_category",
]


@dataclass(frozen=True)
class Metrics:
    """The 5.6 metrics, all computed from the ledger at one point in time."""

    months_of_history: int
    partial: bool
    recurring_burn: Decimal | None
    episodic_accrual: Decimal | None
    episodic_partial: bool
    expected_burn: Decimal | None
    liquidity: Decimal
    runway_months: Decimal | None
    essential_monthly: Decimal | None
    discretionary_monthly: Decimal | None
    savings_flow: Decimal | None
    period_start: dt.date
    period_end: dt.date
    window_months: int = 6
    episodic_months: int = 24


@dataclass(frozen=True)
class LedgerScope:
    """Which slice of the ledger a reading is about.

    Account names narrow everything that belongs to an account: spending by the
    account that paid it, liquidity, savings, net worth. Category names narrow
    spending only — a category says nothing about the money that comes in, and
    liquidity is not a category's business. Empty means every one of them.
    """

    accounts: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()


# -- calendar helpers ------------------------------------------------------

def _month_index(day: dt.date) -> int:
    """A month as a single integer, so month arithmetic is plain integer math."""
    return day.year * 12 + day.month - 1


def _month_key(index: int) -> str:
    year, month = divmod(index, 12)
    return f"{year:04d}-{month + 1:02d}"


def _month_bounds(index: int) -> tuple[dt.date, dt.date]:
    year, month = divmod(index, 12)
    month += 1
    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, 1), dt.date(year, month, last)


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _window(earliest: int | None, last_complete: int, months: int) -> tuple[int, int] | None:
    """The last ``months`` complete months, clipped to the months we have data for."""
    if earliest is None or last_complete < earliest:
        return None
    return max(earliest, last_complete - months + 1), last_complete


# -- ledger queries --------------------------------------------------------

def _placeholders(names: tuple[str, ...]) -> str:
    """One ``?`` per name, for a list the caller already de-duplicated."""
    return ", ".join("?" for _ in names)


def _spending_scope(scope: LedgerScope) -> tuple[str, list[object]]:
    """The test a category-side query needs to obey a scope.

    A category posting has no account of its own, so the account that paid is
    the real side of the same transaction: that is what makes "what did I spend
    on these two cards" an answerable question.
    """
    sql = ""
    params: list[object] = []
    if scope.accounts:
        sql += (
            " AND EXISTS (SELECT 1 FROM postings paid"
            " JOIN accounts payer ON payer.id = paid.account_id"
            " WHERE paid.transaction_id = t.id AND payer.type = 'real'"
            f" AND payer.name IN ({_placeholders(scope.accounts)}))"
        )
        params += list(scope.accounts)
    if scope.categories:
        sql += f" AND a.name IN ({_placeholders(scope.categories)})"
        params += list(scope.categories)
    return sql, params


def _account_scope(scope: LedgerScope, column: str) -> tuple[str, list[object]]:
    """The test an account-side query needs: keep only these accounts."""
    if not scope.accounts:
        return "", []
    return f" AND {column} IN ({_placeholders(scope.accounts)})", list(scope.accounts)


def _monthly_category_totals(
    ledger: Ledger,
    start: dt.date,
    end: dt.date,
    *,
    episodic: bool,
    essential: bool | None = None,
    scope: LedgerScope = LedgerScope(),
) -> dict[str, Decimal]:
    """Category posting totals per ``YYYY-MM`` month for one flag combination.

    Only transactions that moved money out of an account count, exactly like
    ``Ledger.spend_between``: incoming money carries a negative category
    posting and would otherwise net against spending month by month.
    """
    sql = """
        SELECT substr(t.date, 1, 7) AS month, p.amount AS amount
        FROM postings p
        JOIN transactions t ON t.id = p.transaction_id
        JOIN accounts a ON a.id = p.account_id
        WHERE a.type = 'category' AND t.status = 'BOOK'
          AND CAST(t.amount AS REAL) < 0
          AND a.episodic = ?
          AND t.date >= ? AND t.date <= ?
    """
    params: list[object] = [1 if episodic else 0, start.isoformat(), end.isoformat()]
    if essential is not None:
        sql += " AND a.essential = ?"
        params.append(1 if essential else 0)
    scoped, scope_params = _spending_scope(scope)
    sql += scoped
    params += scope_params
    totals: dict[str, Decimal] = {}
    for row in ledger.conn.execute(sql, params):
        month = row["month"]
        totals[month] = totals.get(month, Decimal(0)) + parse_decimal(row["amount"])
    return totals


def _window_total(
    ledger: Ledger, start: dt.date, end: dt.date, sql: str, extra: Iterable[object] = ()
) -> Decimal | None:
    total = Decimal(0)
    seen = False
    params = (start.isoformat(), end.isoformat(), *extra)
    for row in ledger.conn.execute(sql, params):
        total += parse_decimal(row["amount"])
        seen = True
    return total if seen else None


_SAVINGS_SQL = """
    SELECT p.amount AS amount
    FROM postings p
    JOIN transactions t ON t.id = p.transaction_id
    JOIN accounts a ON a.id = p.account_id
    WHERE a.type = 'real' AND a.investment = 1 AND t.status = 'BOOK'
      AND t.date >= ? AND t.date <= ?
"""


def _window_values(totals: dict[str, Decimal], keys: Iterable[str]) -> list[Decimal]:
    return [totals.get(key, Decimal(0)) for key in keys]


# -- entry point -----------------------------------------------------------

def compute_metrics(
    ledger: Ledger,
    today: dt.date,
    window_months: int = 6,
    episodic_months: int = 24,
    scope: LedgerScope = LedgerScope(),
) -> Metrics:
    """Compute the 5.6 metrics as of ``today``.

    A complete month is a calendar month that ended before ``today``; the last
    ``window_months`` (or ``episodic_months``) of them name the windows. A
    window is clipped to the months the ledger actually covers, so a short
    history yields a metric over fewer months with ``partial`` set, not a
    deflated median padded with pre-history zeros.

    ``scope`` narrows what the numbers are about: account names follow the
    spending, the liquidity and the savings flow, category names the spending
    alone. A period is deliberately not a parameter — the windows of 5.6 are
    what these metrics are, not a view over them.
    """
    if window_months < 1 or episodic_months < 1:
        raise ValueError("window_months and episodic_months must be positive")
    last_complete = _month_index(today) - 1

    first_book = ledger.conn.execute(
        "SELECT MIN(date) AS first FROM transactions WHERE status = 'BOOK'"
    ).fetchone()["first"]
    earliest = _month_index(dt.date.fromisoformat(first_book)) if first_book else None

    if earliest is not None and last_complete >= earliest:
        months_of_history = min(last_complete - earliest + 1, episodic_months)
    else:
        months_of_history = 0

    window = _window(earliest, last_complete, window_months)
    episodic_window = _window(earliest, last_complete, episodic_months)

    period_end = _month_bounds(last_complete)[1]
    period_start = _month_bounds(
        window[0] if window is not None else last_complete - window_months + 1
    )[0]

    recurring_burn: Decimal | None = None
    essential_monthly: Decimal | None = None
    discretionary_monthly: Decimal | None = None
    savings_flow: Decimal | None = None
    if window is not None:
        start, end = _month_bounds(window[0])[0], _month_bounds(window[1])[1]
        keys = [_month_key(index) for index in range(window[0], window[1] + 1)]

        non_episodic = _monthly_category_totals(ledger, start, end, episodic=False, scope=scope)
        if non_episodic:
            recurring_burn = _median(_window_values(non_episodic, keys))

        essential = _monthly_category_totals(
            ledger, start, end, episodic=False, essential=True, scope=scope
        )
        if essential:
            essential_monthly = _median(_window_values(essential, keys))

        discretionary = _monthly_category_totals(
            ledger, start, end, episodic=False, essential=False, scope=scope
        )
        if discretionary:
            discretionary_monthly = _median(_window_values(discretionary, keys))

        savings_sql, savings_params = _account_scope(scope, "a.name")
        savings_flow = _window_total(
            ledger, start, end, _SAVINGS_SQL + savings_sql, savings_params
        )

    episodic_accrual: Decimal | None = None
    if episodic_window is not None:
        start, end = _month_bounds(episodic_window[0])[0], _month_bounds(episodic_window[1])[1]
        one_off = sum(
            _monthly_category_totals(ledger, start, end, episodic=True, scope=scope).values(),
            Decimal(0),
        )
        # Always divided by the nominal window so a short history cannot inflate it.
        episodic_accrual = one_off / episodic_months

    if recurring_burn is not None and episodic_accrual is not None:
        expected_burn: Decimal | None = recurring_burn + episodic_accrual
    elif recurring_burn is not None:
        expected_burn = recurring_burn
    elif episodic_accrual is not None:
        expected_burn = episodic_accrual
    else:
        expected_burn = None

    liquidity_sql, liquidity_params = _account_scope(scope, "name")
    liquidity = sum(
        (
            ledger.balance(row["id"], today)
            for row in ledger.conn.execute(
                "SELECT id FROM accounts WHERE type = 'real'" + liquidity_sql, liquidity_params
            )
        ),
        Decimal(0),
    )

    # The denominator is the expected burn: with no burn estimate there is no
    # denominator, and a non-positive one yields no runway.
    denominator = expected_burn
    runway_months = (
        liquidity / denominator if denominator is not None and denominator > 0 else None
    )

    return Metrics(
        months_of_history=months_of_history,
        partial=months_of_history < window_months,
        recurring_burn=recurring_burn,
        episodic_accrual=episodic_accrual,
        episodic_partial=months_of_history < episodic_months,
        expected_burn=expected_burn,
        liquidity=liquidity,
        runway_months=runway_months,
        essential_monthly=essential_monthly,
        discretionary_monthly=discretionary_monthly,
        savings_flow=savings_flow,
        period_start=period_start,
        period_end=period_end,
        window_months=window_months,
        episodic_months=episodic_months,
    )


# -- dashboard series ------------------------------------------------------
#
# Three readings of the same ledger, one per chart. They are queries, not
# stored numbers, so a chart can never drift from the metrics above it.

_MONTHLY_EXPENSE_SQL = """
    SELECT substr(t.date, 1, 7) AS month, p.amount AS amount
    FROM postings p
    JOIN transactions t ON t.id = p.transaction_id
    JOIN accounts a ON a.id = p.account_id
    WHERE a.type = 'category' AND t.status = 'BOOK'
      AND CAST(t.amount AS REAL) < 0
      AND t.date >= ? AND t.date <= ?
"""

_MONTHLY_INCOME_SQL = """
    SELECT substr(t.date, 1, 7) AS month, t.amount AS amount
    FROM transactions t
    JOIN accounts a ON a.id = t.account_id
    WHERE a.type = 'real' AND t.status = 'BOOK'
      AND CAST(t.amount AS REAL) > 0
      AND t.date >= ? AND t.date <= ?
      AND NOT EXISTS (
          SELECT 1 FROM postings p JOIN accounts v ON v.id = p.account_id
          WHERE p.transaction_id = t.id AND v.type = 'virtual'
      )
"""


@dataclass(frozen=True)
class CategorySpend:
    """One slice of a month: a category and what it took, as a positive amount."""

    category: str
    amount: Decimal


@dataclass(frozen=True)
class MonthlyFlow:
    """One month of the income/expense chart.

    ``partial`` marks the month still in progress, which reads as low spending
    only because it has not finished.
    """

    month: str
    income: Decimal
    expenses: Decimal
    partial: bool


@dataclass(frozen=True)
class NetWorthPoint:
    """Total tracked money on a date the bank reported balances."""

    date: dt.date
    total: Decimal


@dataclass(frozen=True)
class AccountBalance:
    """The most recent reported balance of one tracked account."""

    account: str
    date: dt.date
    balance: Decimal


def _first_month_with_data(ledger: Ledger) -> int | None:
    """The month of the oldest settled row, or ``None`` on an empty ledger."""
    row = ledger.conn.execute(
        "SELECT MIN(date) AS first FROM transactions WHERE status = 'BOOK'"
    ).fetchone()
    return _month_index(dt.date.fromisoformat(row["first"])) if row["first"] else None


def spend_by_category(
    ledger: Ledger, start: dt.date, end: dt.date, scope: LedgerScope = LedgerScope()
) -> list[CategorySpend]:
    """What each category took in the period, largest first.

    Uncategorized money is a slice like any other: leaving it out would make the
    chart add up to less than what actually left the accounts.
    """
    totals: dict[str, Decimal] = {}
    scoped, extra = _spending_scope(scope)
    for row in ledger.conn.execute(
        """SELECT a.name AS category, p.amount AS amount
           FROM postings p
           JOIN transactions t ON t.id = p.transaction_id
           JOIN accounts a ON a.id = p.account_id
           WHERE a.type = 'category' AND t.status = 'BOOK'
             AND CAST(t.amount AS REAL) < 0
             AND t.date >= ? AND t.date <= ?"""
        + scoped,
        (start.isoformat(), end.isoformat(), *extra),
    ):
        category = row["category"]
        totals[category] = totals.get(category, Decimal(0)) + parse_decimal(row["amount"])
    return [
        CategorySpend(category=category, amount=amount)
        for category, amount in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        if amount != 0
    ]


def monthly_flows(
    ledger: Ledger, start: dt.date, end: dt.date, scope: LedgerScope = LedgerScope()
) -> list[MonthlyFlow]:
    """Income and spending per month in the period, oldest first.

    Expenses are the same category postings the burn is computed from, so this
    chart cannot disagree with the metrics above it. Income is money that
    entered a real account, with the legs of any transfer left out — a pair
    between tracked accounts, or a leg to an own account that is not connected;
    moving your own money is not income. Category names narrow the expenses
    alone: a category does not describe the money coming in.

    The period is clipped to the months the ledger covers and to the present —
    a chart cannot show a month that has not happened — so a young ledger does
    not chart half a year of nothing. Empty months inside the period stay, so a
    flat month reads as a flat month.
    """
    last = min(_month_index(end), _month_index(dt.date.today()))
    earliest = _first_month_with_data(ledger)
    # An empty ledger charts the month in progress; a ledger with data charts
    # from its own first month. Either way the period cannot invent a past.
    first = last if earliest is None else max(_month_index(start), earliest)
    if first > last:
        return []
    keys = [_month_key(index) for index in range(first, last + 1)]
    bounds = (_month_bounds(first)[0], _month_bounds(last)[1])

    scoped, extra = _spending_scope(scope)
    account_scoped, account_params = _account_scope(scope, "a.name")

    expenses: dict[str, Decimal] = {}
    for row in ledger.conn.execute(
        _MONTHLY_EXPENSE_SQL + scoped, (bounds[0].isoformat(), bounds[1].isoformat(), *extra)
    ):
        expenses[row["month"]] = expenses.get(row["month"], Decimal(0)) + parse_decimal(row["amount"])

    income: dict[str, Decimal] = {}
    for row in ledger.conn.execute(
        _MONTHLY_INCOME_SQL + account_scoped,
        (bounds[0].isoformat(), bounds[1].isoformat(), *account_params),
    ):
        income[row["month"]] = income.get(row["month"], Decimal(0)) + parse_decimal(row["amount"])

    current = _month_key(_month_index(dt.date.today()))
    return [
        MonthlyFlow(
            month=key,
            income=income.get(key, Decimal(0)),
            expenses=expenses.get(key, Decimal(0)),
            partial=key == current,
        )
        for key in keys
    ]


def net_worth_series(
    ledger: Ledger,
    start: dt.date | None = None,
    end: dt.date | None = None,
    scope: LedgerScope = LedgerScope(),
) -> list[NetWorthPoint]:
    """Tracked money at each date a balance was reported, oldest first.

    Every point is an observation, never a reconstruction, and an account counts
    only from the first date the bank reported a balance for it: the line starts
    where the data starts instead of pretending to know the past. A period cuts
    the points it shows, never the running total: an observation before
    ``start`` still decides what the first point inside the period is worth.
    """
    known: dict[int, Decimal] = {}
    totals: dict[str, Decimal] = {}
    scoped, extra = _account_scope(scope, "a.name")
    for row in ledger.conn.execute(
        """SELECT ab.date AS date, ab.account_id AS account_id, ab.balance AS balance
           FROM account_balances ab
           JOIN accounts a ON a.id = ab.account_id
           WHERE a.type = 'real'"""
        + scoped
        + " ORDER BY ab.date, ab.account_id",
        extra,
    ):
        known[row["account_id"]] = parse_decimal(row["balance"])
        totals[row["date"]] = sum(known.values(), Decimal(0))
    return [
        NetWorthPoint(date=dt.date.fromisoformat(day), total=total)
        for day, total in sorted(totals.items())
        if (start is None or day >= start.isoformat()) and (end is None or day <= end.isoformat())
    ]


def latest_balances(ledger: Ledger, scope: LedgerScope = LedgerScope()) -> list[AccountBalance]:
    """The most recent reported balance of every tracked account."""
    balances = []
    scoped, extra = _account_scope(scope, "name")
    for account in ledger.conn.execute(
        "SELECT id, name FROM accounts WHERE type = 'real'" + scoped + " ORDER BY name", extra
    ):
        row = ledger.conn.execute(
            """SELECT date, balance FROM account_balances
               WHERE account_id = ? ORDER BY date DESC LIMIT 1""",
            (account["id"],),
        ).fetchone()
        if row is not None:
            balances.append(
                AccountBalance(
                    account=account["name"],
                    date=dt.date.fromisoformat(row["date"]),
                    balance=parse_decimal(row["balance"]),
                )
            )
    return balances
