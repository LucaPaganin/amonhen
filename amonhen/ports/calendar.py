"""The calendar, as a port: where the sessions of a service are written (desiderata 5.17).

The tracking asks one thing of a calendar: what changed since the last time it
asked, with a token that remembers where that was. A first request carries no
token and gets everything. That is the shape of Google Calendar's incremental
sync, and it is what makes reading twice give the same ledger.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CalendarWindow:
    """The days a read covers, both ends included.

    The window belongs to the contract, not to one adapter: it decides which
    sessions can exist, and Google binds a sync token to the request that
    produced it, so a different window is a different question and needs a
    full read.
    """

    start: dt.date
    end: dt.date

    def key(self) -> str:
        return f"{self.start.isoformat()}|{self.end.isoformat()}"


@dataclass(frozen=True)
class CalendarEvent:
    """One event as the calendar reported it.

    `start` is the ISO text the calendar gave (a day, or an instant with its
    offset), so its first ten characters are the local day. A cancelled event
    may arrive with neither summary nor start: only its id is certain.
    """

    event_id: str
    summary: str
    start: str
    cancelled: bool


@dataclass(frozen=True)
class CalendarChanges:
    events: list[CalendarEvent]
    next_sync_token: str


class CalendarError(Exception):
    """The calendar did not answer; the tracking keeps what it had."""


class SyncTokenExpired(CalendarError):
    """The token is too old for the calendar: read everything again."""


class CalendarSource(Protocol):
    def changes(self, calendar_id: str, sync_token: str | None, window: CalendarWindow) -> CalendarChanges:
        """Every event since ``sync_token`` within ``window``, or every one when it is None."""
        ...
