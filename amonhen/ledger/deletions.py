"""Deleting a movement into the trash, and bringing it back."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from decimal import Decimal
from typing import Iterable

from amonhen.db import deferred_commits
from amonhen.ledger.definitions import DeletedTotal, Deletion
from amonhen.models import IncomingTransaction, parse_decimal


class DeletionsMixin:
    """Deleting a movement into the trash, and bringing it back.

    One part of `Ledger`, which composes them: the methods use `self.conn` and call
    each other through `self`, whatever part they are in."""

    def delete_transaction(self, transaction_id: int) -> Deletion:
        """Take a movement out of the ledger, keeping it as a tombstone.

        Deleting one leg of a transfer would leave the other leg posted to the
        clearing account with no partner — out of the spending, and nothing on
        the row saying why — so the pair is rejected first and the other leg
        goes back to the queue. The row is copied whole into
        `deleted_transactions`, which is what stops the next sync from writing
        it straight back.
        """
        row = self.conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"transaction {transaction_id} not found")
        if row["mirror_of"] is not None:
            raise ValueError(
                f"transaction {transaction_id} is the other half a transfer rule wrote for "
                f"movement {row['mirror_of']}: delete that one, or change the rule"
            )
        # The other half a transfer rule wrote goes with the movement (the row
        # names it, and the foreign key cascades): there is no pair to reject.
        link = None if self.mirror_of(transaction_id) else self.transfer_link(transaction_id)
        written = self._written_tags(transaction_id)
        with self.conn:
            if link is not None:
                self.set_transfer_review(link["leg_a"], link["leg_b"], "reject")
            # Copied from the row itself rather than from a tuple of fifteen
            # placeholders: a swapped pair there is silent, and the column list
            # would have to be kept in step with the table by hand.
            self.conn.execute(
                """INSERT INTO deleted_transactions (
                       account_id, key, date, amount, description, status, external_id,
                       content_hash, source, source_file, raw_payload, counterparty,
                       counterparty_account, currency, notes, deleted_at, restored_at
                   )
                   SELECT account_id, COALESCE(external_id, content_hash), date, amount,
                       description, status, external_id, content_hash, source, source_file,
                       raw_payload, counterparty, counterparty_account, currency, notes,
                       ?, NULL
                   FROM transactions WHERE id = ?
                   ON CONFLICT (account_id, key) DO UPDATE SET
                       date = excluded.date, amount = excluded.amount,
                       description = excluded.description, status = excluded.status,
                       external_id = excluded.external_id,
                       content_hash = excluded.content_hash, source = excluded.source,
                       source_file = excluded.source_file, raw_payload = excluded.raw_payload,
                       counterparty = excluded.counterparty,
                       counterparty_account = excluded.counterparty_account,
                       currency = excluded.currency, notes = excluded.notes,
                       deleted_at = excluded.deleted_at, restored_at = NULL""",
                (dt.datetime.now(dt.UTC).isoformat(), transaction_id),
            )
            self.conn.execute(
                "UPDATE deleted_transactions SET tags = ? WHERE account_id = ? AND key = ?",
                (
                    json.dumps(written, ensure_ascii=False) if written else None,
                    row["account_id"],
                    row["external_id"] or row["content_hash"],
                ),
            )
            self.conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        return Deletion(transaction_id=transaction_id, unlinked_pair=link is not None)

    def delete_transactions(self, transaction_ids: Iterable[int]) -> list[Deletion]:
        """Delete several movements in one transaction, each as `delete_transaction`.

        One commit for the lot: on the NAS every commit is a flush, and a page of a
        hundred movements deleted one by one would hold the ledger for a minute.
        An id that is not in the ledger stops the whole batch, before anything is
        written, so a stale page cannot delete half of what it showed.
        """
        ids = list(dict.fromkeys(transaction_ids))
        for transaction_id in ids:
            if self.conn.execute(
                "SELECT 1 FROM transactions WHERE id = ?", (transaction_id,)
            ).fetchone() is None:
                raise KeyError(f"transaction {transaction_id} not found")
        if not ids:
            return []
        # A page that holds both halves of a rule's transfer: the half the rule
        # wrote goes with its movement, and is not a second deletion.
        mirrored = {
            row["id"]
            for row in self.conn.execute(
                f"SELECT id, mirror_of FROM transactions WHERE id IN ({', '.join('?' * len(ids))})",
                ids,
            )
            if row["mirror_of"] in ids
        }
        with deferred_commits(self.conn):
            return [
                self.delete_transaction(transaction_id)
                for transaction_id in ids
                if transaction_id not in mirrored
            ]

    def restore_deleted(self, deleted_id: int) -> int:
        """Put a deleted movement back, with the note it had, and say it came back.

        The row is rebuilt from what the tombstone kept — payload and all, under
        the identity it was deleted by — so nothing has to be fetched again and
        the movement cannot land twice: the row it restores is the one whose
        deletion this is, and a tombstone restored twice is refused because
        there is nothing left to put back.
        """
        row = self.conn.execute(
            "SELECT * FROM deleted_transactions WHERE id = ?", (deleted_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"deleted movement {deleted_id} not found")
        if row["restored_at"] is not None:
            raise ValueError(f"deleted movement {deleted_id} was already restored")
        # Through `record`, with the tombstone's veto lifted: a movement the
        # ledger already holds under any of the identities the dedup knows is
        # answered as a duplicate instead of being written a second time, and a
        # freshly written row gets the note the tombstone kept.
        transaction_id, action = self.record(self._movement_of(row), restoring=True)
        self._mark_restored(deleted_id, row["notes"] if action == "inserted" else None, transaction_id)
        return transaction_id

    def deleted_transactions(self, account_id: int | None = None) -> list[sqlite3.Row]:
        """The movements still deleted, newest deletion first.

        Restored ones are left out: they are in the ledger again, and offering
        to restore them would be offering to do what has been done.
        """
        sql = """SELECT d.*, a.name AS account_name
                 FROM deleted_transactions d JOIN accounts a ON a.id = d.account_id
                 WHERE d.restored_at IS NULL"""
        params: tuple = ()
        if account_id is not None:
            sql += " AND d.account_id = ?"
            params = (account_id,)
        return list(self.conn.execute(sql + " ORDER BY d.deleted_at DESC, d.id DESC", params))

    def _movement_of(self, row: sqlite3.Row) -> IncomingTransaction:
        """The tombstone as the ledger records movements, ready to be written."""
        return IncomingTransaction(
            account_id=row["account_id"],
            date=dt.date.fromisoformat(row["date"]),
            amount=parse_decimal(row["amount"]),
            description=row["description"],
            status=row["status"],
            source=row["source"],
            balancing_account_id=self.uncategorized(),
            external_id=row["external_id"],
            counterparty=row["counterparty"],
            counterparty_account=row["counterparty_account"],
            currency=row["currency"],
            raw=json.loads(row["raw_payload"]),
            source_file=row["source_file"],
        )

    def _mark_restored(self, deleted_id: int, notes: str | None, transaction_id: int) -> None:
        """Hand the movement its note and its tags back, and remember it came home.

        The row was written a moment ago with neither, so the tombstone's copy is
        the only one there is. Both callers already hold the note; a tag a rule
        wrote is not kept, because the next `categorize` writes it again.
        """
        tags = self.conn.execute(
            "SELECT tags FROM deleted_transactions WHERE id = ?", (deleted_id,)
        ).fetchone()["tags"]
        with self.conn:
            if notes:
                self.conn.execute(
                    "UPDATE transactions SET notes = ? WHERE id = ?", (notes, transaction_id)
                )
            for name in json.loads(tags) if tags else ():
                self.add_tag(transaction_id, name)
            self.conn.execute(
                "UPDATE deleted_transactions SET restored_at = ? WHERE id = ?",
                (dt.datetime.now(dt.UTC).isoformat(), deleted_id),
            )

    def deleted_total(self, account_id: int, as_of: dt.date, kind: str) -> DeletedTotal:
        """What the hand-deleted movements would add to the figure being checked.

        A deleted movement is missing from the computed balance while the bank
        still counts it, so the difference a deletion leaves is exactly this
        sum — and it is signed the way the movements were: deleting an expense
        takes money out of the ledger, and the bank cannot see that.

        The same boundary `balance` uses: a movement on or before the opening
        date is already folded into the opening figure, so a deletion there
        explains nothing and must not be added here.
        """
        statuses = ("BOOK", "PDNG") if kind == "available" else ("BOOK",)
        opening_date = self.account(account_id)["opening_date"]
        rows = self.conn.execute(
            f"""SELECT amount FROM deleted_transactions
                WHERE account_id = ? AND restored_at IS NULL AND date <= ?
                  AND (? IS NULL OR date > ?)
                  AND status IN ({", ".join("?" * len(statuses))})""",
            (account_id, as_of.isoformat(), opening_date, opening_date, *statuses),
        ).fetchall()
        return DeletedTotal(
            amount=sum((parse_decimal(row["amount"]) for row in rows), Decimal(0)),
            count=len(rows),
        )
