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
from amonhen.ledger.tracking import sync_token_key, synced_at
from amonhen.models import format_decimal, parse_decimal
from amonhen.ports.calendar import CalendarChanges, CalendarError, CalendarSource, SyncTokenExpired

log = logging.getLogger(__name__)


@dataclass
class CalendarOutcome:
    calendar_id: str
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


def sync_calendars(ledger: Ledger, source: CalendarSource, now: dt.datetime) -> CalendarSyncResult:
    """Read what changed in every calendar of an active service, then link payments.

    A token Google no longer accepts means one full read: the sessions of that
    calendar it does not list any more were deleted meanwhile, and are cancelled.
    """
    result = CalendarSyncResult()
    services = ledger.services(active_only=True)
    for calendar_id in sorted({service["calendar_id"] for service in services}):
        outcome = CalendarOutcome(calendar_id)
        result.calendars.append(outcome)
        token = ledger.setting(sync_token_key(calendar_id))
        try:
            try:
                changes = source.changes(calendar_id, token)
            except SyncTokenExpired:
                log.info("calendar %s: sync token expired, reading everything", calendar_id)
                token = None
                changes = source.changes(calendar_id, None)
        except CalendarError as exc:
            log.warning("calendar %s not read: %s", calendar_id, exc)
            outcome.error = str(exc)
            continue
        calendar_services = [s for s in services if s["calendar_id"] == calendar_id]
        _apply(ledger, calendar_services, changes, full=token is None, now=now, outcome=outcome)
        ledger.set_setting(sync_token_key(calendar_id), changes.next_sync_token)
        log.info(
            "calendar %s: %d sessions written, %d cancelled",
            calendar_id, outcome.written, outcome.cancelled,
        )
    result.payments_linked = ledger.link_payments_by_iban()
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
         "by_iban": bool(row["by_iban"])}
        for row in ledger.payments_of(service_id)
    ]
    return {
        **_summary(ledger, service, today, covered),
        "sessions": sessions,
        "cancelled": cancelled,
        "payments": payments,
    }


# -- private helpers ---------------------------------------------------------------

def _apply(ledger, services, changes: CalendarChanges, *, full: bool, now: dt.datetime, outcome) -> None:
    stamp = synced_at(now)
    seen: set[str] = set()
    with ledger.conn:
        for event in changes.events:
            seen.add(event.event_id)
            match = None if event.cancelled else _service_for(services, event.summary)
            if match is None:
                # Cancelled, or renamed out of every service: no longer a session.
                if ledger.cancel_session(event.event_id, stamp):
                    outcome.cancelled += 1
                continue
            ledger.write_session(event.event_id, match["id"], event.start, event.summary, stamp)
            outcome.written += 1
        if full:
            ids = [service["id"] for service in services]
            for row in ledger.conn.execute(
                f"""SELECT event_id FROM service_sessions
                    WHERE status = ? AND service_id IN ({', '.join('?' * len(ids))})""",
                (VALID, *ids),
            ).fetchall():
                if row["event_id"] not in seen and ledger.cancel_session(row["event_id"], stamp):
                    outcome.cancelled += 1


def _service_for(services, summary: str):
    """The first service, by id, whose title the event carries."""
    for service in sorted(services, key=lambda s: s["id"]):
        if title_matches(service["title_pattern"], summary):
            return service
    return None


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
        "counterparty_iban": service["counterparty_iban"],
        "active": bool(service["active"]),
        "due": format_decimal(covered.due),
        "paid": format_decimal(covered.paid),
        "balance": format_decimal(covered.balance),
        "sessions_due": len(due_sessions),
        "sessions_unpaid": sum(1 for line in due_sessions if line.state != "pagata"),
    }
