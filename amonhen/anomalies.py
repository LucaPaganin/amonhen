"""Desiderata 5.7: deterministic, explainable spending anomalies.

A category's settled outflows are its history. Recent movements are scored
against that history with a robust z-score on the median absolute deviation;
when the category is perfectly regular (MAD zero) the detector falls back to
the historical 95th percentile, so a constant category still reports a
genuinely large movement. Every flag carries the numbers it was computed from
and one sentence, and the whole path is plain Decimal arithmetic on the
ledger: no model, no randomness.
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from amonhen.ledger import Ledger
from amonhen.merchants import merchant_name
from amonhen.models import format_decimal, parse_decimal
from amonhen.settings import UNCATEGORIZED

__all__ = ["Anomaly", "detect_anomalies"]

# By default only the last month of spending is reviewed; the rest of the
# lookback is the history a movement is compared against.
DEFAULT_RECENT_DAYS = 31
# Scaling constant that puts a MAD-based score on the standard-deviation scale.
_ROBUST_Z_FACTOR = Decimal("0.6745")

# An outflow is a negative transaction amount, exactly like Ledger.spend_between:
# incoming money carries a negative category posting and is not spending. The
# posting amount is the category leg's share, and its magnitude is the spend.
_HISTORY_SQL = """
    SELECT t.id AS transaction_id, t.date AS date, t.description AS description,
           a.name AS category, p.amount AS posting_amount
    FROM postings p
    JOIN transactions t ON t.id = p.transaction_id
    JOIN accounts a ON a.id = p.account_id
    WHERE a.type = 'category' AND t.status = 'BOOK' AND a.name != ?
      AND CAST(t.amount AS REAL) < 0
      AND t.date >= ? AND t.date < ?
    ORDER BY t.date, t.id, a.name
"""

_RECENT_SQL = """
    SELECT t.id AS transaction_id, t.date AS date, t.description AS description,
           a.name AS category, p.amount AS posting_amount
    FROM postings p
    JOIN transactions t ON t.id = p.transaction_id
    JOIN accounts a ON a.id = p.account_id
    WHERE a.type = 'category' AND t.status = 'BOOK' AND a.name != ?
      AND CAST(t.amount AS REAL) < 0
      AND t.date >= ? AND t.date <= ?
    ORDER BY t.date, t.id, a.name
