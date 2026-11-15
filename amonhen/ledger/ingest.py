"""Writing what a source reports: the two-tier dedup, pending to booked, the held probable duplicates."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from typing import Iterable

from amonhen.db import deferred_commits
from amonhen.dedup import content_hash
from amonhen.ledger.definitions import (
    PENDING_WINDOW_DAYS,
    _movement_from_json,
    _movement_json,
    _numbered,
    _Plan,
    _TRANSACTION_COLUMNS,
)
from amonhen.models import IncomingTransaction, RecordAction, format_decimal


class IngestMixin:
    """Writing what a source reports: the two-tier dedup, pending to booked, the held probable duplicates.

    One part of `Ledger`, which composes them: the methods use `self.conn` and call
    each other through `self`, whatever part they are in."""

    # -- transactions ------------------------------------------------------

    def record(
        self, txn: IncomingTransaction, occurrence: int = 1, *, restoring: bool = False
    ) -> tuple[int, RecordAction]:
        """Write one movement, or say why it was not written.

        The id is 0 when nothing was written — the movement is one a person
        deleted, and the tombstone knows it — so the caller reads the action.

        `restoring` is for the one caller that *is* bringing a deleted movement
        back: the dedup runs as always, so a movement the ledger already holds is
        answered as a duplicate instead of being written twice, and only the
        tombstone's veto — the thing being undone — is skipped.
        """
        return self._carry_out(txn, self._plan(txn, occurrence, restoring=restoring))

    def _plan(self, txn: IncomingTransaction, occurrence: int = 1, *,
              restoring: bool = False) -> "_Plan":
        """What `record` would do with this movement, without doing it.

        The one decision the write path and the period sync's preview share: a
        preview that reasoned on its own could promise what the write does not do.
        """
        digest = content_hash(txn.account_id, txn.date, txn.amount, txn.description)
        if occurrence > 1:
            # Identical content repeated inside one ingest batch is a second
            # real movement (exports and some providers carry no id), not a
            # re-import of the first.
            digest = f"{digest}:r{occurrence}"
        existing = self._find_by_external_id(txn)
        if existing is not None:
            return self._absorb(existing, txn, digest)
        twin = self._find_by_content_hash(digest)
        if twin is not None:
            if txn.external_id and twin["external_id"] and twin["external_id"] != txn.external_id:
                # Same content, different provider id: two real transactions
                # (four identical top-ups on one day happen). Keep the base hash
                # usable for the import path by suffixing the duplicate's.
                digest = f"{digest}:{txn.external_id}"
            else:
                return self._absorb(twin, txn, digest)
        # The pending row this settled one promotes, or the settled row this
        # late pending twin repeats.
        counterpart = self._find_opposite_status(txn)
        if counterpart is not None:
            return self._absorb(counterpart, txn, digest)
        # The tombstone is read last on purpose: a movement the ledger already
        # holds is a duplicate whatever a person deleted once, and only a row
        # that is really absent can be one a deletion keeps out.
        tombstone = None if restoring else self._tombstone(txn, digest)
        if tombstone is None:
            return _Plan("inserted", digest)
        if not tombstone["reimport_deleted"]:
            return _Plan("suppressed", digest)
        return _Plan("reimported", digest, tombstone=tombstone)

    def _carry_out(self, txn: IncomingTransaction, plan: "_Plan") -> tuple[int, RecordAction]:
        if plan.action == "duplicate":
            return plan.row["id"], "duplicate"
        if plan.action == "promoted":
            return self._promote(plan.row, txn, plan.digest)
        if plan.action == "suppressed":
            return 0, "suppressed"
        transaction_id = self._insert(txn, plan.digest)
        if plan.tombstone is not None:
            self._mark_restored(plan.tombstone["id"], plan.tombstone["notes"], transaction_id)
        return transaction_id, plan.action

    def record_batch(
        self, transactions: Iterable[IncomingTransaction], *, hold_probable: bool = False
    ) -> dict[str, int]:
        """Record a batch, giving identical rows inside it their own identity.

        The batch is one transaction: one commit at the end instead of one per
        movement, and nothing written when any of them fails.

        With `hold_probable` (the period sync), a movement that would be written
        but looks like one the other ingest path already wrote under other words
        is held instead (`held_transactions`), for a person to decide.
        """
        actions: dict[str, int] = {}
        with deferred_commits(self.conn):
            for txn, occurrence in _numbered(transactions):
                plan = self._plan(txn, occurrence)
                twin = (
                    self.probable_duplicate(txn)
                    if hold_probable and plan.action == "inserted" else None
                )
                if twin is not None:
                    action = self._hold(txn, occurrence, plan.digest, twin)
                else:
                    _, action = self._carry_out(txn, plan)
                actions[action] = actions.get(action, 0) + 1
        return actions

    def preview_batch(
        self, transactions: Iterable[IncomingTransaction]
    ) -> list[tuple[IncomingTransaction, RecordAction, sqlite3.Row | None]]:
        """What `record_batch(..., hold_probable=True)` would do, writing nothing.

        Each movement comes back with its action and, for a probable duplicate,
        the row it resembles. Read-only, so a pending row promoted earlier in the
        same batch is not seen by the rows after it: the preview is per movement
        against the ledger as it stands.
        """
        answers = []
        for txn, occurrence in _numbered(transactions):
            plan = self._plan(txn, occurrence)
            twin = self.probable_duplicate(txn) if plan.action == "inserted" else None
            action: RecordAction = plan.action
            if twin is not None:
                held = self._held_row(txn.account_id, txn.external_id or plan.digest)
                action = "discarded" if held is not None and held["decision"] == "discarded" else "held"
            answers.append((txn, action, twin))
        return answers

    def probable_duplicate(self, txn: IncomingTransaction) -> sqlite3.Row | None:
        """A row the other ingest path wrote on the same account, day and amount.

        Section 5.1 makes the content hash the only discriminator between sync
        and file import, and the hash contains the description: when the bank
        words a movement differently in PSD2 and in its export, the hash cannot
        see that they are one. Same account, day and amount from the other
        source is the evidence there is; it is not proof, so it holds a movement
        rather than refusing it.
        """
        return self.conn.execute(
            """SELECT * FROM transactions
               WHERE account_id = ? AND date = ? AND amount = ? AND source <> ?
               ORDER BY id LIMIT 1""",
            (txn.account_id, txn.date.isoformat(), format_decimal(txn.amount), txn.source),
        ).fetchone()

    def _hold(self, txn: IncomingTransaction, occurrence: int, digest: str,
              twin: sqlite3.Row) -> RecordAction:
        """Keep a probable duplicate aside, once: a period run again holds nothing twice."""
        key = txn.external_id or digest
        held = self._held_row(txn.account_id, key)
        if held is not None:
            return "discarded" if held["decision"] == "discarded" else "held"
        with self.conn:
            self.conn.execute(
                """INSERT INTO held_transactions (account_id, key, occurrence, date, amount,
                       description, movement, twin_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    txn.account_id, key, occurrence, txn.date.isoformat(),
                    format_decimal(txn.amount), txn.description, _movement_json(txn),
                    twin["id"], dt.datetime.now(dt.UTC).isoformat(),
                ),
            )
        return "held"

    def _held_row(self, account_id: int, key: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM held_transactions WHERE account_id = ? AND key = ?", (account_id, key)
        ).fetchone()

    def held_transactions(self, account_id: int | None = None) -> list[sqlite3.Row]:
        """The probable duplicates still waiting, with the row each one resembles."""
        sql = """SELECT h.*, a.name AS account_name, t.description AS twin_description,
                        t.source AS twin_source, t.source_file AS twin_source_file
                 FROM held_transactions h
                 JOIN accounts a ON a.id = h.account_id
                 LEFT JOIN transactions t ON t.id = h.twin_id
                 WHERE h.decision = 'pending'"""
        params: tuple = ()
        if account_id is not None:
            sql += " AND h.account_id = ?"
            params = (account_id,)
        return list(self.conn.execute(sql + " ORDER BY h.date, h.id", params))

    def decide_held(self, held_id: int, decision: str) -> tuple[int, RecordAction | None]:
        """Write a held movement (`write`) or keep it out (`discard`), once.

        Writing goes through `record` with the occurrence the batch gave it, so
        the dedup and the tombstones still have their say — a movement the
        ledger acquired since the hold comes back a duplicate, not a second row.
        A discarded movement stays in the table: it is what keeps the same
        period, run again, from asking a second time.
        """
        if decision not in ("write", "discard"):
            raise ValueError(f"unknown decision {decision!r}: write or discard")
        row = self.conn.execute(
            "SELECT * FROM held_transactions WHERE id = ?", (held_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"held movement {held_id} not found")
        if row["decision"] != "pending":
            raise ValueError(f"held movement {held_id} was already decided ({row['decision']})")
        transaction_id, action = 0, None
        with deferred_commits(self.conn):
            if decision == "write":
                movement = _movement_from_json(
                    row["movement"], row["account_id"], self.uncategorized()
                )
                transaction_id, action = self.record(movement, row["occurrence"])
            with self.conn:
                self.conn.execute(
                    "UPDATE held_transactions SET decision = ? WHERE id = ?",
                    ("written" if decision == "write" else "discarded", held_id),
                )
        return transaction_id, action

    def _tombstone(self, txn: IncomingTransaction, digest: str) -> sqlite3.Row | None:
        """The deletion this movement matches, with the account's own flag.

        Three ways a movement can be the one that was deleted, and each one is a
        relation the ledger already knows:

        - the same provider identifier it was deleted under;
        - the same content arriving from the *other* ingest path — an export
          carries no identifier, and section 5.1 makes the content hash the only
          discriminator in the overlap between sync and import;
        - the settled twin of a pending movement deleted here, which the bank
          reports under a new reference and a new date.

        Exact everywhere else, and only there: four identical top-ups on one day
        are four movements, so a same-status row is never matched on its content
        alone — that is what keeps the surviving twin of a deleted one alive.
        """
        return self.conn.execute(
            """SELECT d.*, a.reimport_deleted
               FROM deleted_transactions d JOIN accounts a ON a.id = d.account_id
               WHERE d.account_id = ?
                 AND (
                     d.key = ?
                     OR (d.content_hash = ? AND d.source <> ?)
                     OR (d.status <> ? AND d.amount = ?
                         AND ABS(julianday(d.date) - julianday(?)) <= ?)
                 )""",
            (
                txn.account_id,
                txn.external_id or digest,
                digest,
                txn.source,
                txn.status,
                format_decimal(txn.amount),
                txn.date.isoformat(),
                PENDING_WINDOW_DAYS,
            ),
        ).fetchone()

    def _find_by_external_id(self, txn: IncomingTransaction) -> sqlite3.Row | None:
        if not txn.external_id:
            return None
        return self.conn.execute(
            "SELECT * FROM transactions WHERE account_id = ? AND external_id = ?",
            (txn.account_id, txn.external_id),
        ).fetchone()

    def _find_by_content_hash(self, digest: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM transactions WHERE content_hash = ? ORDER BY id LIMIT 1", (digest,)
        ).fetchone()

    def _find_opposite_status(self, txn: IncomingTransaction) -> sqlite3.Row | None:
        """The pending/booked twin of this row, if the bank changed date or id."""
        wanted = "PDNG" if txn.status == "BOOK" else "BOOK"
        return self.conn.execute(
            """SELECT * FROM transactions
               WHERE account_id = ? AND amount = ? AND status = ?
                 AND ABS(julianday(date) - julianday(?)) <= ?
               ORDER BY date LIMIT 1""",
            (txn.account_id, format_decimal(txn.amount), wanted,
             txn.date.isoformat(), PENDING_WINDOW_DAYS),
        ).fetchone()

    def _absorb(self, existing: sqlite3.Row, txn: IncomingTransaction, digest: str) -> "_Plan":
        if existing["status"] == "PDNG" and txn.status == "BOOK":
            return _Plan("promoted", digest, row=existing)
        return _Plan("duplicate", digest, row=existing)

    def _promote(self, pending: sqlite3.Row, txn: IncomingTransaction, digest: str) -> tuple[int, RecordAction]:
        with self.conn:
            self.conn.execute(
                """UPDATE transactions
                   SET account_id = ?, date = ?, amount = ?, description = ?, status = ?,
                       external_id = ?, content_hash = ?, source = ?, source_file = ?,
                       raw_payload = ?, counterparty = ?, counterparty_account = ?, currency = ?
                   WHERE id = ?""",
                self._values(txn, digest) + (pending["id"],),
            )
            self._replace_postings(pending["id"], txn)
        return pending["id"], "promoted"

    def _insert(self, txn: IncomingTransaction, digest: str) -> int:
        columns = _TRANSACTION_COLUMNS + ("created_at",)
        with self.conn:
            cursor = self.conn.execute(
                f"INSERT INTO transactions ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' * len(columns))})",
                self._values(txn, digest) + (dt.datetime.now(dt.UTC).isoformat(),),
            )
            transaction_id = int(cursor.lastrowid)
            self._replace_postings(transaction_id, txn)
        return transaction_id

    def _values(self, txn: IncomingTransaction, digest: str) -> tuple:
        return (
            txn.account_id, txn.date.isoformat(), format_decimal(txn.amount), txn.description,
            txn.status, txn.external_id, digest, txn.source, txn.source_file,
            json.dumps(txn.raw, ensure_ascii=False, sort_keys=True), txn.counterparty,
            txn.counterparty_account, txn.currency,
        )

    def _replace_postings(self, transaction_id: int, txn: IncomingTransaction) -> None:
        self.conn.execute("DELETE FROM postings WHERE transaction_id = ?", (transaction_id,))
        for account_id, amount in (
            (txn.account_id, txn.amount),
            (txn.balancing_account_id, -txn.amount),
        ):
            self.conn.execute(
                "INSERT INTO postings (transaction_id, account_id, amount) VALUES (?, ?, ?)",
                (transaction_id, account_id, format_decimal(amount)),
            )
