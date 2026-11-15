"""Giroconti: pairs, their review, virtual destinations, passthrough and the halves a rule writes."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

from amonhen.ledger.definitions import TRANSFER_CLEARING
from amonhen.models import Account, format_decimal, parse_decimal


class TransferLegsMixin:
    """Giroconti: pairs, their review, virtual destinations, passthrough and the halves a rule writes.

    One part of `Ledger`, which composes them: the methods use `self.conn` and call
    each other through `self`, whatever part they are in."""

    def is_transfer(self, transaction_id: int) -> bool:
        row = self.conn.execute(
            """SELECT 1 FROM postings p
               JOIN accounts a ON a.id = p.account_id
               WHERE p.transaction_id = ? AND a.type = 'virtual' LIMIT 1""",
            (transaction_id,),
        ).fetchone()
        return row is not None

    def set_transfer_review(self, leg_a: int, leg_b: int, decision: str) -> None:
        """Confirm or reject a link. Rejecting gives both legs their category back."""
        if decision not in ("confirm", "reject"):
            raise ValueError(f"unknown decision {decision!r}")
        with self.conn:
            cursor = self.conn.execute(
                """UPDATE transfer_links SET confirmed_by_human = ?
                   WHERE (leg_a = ? AND leg_b = ?) OR (leg_a = ? AND leg_b = ?)""",
                (1 if decision == "confirm" else -1, leg_a, leg_b, leg_b, leg_a),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"no transfer link between {leg_a} and {leg_b}")
        if decision == "reject":
            for leg in (leg_a, leg_b):
                self.set_category(leg, self.uncategorized())

    def link_transfer_pair(self, leg_a: int, leg_b: int, confidence: str, method: str) -> None:
        """Record a transfer link and clear both legs in one transaction.

        If the two halves could commit separately, a failure in between would
        leave a link whose legs still count as spending, and the candidate
        query skips linked legs, so nothing would ever retry the pair.
        """
        clearing = self.transfer_account()
        with self.conn:
            # Clear first: a missing leg raises before anything is written, and
            # the whole block rolls back either way.
            self._clear_leg(leg_a, clearing)
            self._clear_leg(leg_b, clearing)
            self.conn.execute(
                """INSERT OR IGNORE INTO transfer_links (leg_a, leg_b, confidence, method)
                   VALUES (?, ?, ?, ?)""",
                (leg_a, leg_b, confidence, method),
            )

    def _clear_leg(self, transaction_id: int, clearing: int) -> None:
        row = self.conn.execute(
            "SELECT amount FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"transaction {transaction_id} not found")
        already_cleared = self.conn.execute(
            "SELECT 1 FROM postings WHERE transaction_id = ? AND account_id = ?",
            (transaction_id, clearing),
        ).fetchone()
        if already_cleared:
            return
        amount = parse_decimal(row["amount"])
        self.conn.execute(
            """DELETE FROM postings WHERE transaction_id = ?
               AND account_id IN (SELECT id FROM accounts WHERE type IN ('category', 'virtual'))""",
            (transaction_id,),
        )
        self.conn.execute(
            "INSERT INTO postings (transaction_id, account_id, amount, note) VALUES (?, ?, ?, ?)",
            (transaction_id, clearing, format_decimal(-amount), "transfer"),
        )

    def transfer_target(self, transaction_id: int) -> str | None:
        """The virtual account a leg was posted to, when it has one."""
        row = self.conn.execute(
            """SELECT a.name FROM postings p JOIN accounts a ON a.id = p.account_id
               WHERE p.transaction_id = ? AND a.type = 'virtual'
               ORDER BY a.id LIMIT 1""",
            (transaction_id,),
        ).fetchone()
        return row["name"] if row else None

    def transfer_link(self, transaction_id: int) -> sqlite3.Row | None:
        """The recorded link this leg belongs to, whichever side it is.

        A leg can hold a rejected row and a live one at once — the "no" to the
        pair the matcher proposed, and the pair a person or a rule made after it —
        and the live one is the leg's link.
        """
        return self.conn.execute(
            """SELECT * FROM transfer_links
               WHERE leg_a = ? OR leg_b = ?
               ORDER BY confirmed_by_human = -1, leg_a LIMIT 1""",
            (transaction_id, transaction_id),
        ).fetchone()

    def _live_link(self, transaction_id: int) -> sqlite3.Row | None:
        """The leg's link unless it is a rejection, which pairs it with nothing."""
        link = self.transfer_link(transaction_id)
        return link if link is not None and link["confirmed_by_human"] != -1 else None

    def transfer_of(self, transaction_id: int) -> dict | None:
        """What a leg is a transfer to, or None when it is not a transfer.

        A paired leg names the account its other half sits on: the clearing
        account it was posted to is an implementation detail. A leg to an own
        account that is not connected here has no other half, so it names that
        account. ``state`` keeps a proposal apart from a link a human already
        answered, so the app can show a leg without asking for a decision again.
        """
        target = self.transfer_target(transaction_id)
        if target is None:
            return None
        link = self._live_link(transaction_id)
        if link is None:
            return {
                "kind": "pair" if target == TRANSFER_CLEARING else "passthrough",
                "target": target,
                "state": "confirmed",
                "leg_id": None,
                "by_rule": False,
            }
        other = link["leg_b"] if link["leg_a"] == transaction_id else link["leg_a"]
        row = self.conn.execute(
            """SELECT a.name AS account FROM transactions t
               JOIN accounts a ON a.id = t.account_id WHERE t.id = ?""",
            (other,),
        ).fetchone()
        return {
            "kind": "pair",
            "target": row["account"] if row else target,
            "state": "proposed" if link["confirmed_by_human"] == 0 else "confirmed",
            "leg_id": other,
            # A transfer rule wrote the other half: the pair is undone by
            # changing the rule, not from the movement.
            "by_rule": link["method"] == "rule",
        }

    def virtual_accounts(self) -> list[str]:
        """The names money was recorded into, the pairing account left out."""
        return [
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM accounts WHERE type = 'virtual' AND name <> ? ORDER BY name",
                (TRANSFER_CLEARING,),
            )
        ]

    def move_to_virtual_account(self, transaction_id: int, name: str) -> None:
        """Send the category side of a transaction to a virtual account.

        Used for money moved to an own account that is not connected here: it is
        not spending, and the virtual account keeps the destination visible
        instead of pretending the money vanished.
        """
        account_id = self.ensure_account(Account(name=name, type="virtual"))
        row = self.account(account_id)
        if row["type"] != "virtual":
            raise ValueError(f"{name!r} already names a {row['type']} account")
        with self.conn:
            self._clear_leg(transaction_id, account_id)

    def mirror_target(self, name: str) -> sqlite3.Row:
        """The account a transfer rule may write the other half of a movement on.

        A real account added by hand, or a connected one marked
        `unreported_funding`. Any other connected account already has its own
        half, which the bank reports and the matcher pairs, and writing a second
        one would count the money twice. Raises ValueError with the reason otherwise.
        """
        row = self.find_account(name=name)
        if row is None or row["type"] != "real":
            raise ValueError(f"{name!r} is not a real account")
        if row["external_uid"] is not None and not row["unreported_funding"]:
            raise ValueError(
                f"{name!r} is connected to a bank: its movements arrive by themselves "
                "and the pairing links them (unless it does not report its top-ups)"
            )
        return row

    def mirror_transfer(self, transaction_id: int, name: str) -> int:
        """Write the other half of a transfer on an account that cannot report it, and pair them.

        An account added by hand, or a connected wallet that reports purchases but
        not the top-ups paying for them (`unreported_funding`).

        A deposit that only Revolut's own app shows has no movements a bank
        reports, so the transfers to and from it have nowhere to land: the rule
        that recognises them writes the opposite movement on that account — same
        day, same description, opposite amount — and links the two as a confirmed
        pair. The money leaves spending and income as any pair does, and the
        account's balance is what those movements add up to. The row names the
        movement it mirrors, and goes with it. Returns the new row's id.
        """
        row = self.conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"transaction {transaction_id} not found")
        if row["mirror_of"] is not None:
            raise ValueError(f"transaction {transaction_id} is itself the other half of a transfer")
        target = self.mirror_target(name)
        if target["id"] == row["account_id"]:
            raise ValueError("a movement cannot be a transfer to its own account")
        amount = -parse_decimal(row["amount"])
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO transactions (
                       account_id, date, amount, description, status, external_id,
                       content_hash, source, source_file, raw_payload, currency,
                       created_at, mirror_of
                   ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, NULL, ?, ?, ?, ?)""",
                (
                    target["id"], row["date"], format_decimal(amount), row["description"],
                    row["status"],
                    # Out of the dedup's way: an export of this account, imported
                    # one day, must not be taken for the rule's own rows.
                    f"mirror:{transaction_id}",
                    # Where the information came from is the movement it mirrors.
                    row["source"],
                    json.dumps({"mirror_of": transaction_id}),
                    row["currency"],
                    dt.datetime.now(dt.UTC).isoformat(),
                    transaction_id,
                ),
            )
            mirror_id = int(cursor.lastrowid)
            self.conn.execute(
                "INSERT INTO postings (transaction_id, account_id, amount) VALUES (?, ?, ?)",
                (mirror_id, target["id"], format_decimal(amount)),
            )
            self.link_transfer_pair(transaction_id, mirror_id, "high", "rule")
            self.conn.execute(
                "UPDATE transfer_links SET confirmed_by_human = 1 WHERE leg_a = ? AND leg_b = ?",
                (transaction_id, mirror_id),
            )
        return mirror_id

    def mirror_of(self, transaction_id: int) -> sqlite3.Row | None:
        """The row a transfer rule wrote as this movement's other half, if any."""
        return self.conn.execute(
            """SELECT t.*, a.name AS account FROM transactions t
               JOIN accounts a ON a.id = t.account_id WHERE t.mirror_of = ?""",
            (transaction_id,),
        ).fetchone()

    def drop_mirror(self, transaction_id: int) -> None:
        """Take back the other half a transfer rule wrote, and return the movement
        to the queue.

        The half is the rule's and not a movement anybody reported, so it goes
        without a tombstone, and its link with it.
        """
        with self.conn:
            self.conn.execute("DELETE FROM transactions WHERE mirror_of = ?", (transaction_id,))
            self.set_category(transaction_id, self.uncategorized())

    def mark_passthrough(self, transaction_id: int, destination: str) -> None:
        """Declare a leg money that is not the holder's to count.

        Money moved to an own account that is not connected here, and money that
        arrives from somebody else — a co-holder's share, a reimbursement — are
        the same thing to the ledger: neither spending nor income. The
        destination becomes the virtual account the other side is recorded into,
        so the leg leaves the burn, income and the queue together.
        """
        name = destination.strip()
        if not name:
            raise ValueError("the destination needs a name")
        if name == TRANSFER_CLEARING:
            raise ValueError(f"{TRANSFER_CLEARING!r} is the pairing account, not a destination")
        if self._live_link(transaction_id) is not None:
            raise ValueError("the leg is paired with another movement: undo that link first")
        existing = self.find_account(name=name)
        if existing is not None and existing["type"] != "virtual":
            raise ValueError(
                f"{name!r} is a {existing['type']} account: link the two legs instead"
            )
        self.move_to_virtual_account(transaction_id, name)

    def mark_transfer_pair(self, leg_a: int, leg_b: int) -> None:
        """Record a pair a person decided on, marked as already reviewed.

        The guards are the automatic matcher's own rules — two real accounts,
        different ones, equal and opposite amounts, no split to lose — because a
        manual link that broke them would take money out of the burn on the
        operator's word alone.
        """
        first = self._linkable_leg(leg_a)
        second = self._linkable_leg(leg_b)
        if first["account_id"] == second["account_id"]:
            raise ValueError("the two legs sit on the same account")
        if parse_decimal(first["amount"]) + parse_decimal(second["amount"]) != 0:
            raise ValueError("the two legs do not have equal and opposite amounts")
        # Only a row for these two legs: a leg's rejection of some other pair is
        # the very mistake this call corrects, and reusing it re-confirmed it.
        link = self.conn.execute(
            """SELECT * FROM transfer_links
               WHERE (leg_a = ? AND leg_b = ?) OR (leg_a = ? AND leg_b = ?)""",
            (leg_a, leg_b, leg_b, leg_a),
        ).fetchone()
        if link is None:
            # "high" because a person is the strongest evidence there is.
            first, second, confidence, method = leg_a, leg_b, "high", "human"
        else:
            # An earlier rejection is a row already: reusing it keeps one row per
            # pair, and re-clearing the legs puts the money back where the pair
            # says — a rejected pair left them sitting on Uncategorized.
            first, second = link["leg_a"], link["leg_b"]
            confidence, method = link["confidence"], link["method"]
        self.link_transfer_pair(first, second, confidence, method)
        self.set_transfer_review(first, second, "confirm")

    def unlink_transfer(self, transaction_id: int) -> str | None:
        """Undo a transfer, giving the leg — or the pair — its category back.

        Returns the own-account name a lone leg pointed at, which the caller
        needs to warn when the configuration re-applies that label on every
        sync. Raises KeyError when there was no transfer to undo.
        """
        target = self.transfer_target(transaction_id)
        if target is None:
            raise KeyError(f"transaction {transaction_id} is not a transfer")
        link = self._live_link(transaction_id)
        if link is not None and link["method"] == "rule":
            raise ValueError(
                "a transfer rule wrote this pair: change or remove the rule, or it is "
                "written again at the next sync"
            )
        if link is not None:
            # Rejecting keeps the row: the candidate query skips any leg that
            # holds one, so the pair cannot come straight back at the next sync.
            self.set_transfer_review(link["leg_a"], link["leg_b"], "reject")
            return None
        self.set_category(transaction_id, self.uncategorized())
        return target

    def _linkable_leg(self, transaction_id: int) -> sqlite3.Row:
        """A transaction a person may declare a leg, or the reason why not."""
        row = self.conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"transaction {transaction_id} not found")
        if self.account(row["account_id"])["type"] != "real":
            raise ValueError(f"transaction {transaction_id} does not sit on a real account")
        if self.transfer_target(transaction_id) is not None:
            raise ValueError(f"transaction {transaction_id} is already a transfer")
        if len(self.splits(transaction_id)) > 1:
            raise ValueError(
                f"transaction {transaction_id} is split: linking it would drop the split"
            )
        return row
