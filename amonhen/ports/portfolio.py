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


# What a document is about, as AmonHen names it: the source maps each kind to its own
# document type (Paperless's "Busta paga", for instance).
DOCUMENT_KINDS = ("busta_paga", "prospetto")
IMPORTED, FAILED = "importato", "errore"


@dataclass(frozen=True)
class ReadStatement:
    """What a fund's annual statement says: its contribution operations and the closing units."""

    year: int
    operations: tuple[StatementOperation, ...]
    units_end: Decimal


@dataclass(frozen=True)
class FetchedDocument:
    """One document a source holds, already read: what it says, or why it could not be read.

    Exactly one of ``payslip``, ``statement`` and ``error`` is set.
    """

    source_id: int
    kind: str
    layout: str | None = None
    payslip: PayslipContribution | None = None
    statement: ReadStatement | None = None
    error: str | None = None


@runtime_checkable
class DocumentSource(Protocol):
    """Where the documents come from (Paperless), read and written back by id."""

    def list_new(self, kind: str, modified_after: str | None) -> list[tuple[int, str]]:
        """The ids of the documents of ``kind`` modified after the cursor, with their own
        modification stamp, oldest first. The stamp is the source's text, kept as it is."""

    def read(self, kind: str, source_id: int) -> FetchedDocument:
        """Download the original and read it. A document that cannot be read comes back with
        ``error``; only an unreachable source raises."""

    def report(self, source_id: int, outcome: str, figures: dict[str, str]) -> None:
        """Say on the source what became of the document: its outcome and its key figures."""


@runtime_checkable
class NavSource(Protocol):
    def unit_value(self, page: str, fund_class: str, month: str) -> Decimal:
        """The unit value of ``fund_class`` for ``month`` from its public page; raises
        `NavUnavailable` when the page cannot be read, names another class or another month."""
