"""The portfolio's sources as the use cases see them: the broker, the documents, the fund's NAV.

Three real things that change and must be faked in a test, each behind a small protocol
that speaks AmonHen's own types and errors, never the provider's — the lesson of
`ports.bank`. The parser is not one of them: it is a pure library the document adapter
calls, and none of its types crosses this line (docs/investments.md).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from amonhen.core.portfolio import StatementOperation


class SourceError(Exception):
    """A source did not return what was asked; the message is the source's own words."""


class SourceUnavailable(SourceError):
    """The source could not be reached or refused."""


class NavUnavailable(SourceError):
    """The fund's unit value for a month could not be read: the app asks for it by hand,
    and never reuses another month's."""


@dataclass(frozen=True)
class BrokerTrade:
    isin: str
    date: dt.date
    units: Decimal
    price: Decimal
    amount: Decimal
    fees: Decimal
    reference: str


@dataclass(frozen=True)
class BrokerPosition:
    isin: str
    units: Decimal


@dataclass(frozen=True)
class PricePoint:
    isin: str
    date: dt.date
    value: Decimal


@dataclass(frozen=True)
class PayslipContribution:
    """What a payslip withheld for the fund: own, the employer's, the TFR."""

    reference: str
    period: str  # YYYY-MM
    own: Decimal
    employer: Decimal
    tfr: Decimal


@runtime_checkable
class BrokerSource(Protocol):
    """Read-only: positions, trades and month-end closes. Nothing that prepares an order."""

    def trades(self, since: dt.date | None) -> list[BrokerTrade]: ...

    def positions(self) -> list[BrokerPosition]: ...

    def month_end_prices(self, isin: str) -> list[PricePoint]: ...


@runtime_checkable
class DocumentSource(Protocol):
    def payslips(self, since: dt.date | None) -> list[PayslipContribution]: ...

    def statement_operations(self, since: dt.date | None) -> list[StatementOperation]: ...

    def statement_units(self) -> Decimal | None:
        """The units the latest statement says the fund holds."""


@runtime_checkable
class NavSource(Protocol):
    def unit_value(self, fund_class: str, month: str) -> Decimal:
        """The fund's unit value for a month; raises `NavUnavailable` when it cannot be read."""
