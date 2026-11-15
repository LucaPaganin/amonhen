"""Accounts and categories: creating, finding, renaming and flagging them, and the settings."""
from __future__ import annotations

import sqlite3
from dataclasses import replace

from amonhen.db import deferred_commits
from amonhen.ledger.definitions import TRANSFER_CLEARING, log
from amonhen.models import Account, format_decimal
from amonhen.settings import UNCATEGORIZED


class AccountsMixin:
    """Accounts and categories: creating, finding, renaming and flagging them, and the settings.

    One part of `Ledger`, which composes them: the methods use `self.conn` and call
    each other through `self`, whatever part they are in."""

    # -- accounts ----------------------------------------------------------

    def ensure_account(self, account: Account) -> int:
        """The ledger's id for the account, created on first sight.

        A connected account is found by its uid before its name: the name is what
        a person chose in `accounts.json` and may change, the uid never does.
        Looking by name first kept the first name for good, and a rename to a
        name another account had held sent the movements into that account. A
        name found on a row that belongs to another uid is not this account: the
        new one is numbered instead (names are unique), and a rename to a name in
        use is left undone — a sync must not stop over a name.
        """
        row = None
        if account.external_uid:
            row = self.conn.execute(
                "SELECT id, name FROM accounts WHERE external_uid = ?", (account.external_uid,)
            ).fetchone()
            if row is not None and row["name"] != account.name:
                try:
                    self.rename_account(row["id"], account.name)
                except ValueError as exc:
                    log.warning("account %s keeps its name: %s", row["name"], exc)
        if row is None:
            row = self.conn.execute(
                "SELECT id FROM accounts WHERE name = ? AND (? IS NULL OR external_uid IS NULL"
                " OR external_uid = '')",
                (account.name, account.external_uid),
            ).fetchone()
        if row is not None:
            self._fill_missing_fields(row["id"], account)
            return row["id"]

        name, number = account.name, 1
        while self.find_account(name=name) is not None:
            number += 1
            name = f"{account.name} {number}"
        if name != account.name:
            log.warning("the name %s belongs to another account: recorded as %s", account.name, name)
        account = replace(account, name=name)
        cursor = self.conn.execute(
            """INSERT INTO accounts (name, type, institution, iban, external_uid, currency,
                                     opening_balance, opening_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                account.name, account.type, account.institution, account.iban,
                account.external_uid, account.currency,
                format_decimal(account.opening_balance) if account.opening_balance is not None else None,
                account.opening_date.isoformat() if account.opening_date else None,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def rename_account(self, account_id: int, name: str) -> None:
        """Give a real account another name, and the transfer rules that name it with it.

        A name any other account holds is refused. A transfer rule names its
        destination, not its id: left behind, the next pass would find no real
        account by the old name, take the halves off this account and record the
        legs on a new virtual account under the old name — what `rename_category`
        already prevents for a category.
        """
        wanted = name.strip()
        if not wanted:
            raise ValueError("the account name is empty")
        row = self.account(account_id)
        if row["type"] != "real":
            raise ValueError("only a real account is renamed here")
        other = self.find_account(name=wanted)
        if other is not None and other["id"] != account_id:
            raise ValueError(f"another account is already called {wanted!r}")
        with self.conn:
            self.conn.execute("UPDATE accounts SET name = ? WHERE id = ?", (wanted, account_id))
            self.conn.execute(
                "UPDATE rules SET target = ? WHERE action = 'transfer' AND target = ?",
                (wanted, row["name"]),
            )

    def _fill_missing_fields(self, account_id: int, account: Account) -> None:
        updates = {
            "institution": account.institution,
            "iban": account.iban,
            "external_uid": account.external_uid,
            "currency": account.currency,
        }
        for column, value in updates.items():
            if value:
                self.conn.execute(
                    f"UPDATE accounts SET {column} = ? WHERE id = ? AND ({column} IS NULL OR {column} = '')",
                    (value, account_id),
                )
        self.conn.commit()

    def account(self, account_id: int) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            raise KeyError(f"account {account_id} not found")
        return row

    def find_account(self, *, name: str | None = None, iban: str | None = None,
                     external_uid: str | None = None) -> sqlite3.Row | None:
        for column, value in (("name", name), ("iban", iban), ("external_uid", external_uid)):
            if value:
                row = self.conn.execute(
                    f"SELECT * FROM accounts WHERE {column} = ?", (value,)
                ).fetchone()
                if row is not None:
                    return row
        return None

    def category(self, name: str) -> int:
        """The category account with this name, created if it does not exist.

        A name already used by a real or virtual account is refused: returning
        it would let a rule or a picker post to something that is not a
        category, and the posting would then fail halfway through.
        """
        if not name or not name.strip():
            raise ValueError("a category needs a name")
        existing = self.conn.execute(
            "SELECT id, type FROM accounts WHERE name = ?", (name,)
        ).fetchone()
        if existing is not None:
            if existing["type"] != "category":
                raise ValueError(f"{name!r} is a {existing['type']} account, not a category")
            return existing["id"]
        return self.ensure_account(Account(name=name, type="category"))

    def uncategorized(self) -> int:
        return self.category(UNCATEGORIZED)

    def transfer_account(self) -> int:
        return self.ensure_account(Account(name=TRANSFER_CLEARING, type="virtual"))

    def delete_account(self, account_id: int) -> int:
        """Take a real account out of the ledger, with everything that hangs on it.

        Its movements, its trash, the balances the bank declared for it and the
        rules narrowed to it all go: the account is not suspended, it is gone, and
        nothing is kept to restore. The other leg of a transfer it took part in is
        not deleted — that money did leave or reach another account — so the pair
        is rejected first and the leg goes back to the queue, as when one leg is
        deleted by hand. Returns how many movements went with it.
        """
        row = self.account(account_id)
        if row["type"] != "real":
            raise ValueError(f"{row['name']!r} is not a real account: only those are deleted here")
        ids = [
            item["id"]
            for item in self.conn.execute(
                "SELECT id FROM transactions WHERE account_id = ?", (account_id,)
            )
        ]
        with deferred_commits(self.conn):
            for transaction_id in ids:
                link = self.transfer_link(transaction_id)
                if link is not None and link["confirmed_by_human"] != -1:
                    self.set_transfer_review(link["leg_a"], link["leg_b"], "reject")
            with self.conn:
                self.conn.execute("DELETE FROM transactions WHERE account_id = ?", (account_id,))
                # A posting on this account from another movement would leave
                # that movement unbalanced; nothing writes one, and if something
                # ever did the delete must stop rather than break the ledger.
                stray = self.conn.execute(
                    "SELECT COUNT(*) FROM postings WHERE account_id = ?", (account_id,)
                ).fetchone()[0]
                if stray:
                    raise ValueError(f"{stray} postings of other movements sit on this account")
                for table in ("deleted_transactions", "held_transactions",
                              "account_balances", "rules"):
                    self.conn.execute(f"DELETE FROM {table} WHERE account_id = ?", (account_id,))
                # A transfer rule towards this account would recreate it as a
                # virtual one at the next sync.
                self.conn.execute(
                    "DELETE FROM rules WHERE action = 'transfer' AND target = ?", (row["name"],)
                )
                self.conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return len(ids)

    def set_category_flag(self, account_id: int, flag: str, value: bool) -> None:
        """Mark a category as episodic (accrued), essential (not cuttable), income
        (money in on it is income, not a refund) or contribution (money in on it
        covers every expense).

        A contribution is a kind of its own, so turning it on clears the other
        flags and turning one of them on clears it. The review bucket cannot be
        one: everything waiting there would count as money received.
        """
        if flag not in ("episodic", "essential", "income", "contribution"):
            raise ValueError(f"unknown category flag {flag!r}")
        row = self.account(account_id)
        if row["type"] != "category":
            raise ValueError(f"account {account_id} is not a category")
        if flag == "contribution" and value and row["name"] == UNCATEGORIZED:
            raise ValueError("the review category cannot hold contributions")
        with self.conn:
            self.conn.execute(
                f"UPDATE accounts SET {flag} = ? WHERE id = ?", (1 if value else 0, account_id)
            )
            if value and flag == "contribution":
                self.conn.execute(
                    "UPDATE accounts SET episodic = 0, essential = 0, income = 0 WHERE id = ?",
                    (account_id,),
                )
            elif value:
                self.conn.execute(
                    "UPDATE accounts SET contribution = 0 WHERE id = ?", (account_id,)
                )

    def rename_category(self, account_id: int, name: str) -> None:
        """Give a category another name, and everything that names it with it.

        A posting points at the account's id, but a rule and a proposal hold the
        name: left behind, the next `categorize` would create the old name again
        and move the rule's movements back into it. The review bucket keeps its
        name, because the whole ledger finds it by that name.
        """
        wanted = name.strip()
        row = self.account(account_id)
        if row["type"] != "category":
            raise ValueError(f"account {account_id} is not a category")
        if row["name"] == UNCATEGORIZED:
            raise ValueError("the review category keeps its name")
        if not wanted:
            raise ValueError("a category needs a name")
        other = self.find_account(name=wanted)
        if other is not None and other["id"] != account_id:
            raise ValueError(f"another account is already called {wanted!r}")
        old = row["name"]
        with self.conn:
            self.conn.execute("UPDATE accounts SET name = ? WHERE id = ?", (wanted, account_id))
            self.conn.execute(
                "UPDATE rules SET target = ? WHERE action = 'category' AND target = ?", (wanted, old)
            )
            self.conn.execute(
                "UPDATE merchant_suggestions SET category = ? WHERE category = ?", (wanted, old)
            )

    def set_category_description(self, account_id: int, text: str) -> None:
        """Say what a category is about; an empty text removes it."""
        if self.account(account_id)["type"] != "category":
            raise ValueError(f"account {account_id} is not a category")
        with self.conn:
            self.conn.execute(
                "UPDATE accounts SET description = ? WHERE id = ?",
                (text.strip() or None, account_id),
            )

    def set_investment(self, account_id: int, value: bool) -> None:
        if self.account(account_id)["type"] != "real":
            raise ValueError(f"account {account_id} is not a real account")
        with self.conn:
            self.conn.execute(
                "UPDATE accounts SET investment = ? WHERE id = ?", (1 if value else 0, account_id)
            )

    def set_computed_balance(self, account_id: int, value: bool) -> None:
        """Whether the net worth reads this account's balance from its postings.

        For an account no bank declares a balance for — a deposit whose only
        movements are the transfers a rule writes — the observed series has
        nothing to observe, and its money would be missing from the net worth.
        A declaration made on it still checks the computed figure (section 5.4).
        """
        if self.account(account_id)["type"] != "real":
            raise ValueError(f"account {account_id} is not a real account")
        with self.conn:
            self.conn.execute(
                "UPDATE accounts SET computed_balance = ? WHERE id = ?",
                (1 if value else 0, account_id),
            )

    def set_unreported_funding(self, account_id: int, value: bool) -> None:
        """Whether a transfer rule may write the other half on this connected account.

        PayPal reports a purchase paid with a card but never the money the card
        put in, so the purchase arrives twice — on PayPal and on the card's bank —
        and nothing pairs two debits. With this on, a transfer rule on the bank's
        side towards this account writes the missing credit (`mirror_transfer`),
        exactly as it does for an account added by hand. It is a statement about
        what the bank sends, so it is a person's to make. Turning it off leaves
        the halves already written to the rules that wrote them.
        """
        if self.account(account_id)["type"] != "real":
            raise ValueError(f"account {account_id} is not a real account")
        with self.conn:
            self.conn.execute(
                "UPDATE accounts SET unreported_funding = ? WHERE id = ?",
                (1 if value else 0, account_id),
            )

    def setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_reimport_deleted(self, account_id: int, value: bool) -> None:
        """Whether this account takes back the movements a person deleted.

        Off, which is what deleting means; on, the next sync writes them in
        again from the tombstone, note included. Per account because the reason
        to turn it on is one account's own history — a consent renewed, a period
        deleted by mistake — not a property of the ledger.
        """
        if self.account(account_id)["type"] != "real":
            raise ValueError(f"account {account_id} is not a real account")
        with self.conn:
            self.conn.execute(
                "UPDATE accounts SET reimport_deleted = ? WHERE id = ?",
                (1 if value else 0, account_id),
            )

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO settings (key, value) VALUES (?, ?)
                   ON CONFLICT (key) DO UPDATE SET value = excluded.value""",
                (key, value),
            )
