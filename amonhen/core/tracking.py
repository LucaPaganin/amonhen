"""Desiderata 5.17, pure: which event is a session, and which sessions the payments cover.

The balance is the conserved quantity: sessions due minus payments linked. Which
sessions are paid is not stored anywhere — the payments cover the sessions in
date order, the oldest first — so correcting an amount, cancelling a session or
linking a payment can never leave a written coverage behind.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


KINDS = ("lezione", "seduta", "altro")
DIRECTIONS = ("entrata", "uscita")
VALID, CANCELLED = "valida", "annullata"

# How a service's price becomes a session's amount: the price once, or the price
# for every hour the event lasts.
BILLING = ("sessione", "ora")
BILLING_HOURS = "ora"

CENT = Decimal("0.01")
HOUR = Decimal("0.01")

PAID, PARTIAL, DUE, FUTURE = "pagata", "parziale", "da_pagare", "futura"

ZERO = Decimal(0)


@dataclass(frozen=True)
class Session:
    event_id: str
    start: str
    amount: Decimal


@dataclass(frozen=True)
class CoveredSession:
    event_id: str
    start: str
    amount: Decimal
    covered: Decimal
    state: str


@dataclass(frozen=True)
class Coverage:
    due: Decimal  # the valid sessions up to today
    paid: Decimal  # the payments linked, as a size
    balance: Decimal  # due - paid: positive is still owed, negative is paid ahead
    sessions: list[CoveredSession]


def title_matches(pattern: str, summary: str) -> bool:
    """The title carries the pattern, case and spaces aside, or `/an expression/` in it.

    Contained rather than equal: a calendar entry that gains a name ("Ripetizioni
    Andrea" for a series typed as "Ripetizioni") is still the same session, and
    losing a whole series to a renamed title is a silent, invisible failure. A
    cancelled event is excluded by its status, not by its wording.

    The slashes are the rules' convention (`merchants.rule_pattern`).
    """
    typed = pattern.strip()
    if len(typed) > 2 and typed.startswith("/") and typed.endswith("/"):
        return re.search(typed[1:-1], summary, re.IGNORECASE) is not None
    wanted = _text_key(typed)
    return bool(wanted) and wanted in _text_key(summary)


def session_day(start: str) -> dt.date:
    """The local day of a session: the calendar's text begins with it."""
    return dt.date.fromisoformat(start[:10])


def event_hours(start: str, end: str) -> Decimal | None:
    """How long the event lasts, in hours; None when the calendar gave no length.

    An all-day event carries two dates and no times: its length is not a length
    anybody is paid for, so it is unknown rather than twenty-four.
    """
    if len(start) <= 10 or len(end) <= 10:
        return None
    try:
        first, last = dt.datetime.fromisoformat(start), dt.datetime.fromisoformat(end)
    except ValueError:
        return None
    seconds = Decimal(int((last - first).total_seconds()))
    if seconds <= 0:
        return None
    return (seconds / Decimal(3600)).quantize(HOUR, rounding=ROUND_HALF_UP)


def session_amount(rate: Decimal, hours: Decimal | None, billing: str, default_hours: Decimal) -> Decimal:
    """What one session costs: the price, or the price for each hour it lasts.

    An hourly service whose event has no length bills ``default_hours``: a
    session that costs nothing would be a silent hole in the balance.
    """
    if billing != BILLING_HOURS:
        return rate
    billed = hours if hours is not None and hours > 0 else default_hours
    return (rate * billed).quantize(CENT, rounding=ROUND_HALF_UP)


def coverage(sessions: list[Session], paid: Decimal, today: dt.date) -> Coverage:
    """The payments spread over the valid sessions, the oldest first.

    ``sessions`` are the valid ones; a session after ``today`` is not due yet, so
    it neither counts in the balance nor takes a payment.
    """
    ordered = sorted(sessions, key=lambda session: (session.start, session.event_id))
    due = sum((s.amount for s in ordered if session_day(s.start) <= today), ZERO)
    left = paid
    lines: list[CoveredSession] = []
    for session in ordered:
        if session_day(session.start) > today:
            lines.append(CoveredSession(session.event_id, session.start, session.amount, ZERO, FUTURE))
            continue
        covered = min(session.amount, max(left, ZERO))
        left -= covered
        if covered == session.amount:
            state = PAID
        elif covered > 0:
            state = PARTIAL
        else:
            state = DUE
        lines.append(CoveredSession(session.event_id, session.start, session.amount, covered, state))
    return Coverage(due=due, paid=paid, balance=due - paid, sessions=lines)


def _text_key(text: str) -> str:
    """Trimmed, spaces collapsed, lower case: how a rule on a description compares text too."""
    return re.sub(r"\s+", " ", text.strip()).lower()
