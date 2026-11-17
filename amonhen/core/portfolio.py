"""The portfolio (desiderata 5.16): a BTP's cash flows, a pension contribution's two states,
the reconciliations, the month-end net worth.

Pure, like the rest of `core/`: values in, values out. No database, no source, no date of
its own — the day always arrives as an argument.
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal

from amonhen.models import parse_decimal

KINDS = ("etf", "btp", "fondo_pensione", "immobile")
WITHHELD, INVESTED = "trattenuto", "investito"

CENT = Decimal("0.01")
UNITS = Decimal("0.000001")


def add_months(day: dt.date, months: int) -> dt.date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return dt.date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def month_end(month: str) -> dt.date:
    year, number = (int(part) for part in month.split("-"))
    return dt.date(year, number, calendar.monthrange(year, number)[1])


def month_of(day: dt.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


# -- the BTP: no source, its cash flows follow from what it is ------------------

@dataclass(frozen=True)
class BtpTerms:
    """What a BTP Valore says about itself, written as data, never as constants of the code."""

    nominal: Decimal
    start: dt.date
    rates: tuple[Decimal, ...]  # the gross yearly rate in percent, one per year of its life
    tax: Decimal                # percent withheld on each coupon
    bonus: Decimal              # percent of the nominal, owed only to whoever reaches maturity

    @classmethod
    def from_text(cls, text: str) -> "BtpTerms":
        data = json.loads(text)
        try:
            terms = cls(
                nominal=parse_decimal(data["nominal"]),
                start=dt.date.fromisoformat(data["start"]),
                rates=tuple(parse_decimal(rate) for rate in data["rates"]),
                tax=parse_decimal(data["tax"]),
                bonus=parse_decimal(data["bonus"]),
            )
        except KeyError as exc:
            raise ValueError(f"mancano nei termini del BTP: {exc.args[0]}") from exc
        if terms.nominal <= 0 or not terms.rates:
            raise ValueError("un BTP ha un nominale e almeno un anno di vita")
        return terms

    @property
    def maturity(self) -> dt.date:
        return add_months(self.start, 12 * len(self.rates))


@dataclass(frozen=True)
class Flow:
    date: dt.date
    amount: Decimal
    kind: str  # cedola | premio


def _quarter_net(terms: BtpTerms, quarter: int) -> Decimal:
    """The coupon of quarter ``quarter`` (0-based), net of the tax."""
    gross = terms.nominal * terms.rates[quarter // 4] / 100 / 4
    return gross * (1 - terms.tax / 100)


def coupons(terms: BtpTerms) -> list[Flow]:
    """Every quarterly coupon, net, and the loyalty bonus on the maturity date."""
    flows = [
        Flow(add_months(terms.start, 3 * (quarter + 1)), _quarter_net(terms, quarter).quantize(CENT), "cedola")
        for quarter in range(4 * len(terms.rates))
    ]
    flows.append(Flow(terms.maturity, (terms.nominal * terms.bonus / 100).quantize(CENT), "premio"))
    return flows


def accrued(terms: BtpTerms, on: dt.date) -> Decimal:
    """The part of the running quarter's coupon already earned, net of the tax."""
    if on <= terms.start or on >= terms.maturity:
        return Decimal(0)
    months = (on.year - terms.start.year) * 12 + on.month - terms.start.month
    quarter = months // 3
    last = add_months(terms.start, 3 * quarter)
    if last > on:
        quarter -= 1
        last = add_months(terms.start, 3 * quarter)
    following = add_months(terms.start, 3 * (quarter + 1))
    share = Decimal((on - last).days) / Decimal((following - last).days)
    return _quarter_net(terms, quarter) * share


def btp_value(terms: BtpTerms, on: dt.date) -> Decimal:
    """Nominal plus the accrued coupon: held to maturity, its market price returns to 100.

    The bonus counts on the maturity date only, because it is owed only to whoever gets there.
    """
    if on < terms.start or on > terms.maturity:
        return Decimal(0)
    if on == terms.maturity:
        return terms.nominal + terms.nominal * terms.bonus / 100
    return terms.nominal + accrued(terms, on)


