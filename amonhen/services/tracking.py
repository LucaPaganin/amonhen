"""The tracked services (desiderata 5.17): read the calendars, answer the balances.

The order of the steps lives here: what an event is and how payments cover
sessions is in `core.tracking`, the SQL in `ledger.tracking`, the calendar behind
`ports.calendar`. A calendar that does not answer is reported and the others go
on; nothing here touches a posting.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from amonhen.core.tracking import CANCELLED, VALID, Session, coverage, title_matches
from amonhen.ledger import Ledger
from amonhen.ledger.tracking import sync_token_key, sync_window_key, synced_at
from amonhen.models import format_decimal, parse_decimal
from amonhen.ports.calendar import (
    CalendarChanges,
    CalendarError,
    CalendarSource,
    CalendarWindow,
    SyncTokenExpired,
)

log = logging.getLogger(__name__)


@dataclass
class CalendarOutcome:
    calendar_id: str
    window: CalendarWindow | None = None
    events: int = 0
    written: int = 0
    cancelled: int = 0
    error: str | None = None


@dataclass
class CalendarSyncResult:
    calendars: list[CalendarOutcome] = field(default_factory=list)
    payments_linked: int = 0

    @property
    def errors(self) -> list[str]:
        return [f"{c.calendar_id}: {c.error}" for c in self.calendars if c.error]


def calendar_window(now: dt.datetime, service=None) -> CalendarWindow:
    """Today widened by the days on each side: what a read covers.

    A service may ask for its own days (an annual course is not a weekly lesson);
    without them the ledger's defaults apply, so the old call still means the
    same window for everyone.
    """
    from amonhen import settings

    today = now.date()
    lookback = _service_days(service, "lookback_days", settings.CALENDAR_LOOKBACK_DAYS)
    ahead = _service_days(service, "ahead_days", settings.CALENDAR_AHEAD_DAYS)
    return CalendarWindow(today - dt.timedelta(days=lookback), today + dt.timedelta(days=ahead))


def _service_days(service, column: str, default: int) -> int:
    if service is None:
        return default
    value = service[column] if column in service.keys() else None
    return default if value is None else int(value)


def sync_calendars(
    ledger: Ledger, source: CalendarSource, now: dt.datetime
) -> CalendarSyncResult:
    """Read what changed in every calendar of an active service, then link payments.

    A token Google no longer accepts means one full read: the sessions of that
    calendar it does not list any more were deleted meanwhile, and are cancelled.
    A token is only good for the window it was asked with, so a different window
    is a full read too.
    """
    result = CalendarSyncResult()
    services = ledger.services(active_only=True)
    for calendar_id in sorted({service["calendar_id"] for service in services}):
        calendar_services = [s for s in services if s["calendar_id"] == calendar_id]
        # One read per calendar, so the window is the widest any of its services
        # asks for; each service then keeps only the days of its own.
        window = _widest([calendar_window(now, service) for service in calendar_services])
        outcome = CalendarOutcome(calendar_id, window=window)
        result.calendars.append(outcome)
        token = ledger.setting(sync_token_key(calendar_id))
        if ledger.setting(sync_window_key(calendar_id)) != window.key():
            if token is not None:
                log.info("calendar %s: read window changed, reading everything", calendar_id)
            token = None
        try:
            try:
                changes = source.changes(calendar_id, token, window)
            except SyncTokenExpired:
                log.info("calendar %s: sync token expired, reading everything", calendar_id)
                token = None
                changes = source.changes(calendar_id, None, window)
        except CalendarError as exc:
            log.warning("calendar %s not read: %s", calendar_id, exc)
            outcome.error = str(exc)
            continue
        outcome.events = len(changes.events)
        _apply(ledger, calendar_services, changes, full=token is None, now=now, outcome=outcome)
        ledger.set_setting(sync_token_key(calendar_id), changes.next_sync_token)
        ledger.set_setting(sync_window_key(calendar_id), window.key())
        log.info(
            "calendar %s: %d events read from %s to %s, %d sessions written, %d cancelled",
            calendar_id, outcome.events, window.start, window.end, outcome.written, outcome.cancelled,
        )
    result.payments_linked = ledger.link_payments_by_text()
    return result


def overview(ledger: Ledger, today: dt.date) -> list[dict]:
    """Every service with its balance, the active ones first."""
    return [_summary(ledger, service, today) for service in ledger.services()]


def detail(ledger: Ledger, service_id: int, today: dt.date) -> dict | None:
    """One service: its balance, each session with its coverage, the payments."""
    service = ledger.service(service_id)
    if service is None:
        return None
    rows = ledger.sessions_of(service_id)
    summaries = {row["event_id"]: row["summary"] for row in rows}
    covered = _coverage(ledger, service_id, today, rows)
    sessions = [
        {
            "event_id": line.event_id,
            "start": line.start,
            "summary": summaries[line.event_id],
            "amount": format_decimal(line.amount),
            "covered": format_decimal(line.covered),
            "state": line.state,
        }
        for line in covered.sessions
    ]
    cancelled = [
        {"event_id": row["event_id"], "start": row["start"], "summary": row["summary"],
         "amount": row["amount"], "state": CANCELLED}
        for row in rows if row["status"] == CANCELLED
    ]
    payments = [
        {"transaction_id": row["id"], "date": row["date"], "amount": row["amount"],
         "description": row["description"], "counterparty": row["counterparty"],
         "by_rule": bool(row["by_rule"])}
        for row in ledger.payments_of(service_id)
    ]
    return {
        **_summary(ledger, service, today, covered),
        "sessions": sessions,
        "cancelled": cancelled,
        "payments": payments,
    }


# -- private helpers ---------------------------------------------------------------

def _apply(
    ledger, services, changes: CalendarChanges, *, full: bool, now: dt.datetime, outcome,
) -> None:
    stamp = synced_at(now)
    own = {service["id"]: calendar_window(now, service) for service in services}
    seen: set[str] = set()
    with ledger.conn:
        for event in changes.events:
            seen.add(event.event_id)
            match = None if event.cancelled else _service_for(services, event.summary)
            # The read covers the widest window of the calendar's services; each
            # one keeps the days it asked for, and nothing else is its session.
            if match is not None and not _inside(own[match["id"]], event.start):
                match = None
            if match is None:
                # Cancelled, renamed out of every service, or outside the days
                # that service reads: no longer a session.
                if ledger.cancel_session(event.event_id, stamp):
                    outcome.cancelled += 1
                continue
            ledger.write_session(event.event_id, match["id"], event.start, event.summary, stamp)
            outcome.written += 1
        if full:
            # Only the session days this read could have listed, per service: a
            # session outside its window is not gone, it is out of sight.
            stale = []
            for service in services:
                days = own[service["id"]]
                stale += ledger.conn.execute(
                    """SELECT event_id FROM service_sessions
                       WHERE status = ? AND service_id = ?
                         AND substr(start, 1, 10) BETWEEN ? AND ?""",
                    (VALID, service["id"], days.start.isoformat(), days.end.isoformat()),
                ).fetchall()
            for row in stale:
                if row["event_id"] not in seen and ledger.cancel_session(row["event_id"], stamp):
                    outcome.cancelled += 1


def _service_for(services, summary: str):
    """The first service, by id, whose title the event carries."""
    for service in sorted(services, key=lambda s: s["id"]):
        if title_matches(service["title_pattern"], summary):
            return service
    return None


def _inside(window: CalendarWindow, start: str) -> bool:
    """Whether an event's day falls in the days a service reads."""
    day = start[:10]
    return bool(day) and window.start.isoformat() <= day <= window.end.isoformat()


