"""Services, their sessions and the movements that pay them (desiderata 5.17).

None of these tables is read by a posting: spending, the balances and the 5.4 check
cannot see a service, and linking a payment writes nothing on the movement.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from decimal import Decimal

from amonhen.core.tracking import CANCELLED, DIRECTIONS, KINDS, VALID, normalize_iban
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
        counterparty_iban: str | None,
        active: bool = True,
    ) -> int:
        """Create a service (``service_id`` None) or rewrite one; returns its id.

        A new rate is the price of the sessions that appear from now on: the
        sessions already written keep the amount they had.
        """
        name, calendar_id, title_pattern = name.strip(), calendar_id.strip(), title_pattern.strip()
        if not name or not calendar_id or not title_pattern:
            raise ValueError("un servizio ha nome, calendario e titolo")
        if kind not in KINDS:
            raise ValueError(f"tipo sconosciuto: {kind}")
        if direction not in DIRECTIONS:
            raise ValueError(f"verso sconosciuto: {direction}")
        value = parse_decimal(rate)
        if not value.is_finite() or value < 0:
            raise ValueError("il prezzo di una sessione è un importo non negativo")
        row = (
            name, kind, direction, format_decimal(value), calendar_id, title_pattern,
            normalize_iban(counterparty_iban), 1 if active else 0,
        )
        with self.conn:
            if service_id is None:
                cursor = self.conn.execute(
                    """INSERT INTO services (name, kind, direction, rate, calendar_id, title_pattern,
                                             counterparty_iban, active)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    row,
                )
                return int(cursor.lastrowid)
            if self.service(service_id) is None:
                raise ValueError(f"nessun servizio {service_id}")
            self.conn.execute(
                """UPDATE services SET name = ?, kind = ?, direction = ?, rate = ?, calendar_id = ?,
                                       title_pattern = ?, counterparty_iban = ?, active = ?
                   WHERE id = ?""",
                (*row, service_id),
            )
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

    def write_session(self, event_id: str, service_id: int, start: str, summary: str, synced_at: str) -> None:
        """The event as the calendar says it now, valid; the amount is kept if it existed.

        A session moving to another service takes that service's rate, because the
        amount it had was the other service's price.
        """
        existing = self.session(event_id)
        if existing is not None and existing["service_id"] == service_id:
            self.conn.execute(
                """UPDATE service_sessions SET start = ?, summary = ?, status = ?, synced_at = ?
                   WHERE event_id = ?""",
                (start, summary, VALID, synced_at, event_id),
            )
            return
        rate = self.service(service_id)["rate"]
        self.conn.execute(
            """INSERT INTO service_sessions (event_id, service_id, start, summary, amount, status, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (event_id) DO UPDATE SET service_id = excluded.service_id,
                   start = excluded.start, summary = excluded.summary, amount = excluded.amount,
                   status = excluded.status, synced_at = excluded.synced_at""",
            (event_id, service_id, start, summary, rate, VALID, synced_at),
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
                "UPDATE service_sessions SET amount = ? WHERE event_id = ?",
                (format_decimal(value), event_id),
            )

    # -- payments ----------------------------------------------------------

    def payments_of(self, service_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT t.id, t.date, t.amount, t.description, t.counterparty, p.by_iban
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

    def payment_candidates(self, service_id: int, since: dt.date, limit: int = 50) -> list[sqlite3.Row]:
        """The movements a person may link by hand: the service's direction, not linked yet.

        Only movements on a real account, because a mirror written by a transfer
        rule is the other half of money already in the list.
        """
        service = self.service(service_id)
        return self.conn.execute(
            f"""SELECT t.id, t.date, t.amount, t.description, t.counterparty
                FROM transactions t JOIN accounts a ON a.id = t.account_id
                WHERE a.type = 'real' AND t.mirror_of IS NULL AND t.date >= ?
                  AND {_PAYMENT_SIGN_SQL[service["direction"]]}
                  AND t.id NOT IN (SELECT transaction_id FROM service_payments)
                ORDER BY t.date DESC, t.id DESC LIMIT ?""",
            (since.isoformat(), limit),
        ).fetchall()

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
                "INSERT INTO service_payments (transaction_id, service_id, by_iban) VALUES (?, ?, 0)",
                (transaction_id, service_id),
            )

    def link_payments_by_iban(self) -> int:
        """Link every movement from or to a service's IBAN, in the service's direction.

        Movements already linked, by hand or not, and movements a person unlinked
        are left as they are. Returns how many were linked.
        """
        linked = 0
        with self.conn:
            for service in self.services(active_only=True):
                if not service["counterparty_iban"]:
                    continue
                cursor = self.conn.execute(
                    f"""INSERT INTO service_payments (transaction_id, service_id, by_iban)
                        SELECT t.id, ?, 1 FROM transactions t
                        WHERE UPPER(REPLACE(t.counterparty_account, ' ', '')) = ?
                          AND {_PAYMENT_SIGN_SQL[service["direction"]]}
                          AND t.id NOT IN (SELECT transaction_id FROM service_payments)
                          AND 'tracking:unlinked:' || t.id NOT IN (SELECT key FROM settings)""",
                    (service["id"], service["counterparty_iban"]),
                )
                linked += cursor.rowcount
        return linked


def _unlinked_key(transaction_id: int) -> str:
    return f"tracking:unlinked:{transaction_id}"


def sync_token_key(calendar_id: str) -> str:
    """Where the calendar's sync token is kept, in `settings`."""
    return f"tracking:sync_token:{calendar_id}"


def synced_at(now: dt.datetime) -> str:
    return now.isoformat(timespec="seconds")