# -- a pension contribution: withheld first, invested later ----------------------

@dataclass(frozen=True)
class Contribution:
    """One line of the fund's money: its total, when it left the payslip, when it was invested."""

    id: int
    total: Decimal
    withheld_on: dt.date | None  # None for a payment made straight to the fund
    invested_on: dt.date | None  # None while it is in transit


@dataclass(frozen=True)
class StatementOperation:
    date: dt.date
    amount: Decimal
    unit_value: Decimal
    units: Decimal
    reference: str


def match_statement(
    withheld: list[Contribution], operations: list[StatementOperation]
) -> tuple[list[tuple[StatementOperation, list[Contribution]]], list[StatementOperation]]:
    """Which payslip contributions each statement operation invested.

    The fund receives the money late and in irregular batches, so one operation covers
    several consecutive payslips. Both lists are read oldest first and an operation matches
    only when the next withheld contributions add up to it exactly; one that does not
    is returned unmatched, and nothing is adjusted to make it fit.
    """
    matched, unmatched, position = [], [], 0
    for operation in sorted(operations, key=lambda op: op.date):
        total, end = Decimal(0), position
        while end < len(withheld) and total < operation.amount:
            total += withheld[end].total
            end += 1
        if end > position and total == operation.amount:
            matched.append((operation, withheld[position:end]))
            position = end
        else:
            unmatched.append(operation)
    return matched, unmatched


def split_units(operation: StatementOperation, shares: list[Decimal]) -> list[Decimal]:
    """An operation's units among the contributions it invested, in proportion, summing exactly."""
    parts = [(operation.units * share / operation.amount).quantize(UNITS) for share in shares[:-1]]
    return [*parts, operation.units - sum(parts, Decimal(0))]


@dataclass(frozen=True)
class FundPosition:
    withheld: Decimal
    invested: Decimal
    in_transit: Decimal


def fund_position(rows: list[Contribution], on: dt.date) -> FundPosition:
    """Withheld = invested + in transit on ``on``, whatever the batches.

    A payslip contribution exists from its withholding date and is either already
    invested or still in transit; a payment made straight to the fund has no transit.
    """
    withheld = invested = Decimal(0)
    for row in rows:
        if row.withheld_on is None or row.withheld_on > on:
            continue
        withheld += row.total
        if row.invested_on is not None and row.invested_on <= on:
            invested += row.total
    return FundPosition(withheld=withheld, invested=invested, in_transit=withheld - invested)


# -- reconciliations report; they never correct --------------------------------------

@dataclass(frozen=True)
class Difference:
    """Two figures that should agree and the gap between them; neither is adjusted."""

    label: str
    expected: Decimal
    actual: Decimal
    unit: str

    @property
    def difference(self) -> Decimal:
        return self.actual - self.expected


@dataclass(frozen=True)
class FlowMatch:
    date: dt.date
    expected: Decimal
    actual: Decimal | None  # None: nothing arrived near the date


def match_flows(
    expected: list[Flow], credits: list[tuple[dt.date, Decimal]], window_days: int = 5
) -> list[FlowMatch]:
    """Each expected flow against the nearest unused credit within ``window_days``."""
    free = sorted(credits)
    matches = []
    for flow in sorted(expected, key=lambda item: item.date):
        near = [credit for credit in free if abs((credit[0] - flow.date).days) <= window_days]
        chosen = min(near, key=lambda credit: abs((credit[0] - flow.date).days), default=None)
        if chosen is not None:
            free.remove(chosen)
        matches.append(FlowMatch(flow.date, flow.amount, None if chosen is None else chosen[1]))
    return matches


# -- the net worth of a month end -----------------------------------------------------

@dataclass(frozen=True)
class NetWorth:
    liquidity: Decimal
    portfolio: Decimal

    @property
    def total(self) -> Decimal:
        return self.liquidity + self.portfolio