"""


@dataclass(frozen=True)
class Anomaly:
    """One flagged movement, with the history numbers behind the flag."""

    transaction_id: int
    date: dt.date
    merchant: str
    category: str
    amount: Decimal
    median: Decimal
    mad: Decimal
    score: Decimal
    method: Literal["mad", "p95"]
    sentence: str


@dataclass(frozen=True)
class _Spend:
    """A recent category outflow, before it is judged against the history."""

    transaction_id: int
    date: dt.date
    description: str
    amount: Decimal


def detect_anomalies(
    ledger: Ledger,
    as_of: dt.date,
    lookback_months: int = 12,
    min_samples: int = 8,
    z_threshold: Decimal = Decimal("3.5"),
    recent_days: int = DEFAULT_RECENT_DAYS,
) -> list[Anomaly]:
    """Flag recent category movements that do not fit the category history.

    The last ``recent_days`` days are the review window; everything settled in
    the lookback before it is the history a movement is judged against, so a
    movement never props up the baseline it is compared to. A category needs
    ``min_samples`` history values before it is judged at all; a thin category
    produces no verdict rather than a noisy one. The ``Uncategorized`` sentinel
    is not a category: scoring it would compare unrelated merchants and income
    against each other.
    """
    if lookback_months < 1 or min_samples < 1 or recent_days < 1:
        raise ValueError("lookback_months, min_samples and recent_days must be positive")
    threshold = parse_decimal(z_threshold)

    window_start = as_of - dt.timedelta(days=recent_days)
    history = _history_by_category(ledger, _months_before(as_of, lookback_months), window_start)
    recent = _recent_by_category(ledger, window_start, as_of)

    anomalies: list[Anomaly] = []
    for category, values in history.items():
        if len(values) < min_samples:
            continue
        median = _median(values)
        mad = _median([abs(value - median) for value in values])
        if mad > 0:
            anomalies.extend(_flag_mad(recent.get(category, ()), category, median, mad, threshold))
        else:
            anomalies.extend(_flag_p95(recent.get(category, ()), category, median, values))
    anomalies.sort(key=lambda anomaly: (anomaly.date, anomaly.transaction_id, anomaly.category))
    return anomalies


def _flag_mad(
    spends: Iterable[_Spend],
    category: str,
    median: Decimal,
    mad: Decimal,
    threshold: Decimal,
) -> Iterator[Anomaly]:
    """A spread category: flag what is far from the median in MAD units."""
    for spend in spends:
        score = _ROBUST_Z_FACTOR * (spend.amount - median) / mad
        if score > threshold:
            detail = (
                f"z-score robusto {format_decimal(score)} oltre la soglia "
                f"{format_decimal(threshold)}"
            )
            yield _anomaly(spend, category, median, mad, score, "mad", detail)


def _flag_p95(
    spends: Iterable[_Spend],
    category: str,
    median: Decimal,
    values: list[Decimal],
) -> Iterator[Anomaly]:
    """A constant category (MAD zero): flag what breaks its own p95.

    The movement must also be at least twice the median, so a one-cent wobble
    around a small constant never reads as an anomaly.
    """
    p95 = _percentile_95(values)
    for spend in spends:
        if spend.amount > p95 and spend.amount >= 2 * median:
            detail = f"oltre la soglia p95 {format_decimal(p95)}"
            yield _anomaly(spend, category, median, Decimal(0), spend.amount - p95, "p95", detail)


def _anomaly(
    spend: _Spend,
    category: str,
    median: Decimal,
    mad: Decimal,
    score: Decimal,
    method: Literal["mad", "p95"],
    detail: str,
) -> Anomaly:
    merchant = merchant_name(spend.description)
    sentence = (
        f"Spesa di {format_decimal(spend.amount)} da {merchant} in {category}: "
        f"mediana {format_decimal(median)}, {detail}."
    )
    return Anomaly(
        transaction_id=spend.transaction_id,
        date=spend.date,
        merchant=merchant,
        category=category,
        amount=spend.amount,
        median=median,
        mad=mad,
        score=score,
        method=method,
        sentence=sentence,
    )


# -- ledger queries --------------------------------------------------------

def _history_by_category(ledger: Ledger, cutoff: dt.date, end: dt.date) -> dict[str, list[Decimal]]:
    history: dict[str, list[Decimal]] = {}
    for row in ledger.conn.execute(
        _HISTORY_SQL, (UNCATEGORIZED, cutoff.isoformat(), end.isoformat())
    ):
        history.setdefault(row["category"], []).append(abs(parse_decimal(row["posting_amount"])))
    return history


def _recent_by_category(ledger: Ledger, window_start: dt.date, as_of: dt.date) -> dict[str, list[_Spend]]:
    recent: dict[str, list[_Spend]] = {}
    for row in ledger.conn.execute(
        _RECENT_SQL, (UNCATEGORIZED, window_start.isoformat(), as_of.isoformat())
    ):
        spend = _Spend(
            transaction_id=row["transaction_id"],
            date=dt.date.fromisoformat(row["date"]),
            description=row["description"],
            amount=abs(parse_decimal(row["posting_amount"])),
        )
        recent.setdefault(row["category"], []).append(spend)
    return recent


# -- arithmetic ------------------------------------------------------------

def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _percentile_95(values: list[Decimal]) -> Decimal:
    """Nearest-rank 95th percentile: the value at rank ceil(0.95 * n)."""
    ordered = sorted(values)
    rank = (95 * len(ordered) + 99) // 100
    return ordered[rank - 1]


def _months_before(day: dt.date, months: int) -> dt.date:
    """``day`` shifted back by whole months, clamped to the target month's end."""
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day.day, last_day))
