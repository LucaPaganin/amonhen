"""TWR and MWR (desiderata 5.16): two rates that answer two questions.

The TWR measures the instrument: the growth between one flow and the next, whatever was
paid in and when. The MWR measures the person: the one constant rate that makes the
flows, discounted, add up to nothing, so it depends on when the money went in.
Pure: dates and amounts in, a rate out.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal


def twr(periods: list[tuple[Decimal, Decimal]]) -> Decimal | None:
    """Chained growth: each period is its value after the previous flow and before the next.

    The value before a flow is taken at the price of the transaction that makes it, so no
    price history is needed beyond the month ends. Returns the total return as a fraction
    (0.32 is 32%), or None when there is nothing to chain.
    """
    factor = Decimal(1)
    seen = False
    for start, end in periods:
        if start <= 0:
            continue  # nothing was held: there is no growth to measure
        factor *= end / start
        seen = True
    return factor - 1 if seen else None


def mwr(flows: list[tuple[dt.date, Decimal]], *, tolerance: float = 1e-9) -> float | None:
    """The yearly rate that makes ``sum(flow * (1 + r) ** -years)`` zero, or None without a root.

    Money paid in is negative and what comes back — the final value counts as a flow —
    positive. A bracketed bisection, not Newton alone: flows that change sign more than
    once can give two roots, and a bracket never leaves the interval it started in.
    """
    if len(flows) < 2 or all(amount >= 0 for _, amount in flows) or all(amount <= 0 for _, amount in flows):
        return None
    origin = min(day for day, _ in flows)
    dated = [((day - origin).days / 365, float(amount)) for day, amount in flows]

    def present(rate: float) -> float:
        return sum(amount * (1 + rate) ** -years for years, amount in dated)

    low, high = -0.999999, 1.0
    while present(high) * present(low) > 0:
        high *= 2
        if high > 1e6:
            return None
    for _ in range(300):
        middle = (low + high) / 2
        if present(low) * present(middle) <= 0:
            high = middle
        else:
            low = middle
        if high - low < tolerance:
            break
    return (low + high) / 2
