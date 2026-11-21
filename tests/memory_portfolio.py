"""The portfolio's three sources in memory, for tests of the use cases alone.

They speak the ports' own types, like `MemoryBank`, and live in the tests on purpose:
production code does not ship its test doubles. Each can fail the way a real source does.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from amonhen.core.portfolio import StatementOperation
from amonhen.ports.portfolio import (
    FetchedDocument,
    ReadStatement,
    BrokerPosition,
    BrokerTrade,
    NavUnavailable,
    PayslipContribution,
    PricePoint,
    SourceUnavailable,
)


@dataclass
class MemoryBroker:
    trades_: list[BrokerTrade] = field(default_factory=list)
    positions_: list[BrokerPosition] = field(default_factory=list)
    prices: dict[str, list[PricePoint]] = field(default_factory=dict)
    down: bool = False

    def trades(self, since):
        if self.down:
            raise SourceUnavailable("il broker non risponde")
        return [t for t in self.trades_ if since is None or t.date >= since]

    def positions(self):
        return list(self.positions_)

    def month_end_prices(self, isin):
        return list(self.prices.get(isin, []))


@dataclass
class MemoryDocuments:
    """Documents already read, by id, each with its kind and its modification stamp."""

    documents: dict[int, tuple[str, str, FetchedDocument]] = field(default_factory=dict)
    reports: list[tuple[int, str, dict]] = field(default_factory=list)
    reads: list[int] = field(default_factory=list)
    down: bool = False

    def add(self, document: FetchedDocument, stamp: str) -> None:
        self.documents[document.source_id] = (document.kind, stamp, document)

    def list_new(self, kind, modified_after):
        if self.down:
            raise SourceUnavailable("Paperless non risponde")
        return sorted(((i, stamp) for i, (k, stamp, _) in self.documents.items()
                       if k == kind and (modified_after is None or stamp > modified_after)), key=lambda x: x[1])

    def read(self, kind, source_id):
        self.reads.append(source_id)
        return self.documents[source_id][2]

    def report(self, source_id, outcome, figures):
        self.reports.append((source_id, outcome, figures))
        # Writing back modifies the document now, as it does on Paperless: later than any cursor.
        kind, stamp, document = self.documents[source_id]
        self.documents[source_id] = (kind, "2099-" + stamp, document)


def documents_from(slips, operations=(), units=None, *, start=100):
    """Payslips and one statement as documents, numbered and stamped in order."""
    source = MemoryDocuments()
    for offset, slip in enumerate(slips):
        source.add(FetchedDocument(start + offset, "busta_paga", "rina", payslip=slip), f"2026-01-{offset + 1:02d}")
    if operations or units is not None:
        source.add(FetchedDocument(start + 99, "prospetto", "generali",
                                   statement=ReadStatement(2025, tuple(operations), units or Decimal(0))), "2026-02-01")
    return source


@dataclass
class MemoryNav:
    values: dict[str, Decimal] = field(default_factory=dict)  # month -> unit value

    def unit_value(self, page, fund_class, month):
        if month not in self.values:
            raise NavUnavailable(f"la pagina non dà il valore di {month}")
        return self.values[month]
