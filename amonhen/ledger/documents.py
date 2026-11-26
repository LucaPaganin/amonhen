"""The documents behind a movement: the invoice or receipt read from Paperless.

Paperless owns the document and its text; the ledger keeps only the link and a
snapshot of the title, so a movement can show its paperwork without asking
Paperless again — and keeps showing it when Paperless is down.

A person links by choice; a rule may link instead, when the document's amount
and date leave exactly one movement that can pay it (desiderata 5.16-bis).
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from amonhen.core.documents import in_window
from amonhen.core.tracking import description_matches


@dataclass(frozen=True)
class DocumentLinks:
    """What one pass of the rules did, and what it left to a person."""

    linked: int = 0
    ambiguous: tuple[int, ...] = ()
    skipped: int = 0


class DocumentsMixin:
    """One part of `Ledger`: which documents justify which movements."""

    conn: sqlite3.Connection

    def documents_of(self, transaction_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT paperless_id, title, created, kind, by_rule FROM transaction_documents
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
        kind: str | None, linked_at: str, by_rule: bool = False,
    ) -> None:
        """Attach a Paperless document to a movement; linking twice is harmless."""
        if self.conn.execute("SELECT 1 FROM transactions WHERE id = ?", (transaction_id,)).fetchone() is None:
            raise ValueError(f"nessun movimento {transaction_id}")
        with self.conn:
            self.conn.execute(
                """INSERT INTO transaction_documents
                       (transaction_id, paperless_id, title, created, kind, linked_at, by_rule)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (transaction_id, paperless_id) DO UPDATE SET
                       title = excluded.title, created = excluded.created,
                       kind = excluded.kind, linked_at = excluded.linked_at""",
                (transaction_id, paperless_id, title, created, kind, linked_at, int(by_rule)),
            )
            self.conn.execute("DELETE FROM settings WHERE key = ?", (_unlinked_key(paperless_id),))

    def unlink_document(self, transaction_id: int, paperless_id: int) -> None:
        """The document is not this movement's after all.

        A person's unlink is remembered, so a later pass of the rules does not
        put the link back: it is recorded as a link to no movement, in `settings`.
        """
        with self.conn:
            self.conn.execute(
                "DELETE FROM transaction_documents WHERE transaction_id = ? AND paperless_id = ?",
                (transaction_id, paperless_id),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, '1')",
                (_unlinked_key(paperless_id),),
            )

    # -- the rules (desiderata 5.16-bis) -----------------------------------

    def document_rules(self, *, active_only: bool = False) -> list[sqlite3.Row]:
        clause = "WHERE active = 1" if active_only else ""
        return self.conn.execute(
            f"""SELECT correspondent, before_days, after_days, match_text, created_at, active
                FROM document_rules {clause} ORDER BY correspondent"""
        ).fetchall()

    def document_rule(self, correspondent: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT correspondent, before_days, after_days, match_text, created_at, active
               FROM document_rules WHERE correspondent = ?""",
            (correspondent,),
        ).fetchone()

    def set_document_rule(
        self, correspondent: str, *, before_days: int, after_days: int,
        match_text: str | None = None, active: bool = True, created_at: str,
    ) -> None:
        """Write the rule of one issuer, replacing what was there."""
        name = correspondent.strip()
        if not name:
            raise ValueError("una regola vuole un emittente")
        if before_days < 0 or after_days < 0:
            raise ValueError("i giorni di una finestra non sono negativi: il verso lo dà il campo")
        text = (match_text or "").strip() or None
        with self.conn:
            self.conn.execute(
                """INSERT INTO document_rules
                       (correspondent, before_days, after_days, match_text, created_at, active)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (correspondent) DO UPDATE SET
                       before_days = excluded.before_days, after_days = excluded.after_days,
                       match_text = excluded.match_text, active = excluded.active""",
                (name, int(before_days), int(after_days), text, created_at, int(active)),
            )

    def remove_document_rule(self, correspondent: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM document_rules WHERE correspondent = ?", (correspondent,))

    def link_documents_by_rules(self, documents: Sequence[dict], *, now: str) -> DocumentLinks:
        """Link the documents the rules leave with exactly one possible payment.

        A document links when its issuer has a rule, it states an amount and a
        date, the amount is exact to the cent, exactly one movement sits in the
        rule's window, and neither the document nor the movement is already
        spoken for: a movement a person linked, or the rules linked, is not a
        candidate again. Two candidates mean a choice, and a choice is a person's.

        `documents` carries what Paperless says: `paperless_id`, `title`,
        `created`, `kind`, `correspondent`, `amount`.
        """
        rules = {row["correspondent"]: row for row in self.document_rules(active_only=True)}
        if not rules:
            return DocumentLinks()

        candidates = self._payment_candidates()
        linked = 0
        ambiguous: list[int] = []
        skipped = 0
        taken: set[int] = set()

        for document in documents:
            corr = (document.get("correspondent") or "").strip()
            rule = rules.get(corr)
            if rule is None:
                continue
            paperless_id = int(document["paperless_id"])
            amount = _cents(document.get("amount"))
            day = _date(document.get("created"))
            if amount is None or day is None:
                continue
            if self._document_is_linked(paperless_id) or self._unlinked(paperless_id):
                skipped += 1
                continue
            text = (rule["match_text"] or "").strip()
            found = [
                row for row in candidates
                if row["id"] not in taken
                and abs(_cents(row["amount"]) or 0) == amount
                and in_window(day, _date(row["date"]) or day, rule["before_days"], rule["after_days"])
                and (not text or description_matches(text, row["description"] or ""))
            ]
            if len(found) > 1:
                ambiguous.append(paperless_id)
                continue
            if not found:
                continue
            movement = found[0]
            taken.add(movement["id"])
            self.link_document(
                movement["id"], paperless_id, title=document.get("title") or "",
                created=document.get("created"), kind=document.get("kind"),
                linked_at=now, by_rule=True,
            )
            linked += 1

        return DocumentLinks(linked=linked, ambiguous=tuple(ambiguous), skipped=skipped)

    # -- private helpers ---------------------------------------------------

    def _payment_candidates(self) -> list[sqlite3.Row]:
        """The outflows that may pay a document: not a transfer leg, not linked yet."""
        return self.conn.execute(
            """SELECT t.id, t.date, t.amount, t.description FROM transactions t
               WHERE CAST(t.amount AS REAL) < 0
                 AND t.id NOT IN (SELECT transaction_id FROM transaction_documents)
                 AND t.id NOT IN (SELECT leg_a FROM transfer_links)
                 AND t.id NOT IN (SELECT leg_b FROM transfer_links)"""
        ).fetchall()

    def _document_is_linked(self, paperless_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM transaction_documents WHERE paperless_id = ?", (paperless_id,)
        ).fetchone() is not None

    def _unlinked(self, paperless_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM settings WHERE key = ?", (_unlinked_key(paperless_id),)
        ).fetchone() is not None


def _unlinked_key(paperless_id: int) -> str:
    return f"documents:unlinked:{paperless_id}"


def _cents(value) -> int | None:
    """An amount as whole cents, from the text the ledger and Paperless carry."""
    if value is None or value == "":
        return None
    try:
        return int(round(float(str(value).replace(",", ".")) * 100))
    except ValueError:
        return None


def _date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
