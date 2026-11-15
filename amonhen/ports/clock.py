"""The clock, as a port: what day it is is an input like any other.

The figures that depend on today — the month in progress, a balance as of now,
the budget of the current month, the window a sync asks the bank for — read it
from a `Clock` the API and the command line are handed by whoever builds them,
so a test can stop the clock on a date instead of depending on the day it runs.

Two readings of the clock stay outside on purpose. The ledger's own timestamps
(`created_at`, `deleted_at`, `restored_at`) say when something was written and
decide no figure. The Enable Banking client signs its JWT with the real time,
because the bank checks it.
"""
from __future__ import annotations

import datetime as dt
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def today(self) -> dt.date:
        """The local calendar day."""
        ...

    def now(self) -> dt.datetime:
        """The current instant, in UTC."""
        ...


class SystemClock:
    """The machine's clock."""

    def today(self) -> dt.date:
        return dt.date.today()

    def now(self) -> dt.datetime:
        return dt.datetime.now(dt.UTC)
