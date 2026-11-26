"""The documents behind a movement: the invoice or receipt read from Paperless.

Paperless owns the document and its text; the ledger keeps only the link and a
snapshot of the title, so a movement can show its paperwork without asking
Paperless again — and keeps showing it when Paperless is down.
"""
from __future__ import annotations

import sqlite3


class DocumentsMixin:
    """One part of `Ledger`: which documents justify which movements."""

    def documents_of(self, transaction_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT paperless_id, title, created, kind FROM transaction_documents
               WHERE transaction_id = ? ORDER BY created, paperless_id""",
            (transaction_id,),
        ).fetchall()

    def movements_of_documents(self, paperless_ids: list[int]) -> dict[int, list[sqlite3.Row]]:
        """Which movements already pay each document, one query for the whole page."""
        if not paperless_ids:
            return {}
        marks = ", ".join("?" * len(paperless_ids))
        rows = self.conn.execute(
            f"""SELECT d.paperless_id, t.id, t.date, t.amount, t.description
                FROM transaction_documents d JOIN transactions t ON t.id = d.transaction_id
                WHERE d.paperless_id IN ({marks}) ORDER BY t.date, t.id""",
            paperless_ids,
        ).fetchall()
        grouped: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(row["paperless_id"], []).append(row)
        return grouped

    def link_document(
        self, transaction_id: int, paperless_id: int, *, title: str, created: str | None,
        kind: str | None, linked_at: str,
    ) -> None:
        """Attach a Paperless document to a movement; linking twice is harmless."""
        if self.conn.execute("SELECT 1 FROM transactions WHERE id = ?", (transaction_id,)).fetchone() is None:
            raise ValueError(f"nessun movimento {transaction_id}")
        with self.conn:
            self.conn.execute(
                """INSERT INTO transaction_documents
                       (transaction_id, paperless_id, title, created, kind, linked_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (transaction_id, paperless_id) DO UPDATE SET
                       title = excluded.title, created = excluded.created,
                       kind = excluded.kind, linked_at = excluded.linked_at""",
                (transaction_id, paperless_id, title, created, kind, linked_at),
            )

    def unlink_document(self, transaction_id: int, paperless_id: int) -> None:
        """The document is not this movement's after all."""
        with self.conn:
            self.conn.execute(
                "DELETE FROM transaction_documents WHERE transaction_id = ? AND paperless_id = ?",
                (transaction_id, paperless_id),
            )
