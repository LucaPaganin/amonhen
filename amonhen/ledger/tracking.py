"""Services, their sessions and the movements that pay them (desiderata 5.17).

None of these tables is read by a posting: spending, the balances and the 5.4 check
cannot see a service, and linking a payment writes nothing on the movement.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from decimal import Decimal

from amonhen.core.tracking import BILLING, CANCELLED, DIRECTIONS, KINDS, VALID, session_amount
from amonhen.models import format_decimal, parse_decimal

# A payment moves money the service's way: a credit for a service given, a debit
# for one received.
_PAYMENT_SIGN_SQL = {"entrata": "CAST(t.amount AS REAL) > 0", "uscita": "CAST(t.amount AS REAL) < 0"}


class TrackingMixin:
    """One part of `Ledger`: the tables of the tracked services."""

    # -- services ----------------------------------------------------------

    def services(self, active_only: bool = False) -> list[sqlite3.Row]:
        where = "WHERE active = 1" if active_only else ""
        return self.conn.execute(f"SELECT * FROM services {where} ORDER BY active DESC, name").fetchall()

    def service(self, service_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()

    def save_service(
        self,
        service_id: int | None,
        *,
        name: str,
        kind: str,
        direction: str,
        rate: str,
        calendar_id: str,
        title_pattern: str,
        match_text: str | None,
        billing: str = "sessione",
        default_hours: str = "1.00",
        lookback_days: int | None = None,
        ahead_days: int | None = None,
        active: bool = True,
        recalculate: bool = False,
    ) -> int:
        """Create a service (``service_id`` None) or rewrite one; returns its id.

        A new rate is the price of the sessions that appear from now on: the
        sessions already written keep the amount they had, unless ``recalculate``
        asks for them again — that forgets the calendar's token, so the next read
        re-reads every event and recomputes the amounts nobody corrected by hand.
        ``match_text`` empty and the two day counts empty mean "the ledger's own":
        payments only by hand, and the default window.
        """
        name, calendar_id, title_pattern = name.strip(), calendar_id.strip(), title_pattern.strip()
        if not name or not calendar_id or not title_pattern:
            raise ValueError("un servizio ha nome, calendario e titolo")
        if kind not in KINDS:
            raise ValueError(f"tipo sconosciuto: {kind}")
        if direction not in DIRECTIONS:
            raise ValueError(f"verso sconosciuto: {direction}")
        if billing not in BILLING:
            raise ValueError(f"modo di pagare sconosciuto: {billing}")
        hours = parse_decimal(default_hours or "1")
        if not hours.is_finite() or hours <= 0:
            raise ValueError("le ore di una sessione sono un numero positivo")
        value = parse_decimal(rate)
        if not value.is_finite() or value < 0:
            raise ValueError("il prezzo di una sessione è un importo non negativo")
        row = (
            name, kind, direction, format_decimal(value), calendar_id, title_pattern,
            (match_text or "").strip() or None, billing, format_decimal(hours),
            _days(lookback_days), _days(ahead_days), 1 if active else 0,
        )
        with self.conn:
            if service_id is None:
                cursor = self.conn.execute(
                    """INSERT INTO services (name, kind, direction, rate, calendar_id, title_pattern,
                                             match_text, billing, default_hours, lookback_days,
                                             ahead_days, active)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    row,
                )
                return int(cursor.lastrowid)
            if self.service(service_id) is None:
                raise ValueError(f"nessun servizio {service_id}")
            self.conn.execute(
                """UPDATE services SET name = ?, kind = ?, direction = ?, rate = ?, calendar_id = ?,
                                       title_pattern = ?, match_text = ?, billing = ?,
                                       default_hours = ?, lookback_days = ?, ahead_days = ?, active = ?
                   WHERE id = ?""",
                (*row, service_id),
            )
        if recalculate:
            self.forget_calendar_token(calendar_id)
        return service_id

    # -- sessions ----------------------------------------------------------

    def sessions_of(self, service_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM service_sessions WHERE service_id = ? ORDER BY start, event_id",
            (service_id,),
        ).fetchall()

    def session(self, event_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM service_sessions WHERE event_id = ?", (event_id,)
        ).fetchone()

    def forget_calendar_token(self, calendar_id: str) -> None:
        """Make the next read of this calendar a full one, as a new ledger would."""
        with self.conn:
            self.conn.execute(
                "DELETE FROM settings WHERE key IN (?, ?)",
                (sync_token_key(calendar_id), sync_window_key(calendar_id)),
            )

    def write_session(
        self, event_id: str, service_id: int, start: str, end: str, summary: str,
        hours: str | None, synced_at: str,
    ) -> None:
        """The event as the calendar says it now, valid; the amount follows the length.

        An hourly service is paid by the hours the event lasts, so a session whose
        duration changed changes its amount — unless a person corrected it, and
        that correction survives. A session moving to another service takes that
        service's price and loses the correction, which was the other one's.
        """
        service = self.service(service_id)
        hours_value = parse_decimal(hours) if hours is not None else None
        amount = format_decimal(session_amount(
            parse_decimal(service["rate"]), hours_value, service["billing"],
            parse_decimal(service["default_hours"]),
        ))
        existing = self.session(event_id)
        if existing is not None and existing["service_id"] == service_id:
            kept = existing["amount"] if existing["amount_by_hand"] else amount
            self.conn.execute(
                """UPDATE service_sessions SET start = ?, "end" = ?, summary = ?, hours = ?,
                                               amount = ?, status = ?, synced_at = ?
                   WHERE event_id = ?""",
                (start, end or None, summary, _hours_text(hours_value), kept, VALID, synced_at, event_id),
            )
            return
        self.conn.execute(
            """INSERT INTO service_sessions (event_id, service_id, start, "end", summary, hours,
                                             amount, amount_by_hand, status, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
               ON CONFLICT (event_id) DO UPDATE SET service_id = excluded.service_id,
                   start = excluded.start, "end" = excluded."end", summary = excluded.summary,
                   hours = excluded.hours, amount = excluded.amount, amount_by_hand = 0,
                   status = excluded.status, synced_at = excluded.synced_at""",
            (event_id, service_id, start, end or None, summary, _hours_text(hours_value),
             amount, VALID, synced_at),
        )

    def cancel_session(self, event_id: str, synced_at: str) -> bool:
        """The event is gone or no longer a session: out of the balance, still visible."""
        cursor = self.conn.execute(
            """UPDATE service_sessions SET status = ?, synced_at = ?
               WHERE event_id = ? AND status != ?""",
            (CANCELLED, synced_at, event_id, CANCELLED),
        )
        return cursor.rowcount > 0

    def set_session_amount(self, event_id: str, amount: str) -> None:
        value = parse_decimal(amount)
        if not value.is_finite() or value < 0:
            raise ValueError("l'importo di una sessione è non negativo")
        if self.session(event_id) is None:
            raise ValueError(f"nessuna sessione {event_id}")
        with self.conn:
            self.conn.execute(
                "UPDATE service_sessions SET amount = ?, amount_by_hand = 1 WHERE event_id = ?",
                (format_decimal(value), event_id),
            )

    # -- sessions closed by hand --------------------------------------------

    def closures_of(self, service_id: int) -> dict[str, str]:
        """The sessions a person closed by hand, with the note that says why."""
        rows = self.conn.execute(
            """SELECT s.event_id, s.note FROM service_closures s
               JOIN service_sessions x ON x.event_id = s.event_id
               WHERE x.service_id = ?""",
            (service_id,),
        ).fetchall()
        return {row["event_id"]: row["note"] for row in rows}

    def close_session(self, event_id: str, note: str, closed_at: str) -> None:
        """Close a session by hand: it stops being owed, and the note says why.

        The note is required and always: with no movement behind it, it is the
        only thing that explains a session nobody paid.
        """
        written = (note or "").strip()
        if not written:
            raise ValueError("una sessione chiusa a mano ha una nota")
        if self.session(event_id) is None:
            raise ValueError(f"nessuna sessione {event_id}")
        with self.conn:
            self.conn.execute(
                """INSERT INTO service_closures (event_id, note, closed_at) VALUES (?, ?, ?)
                   ON CONFLICT (event_id) DO UPDATE SET note = excluded.note,
                       closed_at = excluded.closed_at""",
                (event_id, written, closed_at),
            )

    def reopen_session(self, event_id: str) -> None:
        """The session is owed again: the hand's mark goes, the payments stay."""
        with self.conn:
            self.conn.execute("DELETE FROM service_closures WHERE event_id = ?", (event_id,))

    # -- payments ----------------------------------------------------------

    def payments_of(self, service_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT t.id, t.date, t.amount, t.description, t.counterparty, p.by_rule
               FROM service_payments p JOIN transactions t ON t.id = p.transaction_id
               WHERE p.service_id = ? ORDER BY t.date, t.id""",
            (service_id,),
        ).fetchall()

    def paid_total(self, service_id: int) -> Decimal:
        return sum(
            (abs(parse_decimal(row["amount"])) for row in self.payments_of(service_id)), Decimal(0)
        )

    def payment_service(self, transaction_id: int) -> int | None:
        row = self.conn.execute(
            "SELECT service_id FROM service_payments WHERE transaction_id = ?", (transaction_id,)
        ).fetchone()
        return row["service_id"] if row else None

    def payment_candidates(
        self, service_id: int, query: str | None = None, limit: int = 15, offset: int = 0
    ) -> list[sqlite3.Row]:
        """The movements a person may link by hand, the likeliest first.

        Only movements on a real account, because a mirror written by a transfer
        rule is the other half of money already in the list. No date limit: the
        list is searched rather than scrolled, and a payment may be older than
        the bank's own retention.

        The order is what makes a short page useful: whoever already paid this
        service, then an amount that is a whole number of sessions, then the most
        recent.
        """
        service = self.service(service_id)
        where, params = _candidate_filters(service, query)
        rate_cents = _cents(service["rate"])
        return self.conn.execute(
            f"""SELECT t.id, t.date, t.amount, t.description, t.counterparty
                FROM transactions t JOIN accounts a ON a.id = t.account_id
                WHERE {where}
                ORDER BY
                  CASE WHEN UPPER(REPLACE(COALESCE(t.counterparty_account, ''), ' ', '')) IN (
                             SELECT UPPER(REPLACE(COALESCE(t2.counterparty_account, ''), ' ', ''))
                             FROM service_payments p JOIN transactions t2 ON t2.id = p.transaction_id
                             WHERE p.service_id = ? AND COALESCE(t2.counterparty_account, '') <> ''
                           ) THEN 0 ELSE 1 END,
                  CASE WHEN ? > 0 AND CAST(ROUND(ABS(CAST(t.amount AS REAL)) * 100) AS INTEGER) % ? = 0
                       THEN 0 ELSE 1 END,
                  t.date DESC, t.id DESC
                LIMIT ? OFFSET ?""",
            (*params, service_id, rate_cents, rate_cents, limit, offset),
        ).fetchall()

    def count_payment_candidates(self, service_id: int, query: str | None = None) -> int:
        """How many movements the same search would page through."""
        service = self.service(service_id)
        where, params = _candidate_filters(service, query)
        row = self.conn.execute(
            f"""SELECT COUNT(*) AS n FROM transactions t JOIN accounts a ON a.id = t.account_id
                WHERE {where}""",
            params,
        ).fetchone()
        return int(row["n"])

    def link_payment(self, transaction_id: int, service_id: int | None) -> None:
        """Link a movement to a service by hand, or unlink it (``service_id`` None).

        A link by hand is never undone by a sync. Unlinking by hand keeps the
        movement out of the IBAN linking too, so it does not come back: that is
        recorded as a link to no service, kept in `settings`.
        """
        with self.conn:
            self.conn.execute("DELETE FROM service_payments WHERE transaction_id = ?", (transaction_id,))
            if service_id is None:
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, '1')",
                    (_unlinked_key(transaction_id),),
                )
                return
            if self.service(service_id) is None:
                raise ValueError(f"nessun servizio {service_id}")
            self.conn.execute("DELETE FROM settings WHERE key = ?", (_unlinked_key(transaction_id),))
            self.conn.execute(
                "INSERT INTO service_payments (transaction_id, service_id, by_rule) VALUES (?, ?, 0)",
                (transaction_id, service_id),
            )

    def link_payments_by_text(self) -> int:
        """Link every movement whose description carries a service's text.

        The service's direction decides which way the money moves: a credit for
        one given, a debit for one received. Movements already linked, by hand or
        by another service, and movements a person unlinked are left as they are.
        Returns how many were linked.
        """
        linked = 0
        with self.conn:
            for service in self.services(active_only=True):
                text = (service["match_text"] or "").strip()
                if not text:
                    continue
                cursor = self.conn.execute(
                    f"""INSERT INTO service_payments (transaction_id, service_id, by_rule)
                        SELECT t.id, ?, 1 FROM transactions t
                        WHERE t.description LIKE ? ESCAPE '\\'
                          AND {_PAYMENT_SIGN_SQL[service["direction"]]}
                          AND t.id NOT IN (SELECT transaction_id FROM service_payments)
                          AND 'tracking:unlinked:' || t.id NOT IN (SELECT key FROM settings)""",
                    (service["id"], _contains(text)),
                )
                linked += cursor.rowcount
        return linked


def _unlinked_key(transaction_id: int) -> str:
    return f"tracking:unlinked:{transaction_id}"


def sync_token_key(calendar_id: str) -> str:
    """Where the calendar's sync token is kept, in `settings`."""
    return f"tracking:sync_token:{calendar_id}"


def _hours_text(hours) -> str | None:
    return None if hours is None else format_decimal(hours)


def sync_window_key(calendar_id: str) -> str:
    """The window the stored token was asked with: a different one needs a full read."""
    return f"tracking:sync_window:{calendar_id}"


def synced_at(now: dt.datetime) -> str:
    return now.isoformat(timespec="seconds")


def _candidate_filters(service, query: str | None) -> tuple[str, list]:
    """The movements a link may use, and the search over them.

    The same filter feeds the page and its count, so a total can never disagree
    with what paging returns.
    """
    clauses = [
        "a.type = 'real'",
        "t.mirror_of IS NULL",
        _PAYMENT_SIGN_SQL[service["direction"]],
        "t.id NOT IN (SELECT transaction_id FROM service_payments)",
    ]
    params: list = []
    typed = (query or "").strip()
    if typed:
        like = f"%{typed}%"
        clauses.append(
            "(t.description LIKE ? OR COALESCE(t.counterparty, '') LIKE ? OR t.amount LIKE ?)"
        )
        params += [like, like, like]
    return " AND ".join(clauses), params


def _cents(amount: str) -> int:
    """A money amount in cents, so a whole number of sessions stays exact."""
    return int(parse_decimal(amount) * 100)


def _days(value: int | None) -> int | None:
    """A day count a service may set, or None for the ledger's own default."""
    if value is None:
        return None
    if value < 0:
        raise ValueError("i giorni di una finestra non sono negativi")
    return int(value)


def _contains(text: str) -> str:
    """The text as a `LIKE` pattern that means exactly "contains this".

    The wildcards a person may type are escapes, not wildcards: searching for
    "50%" or "a_b" must not quietly match everything.
    """
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