def _widest(windows: list[CalendarWindow]) -> CalendarWindow:
    """The window covering every service of one calendar: one read, its bounds."""
    return CalendarWindow(min(w.start for w in windows), max(w.end for w in windows))


def _coverage(ledger: Ledger, service_id: int, today: dt.date, rows=None):
    rows = rows if rows is not None else ledger.sessions_of(service_id)
    sessions = [
        Session(row["event_id"], row["start"], parse_decimal(row["amount"]))
        for row in rows if row["status"] == VALID
    ]
    return coverage(sessions, ledger.paid_total(service_id), today)


def _summary(ledger: Ledger, service, today: dt.date, covered=None) -> dict:
    covered = covered or _coverage(ledger, service["id"], today)
    due_sessions = [line for line in covered.sessions if line.state != "futura"]
    return {
        "id": service["id"],
        "name": service["name"],
        "kind": service["kind"],
        "direction": service["direction"],
        "rate": service["rate"],
        "calendar_id": service["calendar_id"],
        "title_pattern": service["title_pattern"],
        "match_text": service["match_text"],
        "lookback_days": service["lookback_days"],
        "ahead_days": service["ahead_days"],
        "active": bool(service["active"]),
        "due": format_decimal(covered.due),
        "paid": format_decimal(covered.paid),
        "balance": format_decimal(covered.balance),
        "sessions_due": len(due_sessions),
        "sessions_unpaid": sum(1 for line in due_sessions if line.state != "pagata"),
    }
