"""Projections by scenario (desiderata 5.16): W(t+1) = W(t)·(1 + r) + c, in today's euros.

Pure, like `core.planning`: rates arrive as percent texts, money as Decimals. The
return is real, so every result is in today's euros; the inflation a scenario
carries is shown beside it and turns the goal into the euros of its date, nothing more.
These are arithmetic on assumptions a person wrote, not forecasts (section 3).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from amonhen.models import parse_decimal

# The three scenarios, in the order they are read. Their numbers are written by hand.
SCENARIOS = ("prudente", "centrale", "favorevole")

CENT = Decimal("0.01")


def checked_rate(text: str) -> str:
    """A yearly rate in percent as it is stored, or ValueError: it may be below zero, never -100 or less."""
    value = parse_decimal(text.strip())
    if not value.is_finite() or not Decimal(-100) < value <= 100:
        raise ValueError(f"{text}: un tasso annuo, sopra -100 e fino a 100")
    return str(value)


def monthly_rate(annual_percent: Decimal) -> Decimal:
    """The monthly rate that compounds to the yearly one."""
    return (1 + annual_percent / 100) ** (Decimal(1) / 12) - 1


def growth(annual_percent: Decimal, months: int) -> Decimal:
    return (1 + monthly_rate(annual_percent)) ** months


def value_at(start: Decimal, monthly: Decimal, annual_percent: Decimal, months: int) -> Decimal:
    """What ``start`` and ``monthly`` paid in at each month's end are worth after ``months``."""
    g, rate = growth(annual_percent, months), monthly_rate(annual_percent)
    return start * g + (monthly * months if rate == 0 else monthly * (g - 1) / rate)


def needed_monthly(goal: Decimal, start: Decimal, annual_percent: Decimal, months: int) -> Decimal:
    """The monthly payment that reaches ``goal``: zero when ``start`` alone gets there."""
    g, rate = growth(annual_percent, months), monthly_rate(annual_percent)
    missing = goal - start * g
    if missing <= 0:
        return Decimal(0)
    return missing / months if rate == 0 else missing * rate / (g - 1)


def coast_fi(goal: Decimal, annual_percent: Decimal, months: int) -> Decimal:
    """The capital that grows to ``goal`` by itself, with no payment from now on."""
    return goal / growth(annual_percent, months)


@dataclass(frozen=True)
class Projection:
    """One goal under one scenario."""

    value: Decimal           # at the goal's date, today's euros
    reaches: bool
    shortfall: Decimal       # what is missing at the date, zero when it reaches
    needed_monthly: Decimal  # the monthly payment that would reach it
    goal_nominal: Decimal    # the goal in the euros of its date, at the scenario's inflation


def project(
    goal: Decimal, start: Decimal, monthly: Decimal, real_return: Decimal, inflation: Decimal, months: int
) -> Projection:
    if months < 1:
        raise ValueError("la data dell'obiettivo è già passata")
    value = value_at(start, monthly, real_return, months)
    return Projection(
        value=value.quantize(CENT),
        reaches=value >= goal,
        shortfall=max(Decimal(0), goal - value).quantize(CENT),
        needed_monthly=needed_monthly(goal, start, real_return, months).quantize(CENT),
        goal_nominal=(goal * (1 + inflation / 100) ** (Decimal(months) / 12)).quantize(CENT),
    )
