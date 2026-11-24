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
from decimal import Decimal


KINDS = ("lezione", "seduta", "altro")
DIRECTIONS = ("entrata", "uscita")
VALID, CANCELLED = "valida", "annullata"

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
    """Exact text, case and spaces aside, or `/an expression/` searched in the title.

    The slashes are the rules' convention (`merchants.rule_pattern`). Exact rather
    than contained, unlike a rule on a description: "Lezione Tennis"
    must not take "Lezione Tennis annullata" as a session.
    """
    typed = pattern.strip()
    if len(typed) > 2 and typed.startswith("/") and typed.endswith("/"):
        return re.search(typed[1:-1], summary, re.IGNORECASE) is not None
    return _text_key(summary) == _text_key(typed)


def session_day(start: str) -> dt.date:
    """The local day of a session: the calendar's text begins with it."""
    return dt.date.fromisoformat(start[:10])


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


def normalize_iban(iban: str | None) -> str | None:
    """An IBAN as the banks print it differently: no spaces, upper case."""
    if not iban:
        return None
    cleaned = re.sub(r"\s+", "", iban).upper()
    return cleaned or None
