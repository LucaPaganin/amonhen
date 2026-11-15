"""What a person or a rule says about a movement: its category, splits, tags, note, and the proposals."""
from __future__ import annotations

import datetime as dt
import sqlite3
from decimal import Decimal
from typing import Iterable, Sequence

from amonhen.db import deferred_commits
from amonhen.models import format_decimal, parse_decimal


class CategorizationMixin:
    """What a person or a rule says about a movement: its category, splits, tags, note, and the proposals.

    One part of `Ledger`, which composes them: the methods use `self.conn` and call
    each other through `self`, whatever part they are in."""

    def set_notes(self, transaction_id: int, notes: str | None) -> None:
        """Write the note a person put on a movement, or clear it with nothing.

        Local by construction: the bank sends no note, and no ingest path names
        this column, so a note survives every later sync.
        """
        text = (notes or "").strip()
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE transactions SET notes = ? WHERE id = ?",
                (text or None, transaction_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"transaction {transaction_id} not found")

    def tag(self, name: str) -> int:
        """The id of the tag with this name, created when it does not exist."""
        text = " ".join(name.split())
        if not text:
            raise ValueError("a tag needs a name")
        row = self.conn.execute("SELECT id FROM tags WHERE name = ?", (text,)).fetchone()
        if row is not None:
            return row["id"]
        with self.conn:
            return int(self.conn.execute("INSERT INTO tags (name) VALUES (?)", (text,)).lastrowid)

    def tags(self) -> list[sqlite3.Row]:
        """Every tag, with how many movements carry it."""
        return self.conn.execute(
            """SELECT g.id, g.name, g.episodic, g.essential, COUNT(tt.transaction_id) AS movements
               FROM tags g LEFT JOIN transaction_tags tt ON tt.tag_id = g.id
               GROUP BY g.id ORDER BY g.name"""
        ).fetchall()

    def set_tag_flag(self, tag_id: int, flag: str, value: bool) -> None:
        """Say that a tag makes its movements rare or essential."""
        if flag not in ("episodic", "essential"):
            raise ValueError(f"unknown flag {flag!r}")
        with self.conn:
            cursor = self.conn.execute(
                f"UPDATE tags SET {flag} = ? WHERE id = ?", (1 if value else 0, tag_id)
            )
        if cursor.rowcount == 0:
            raise KeyError(f"tag {tag_id} not found")

    def delete_tag(self, tag_id: int) -> None:
        """Take a tag off every movement, with the rules that put it there."""
        row = self.conn.execute("SELECT name FROM tags WHERE id = ?", (tag_id,)).fetchone()
        if row is None:
            raise KeyError(f"tag {tag_id} not found")
        with self.conn:
            self.conn.execute(
                "DELETE FROM rules WHERE action = 'tag' AND target = ?", (row["name"],)
            )
            self.conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

    def tags_of(self, transaction_id: int) -> list[str]:
        """The names of a movement's tags, alphabetically."""
        return [
            row["name"]
            for row in self.conn.execute(
                """SELECT g.name FROM transaction_tags tt JOIN tags g ON g.id = tt.tag_id
                   WHERE tt.transaction_id = ? ORDER BY g.name""",
                (transaction_id,),
            )
        ]

    def _written_tags(self, transaction_id: int) -> list[str]:
        """The tags a person wrote on a movement, leaving out the rules' work."""
        return [
            row["name"]
            for row in self.conn.execute(
                """SELECT g.name FROM transaction_tags tt JOIN tags g ON g.id = tt.tag_id
                   WHERE tt.transaction_id = ? AND tt.by_rule = 0 ORDER BY g.name""",
                (transaction_id,),
            )
        ]

    def add_tag(self, transaction_id: int, name: str, *, by_rule: bool = False) -> None:
        """Put a tag on a movement. A person's tag takes over one a rule wrote."""
        tag_id = self.tag(name)
        with self.conn:
            self.conn.execute(
                """INSERT INTO transaction_tags (transaction_id, tag_id, by_rule) VALUES (?, ?, ?)
                   ON CONFLICT (transaction_id, tag_id) DO UPDATE SET by_rule = MIN(by_rule, excluded.by_rule)""",
                (transaction_id, tag_id, 1 if by_rule else 0),
            )

    def set_tags(self, transaction_id: int, names: Iterable[str]) -> None:
        """Make a movement carry exactly these tags, as a person's decision."""
        wanted = {" ".join(name.split()) for name in names} - {""}
        with deferred_commits(self.conn), self.conn:
            for name in self.tags_of(transaction_id):
                if name not in wanted:
                    self.remove_tag(transaction_id, name)
            for name in wanted:
                self.add_tag(transaction_id, name)

    def remove_tag(self, transaction_id: int, name: str) -> None:
        with self.conn:
            self.conn.execute(
                """DELETE FROM transaction_tags WHERE transaction_id = ?
                   AND tag_id = (SELECT id FROM tags WHERE name = ?)""",
                (transaction_id, name),
            )

    def set_splits(self, transaction_id: int, splits: Sequence[tuple[int, Decimal]]) -> None:
        """Replace the category side with several postings that still sum to zero.

        A split is the same double-entry shape as a single category: the real
        account keeps its signed amount and the category postings carry the
        rest, opposite in sign.
        """
        row = self.conn.execute(
            "SELECT amount FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"transaction {transaction_id} not found")
        if not splits:
            raise ValueError("a split needs at least one category")
        amount = parse_decimal(row["amount"])
        for account_id, _ in splits:
            if self.account(account_id)["type"] != "category":
                raise ValueError(f"account {account_id} is not a category")
        total = sum((split_amount for _, split_amount in splits), Decimal(0))
        if total != -amount:
            raise ValueError(
                f"the split total {format_decimal(total)} does not balance the "
                f"transaction {format_decimal(amount)}"
            )
        with self.conn:
            self._clear_balancing_postings(transaction_id)
            for account_id, split_amount in splits:
                self.conn.execute(
                    "INSERT INTO postings (transaction_id, account_id, amount, note) VALUES (?, ?, ?, ?)",
                    (transaction_id, account_id, format_decimal(split_amount), "split"),
                )

    def splits(self, transaction_id: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """SELECT p.account_id, a.name, p.amount FROM postings p
                   JOIN accounts a ON a.id = p.account_id
                   WHERE p.transaction_id = ? AND a.type = 'category'
                   ORDER BY p.id""",
                (transaction_id,),
            )
        )

    def record_suggestion(self, merchant: str, category: str, source: str) -> None:
        """Remember a proposal; a human decides, nothing is applied here."""
        if not merchant.strip():
            raise ValueError("a suggestion needs a merchant")
        with self.conn:
            self.conn.execute(
                """INSERT INTO merchant_suggestions (merchant, category, source, created_at, decision)
                   VALUES (?, ?, ?, ?, 'pending')
                   ON CONFLICT (merchant) DO UPDATE SET
                       category = excluded.category, source = excluded.source,
                       created_at = excluded.created_at, decision = 'pending'""",
                (merchant.strip(), category, source, dt.datetime.now(dt.UTC).isoformat()),
            )

    def suggestions(self, decision: str = "pending") -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM merchant_suggestions WHERE decision = ? ORDER BY merchant",
                (decision,),
            )
        )

    def decide_suggestion(self, merchant: str, decision: str) -> None:
        if decision not in ("accepted", "dismissed"):
            raise ValueError(f"unknown decision {decision!r}")
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE merchant_suggestions SET decision = ? WHERE merchant = ?",
                (decision, merchant),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"no suggestion for {merchant!r}")

    def _clear_balancing_postings(self, transaction_id: int) -> None:
        """Drop the non-real side of a transaction, category or clearing."""
        self.conn.execute(
            """DELETE FROM postings WHERE transaction_id = ?
               AND account_id IN (SELECT id FROM accounts WHERE type != 'real')""",
            (transaction_id,),
        )

    def set_category(self, transaction_id: int, account_id: int) -> None:
        """Point the balancing side of a transaction at a category account.

        Works whether that side currently holds a category (a recategorization)
        or the transfer clearing account (a rejected transfer link), so the
        postings keep summing to zero.
        """
        row = self.conn.execute(
            "SELECT amount FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"transaction {transaction_id} not found")
        if self.account(account_id)["type"] != "category":
            raise ValueError(f"account {account_id} is not a category")
        amount = parse_decimal(row["amount"])
        with self.conn:
            self._clear_balancing_postings(transaction_id)
            self.conn.execute(
                "INSERT INTO postings (transaction_id, account_id, amount) VALUES (?, ?, ?)",
                (transaction_id, account_id, format_decimal(-amount)),
            )

    def category_of(self, transaction_id: int) -> str | None:
        row = self.conn.execute(
            """SELECT a.name FROM postings p
               JOIN accounts a ON a.id = p.account_id
               WHERE p.transaction_id = ? AND a.type = 'category'
               ORDER BY p.id LIMIT 1""",
            (transaction_id,),
        ).fetchone()
        return row["name"] if row else None
