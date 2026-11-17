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
    slips: list[PayslipContribution] = field(default_factory=list)
    operations: list[StatementOperation] = field(default_factory=list)
    units: Decimal | None = None

    def payslips(self, since):
        return list(self.slips)

    def statement_operations(self, since):
        return list(self.operations)

    def statement_units(self):
        return self.units


@dataclass
class MemoryNav:
    values: dict[str, Decimal] = field(default_factory=dict)  # month -> unit value

    def unit_value(self, fund_class, month):
        if month not in self.values:
            raise NavUnavailable(f"la pagina non dà il valore di {month}")
        return self.values[month]
