"""The ledger: the single write path for accounts, transactions and postings.

Every transaction has postings that sum to zero. A spend is a posting on a real
account balanced by one on a category account; an internal transfer leg is
balanced by the transfer clearing account, which is why transfers never show up
as spending without needing a rule.
"""
import datetime as dt
import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence

from amonhen.dedup import content_hash
from amonhen.models import (
    Account,
    IncomingTransaction,
    RecordAction,
    format_decimal,
    parse_decimal,
)
from amonhen.settings import UNCATEGORIZED

# A pending row becomes the settled transaction when the bank reports the same
# amount on the same account within this many days.
PENDING_WINDOW_DAYS = 3
TRANSFER_CLEARING = "Transfer clearing"

# Settled spending still waiting in the review bucket: a real outflow, a posting
# on the `Uncategorized` category, and no leg of a transfer — linking a pair
# moves a leg's posting to the clearing account, which is virtual. The queue
# counts its rows and a proposal's stake is read with this same fragment, so the
# two can never disagree about what is still undecided.
UNCATEGORIZED_WHERE = """
    WHERE t.status = 'BOOK' AND CAST(t.amount AS REAL) < 0
    AND EXISTS (
        SELECT 1 FROM postings p JOIN accounts a ON a.id = p.account_id
        WHERE p.transaction_id = t.id AND a.type = 'category' AND a.name = ?
    )
    AND NOT EXISTS (
        SELECT 1 FROM postings p JOIN accounts a ON a.id = p.account_id
        WHERE p.transaction_id = t.id AND a.type = 'virtual'
    )"""

_TRANSACTION_COLUMNS = (
    "account_id", "date", "amount", "description", "status", "external_id",
    "content_hash", "source", "source_file", "raw_payload", "counterparty",
    "counterparty_account", "currency",
)


@dataclass(frozen=True)
class BalanceCheck:
    account_id: int
    as_of: dt.date
    opening: Decimal
    declared: Decimal
    computed: Decimal
    kind: str = "available"
    source: str = ""

    @property
    def difference(self) -> Decimal:
        return self.declared - self.computed

    @property
    def ok(self) -> bool:
        return self.difference == 0


# EB tags every balance it declares with a type, and the types fall into two
# groups that are different numbers for the same date — the ones that include
# the pending movements and the ones that leave them out. The order inside each
# group is what to prefer when the bank declares several: the interim figures
# describe now, the closing ones the end of a statement period, and a forecast
# describes a future that has not happened. The last two entries are not EB
# types: they are the words an opening we derived ourselves is tagged with, so
# that row lands in the bucket of the figure it was derived from.
BALANCE_TYPES = (
    ("ITAV", "available"), ("CLAV", "available"), ("OPAV", "available"), ("FWAV", "available"),
    ("ITBD", "booked"), ("CLBD", "booked"), ("OPBD", "booked"), ("PRCD", "booked"),
    ("AVAILABLE", "available"), ("BOOKED", "booked"),
)
BALANCE_KINDS = dict(BALANCE_TYPES)
BALANCE_TYPE_ORDER = {name: index for index, (name, _kind) in enumerate(BALANCE_TYPES)}


def balance_kind(source: str) -> str:
    """Which of the bank's two figures a declared balance is.

    Comparing a declaration against the wrong figure invents a difference that
    is exactly the pending sum, so the type decides which computed balance it is
    asserted against. Anything unrecognised — a balance a person wrote — counts
    as available, which is the figure the ledger's own arithmetic produces.
    """
    return BALANCE_KINDS.get(_balance_type(source), "available")


def _balance_type(source: str) -> str:
    """The EB type inside a `eb:<TYPE>` source tag, or "" for anything else."""
    return source.partition(":")[2].strip().upper()


def _source_priority(source: str) -> int:
    """Smaller is better; a type we do not recognise loses to every one we do."""
    return BALANCE_TYPE_ORDER.get(_balance_type(source), len(BALANCE_TYPE_ORDER))


def _declaration_order(row: sqlite3.Row) -> tuple[str, bool, int]:
    """Newest date first, then the bank's own number, then the type we trust more."""
    return (row["date"], row["source"].startswith("eb:"), -_source_priority(row["source"]))


class Ledger:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # -- accounts ----------------------------------------------------------

    def ensure_account(self, account: Account) -> int:
        row = self.conn.execute(
            "SELECT id FROM accounts WHERE name = ?", (account.name,)
        ).fetchone()
        if row is None and account.external_uid:
            row = self.conn.execute(
                "SELECT id FROM accounts WHERE external_uid = ?", (account.external_uid,)
            ).fetchone()
        if row is not None:
            self._fill_missing_fields(row["id"], account)
            return row["id"]

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

    # -- transactions ------------------------------------------------------

    def record(self, txn: IncomingTransaction, occurrence: int = 1) -> tuple[int, RecordAction]:
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
        counterpart = self._find_opposite_status(txn)
        if counterpart is not None:
            return self._merge_status_change(counterpart, txn, digest)
        return self._insert(txn, digest), "inserted"

    def record_batch(self, transactions: Iterable[IncomingTransaction]) -> dict[str, int]:
        """Record a batch, giving identical rows inside it their own identity."""
        occurrences: dict[str, int] = {}
        actions: dict[str, int] = {}
        for txn in transactions:
            key = content_hash(txn.account_id, txn.date, txn.amount, txn.description)
            occurrences[key] = occurrences.get(key, 0) + 1
            _, action = self.record(txn, occurrence=occurrences[key])
            actions[action] = actions.get(action, 0) + 1
        return actions

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

    def _absorb(self, existing: sqlite3.Row, txn: IncomingTransaction, digest: str) -> tuple[int, RecordAction]:
        if existing["status"] == "PDNG" and txn.status == "BOOK":
            return self._promote(existing, txn, digest)
        return existing["id"], "duplicate"

    def _merge_status_change(self, candidate: sqlite3.Row, txn: IncomingTransaction, digest: str) -> tuple[int, RecordAction]:
        if candidate["status"] == "PDNG" and txn.status == "BOOK":
            return self._promote(candidate, txn, digest)
        # The settled row is already recorded and this is its late pending twin.
        return candidate["id"], "duplicate"

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

    def set_category_flag(self, account_id: int, flag: str, value: bool) -> None:
        """Mark a category as episodic (accrued) or essential (not cuttable)."""
        if flag not in ("episodic", "essential"):
            raise ValueError(f"unknown category flag {flag!r}")
        if self.account(account_id)["type"] != "category":
            raise ValueError(f"account {account_id} is not a category")
        with self.conn:
            self.conn.execute(
                f"UPDATE accounts SET {flag} = ? WHERE id = ?", (1 if value else 0, account_id)
            )

    def set_investment(self, account_id: int, value: bool) -> None:
        if self.account(account_id)["type"] != "real":
            raise ValueError(f"account {account_id} is not a real account")
        with self.conn:
            self.conn.execute(
                "UPDATE accounts SET investment = ? WHERE id = ?", (1 if value else 0, account_id)
            )

    def setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO settings (key, value) VALUES (?, ?)
                   ON CONFLICT (key) DO UPDATE SET value = excluded.value""",
                (key, value),
            )

    def set_budget(self, category_id: int, amount: Decimal | None) -> None:
        """Set the monthly budget of a category; None removes it."""
        if self.account(category_id)["type"] != "category":
            raise ValueError(f"account {category_id} is not a category")
        with self.conn:
            if amount is None:
                self.conn.execute("DELETE FROM budgets WHERE category_id = ?", (category_id,))
                return
            if amount < 0:
                raise ValueError("a budget cannot be negative")
            self.conn.execute(
                """INSERT INTO budgets (category_id, amount, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT (category_id) DO UPDATE SET
                       amount = excluded.amount, updated_at = excluded.updated_at""",
                (category_id, format_decimal(amount), dt.datetime.now(dt.UTC).isoformat()),
            )

    def budget_status(self, month_start: dt.date, month_end: dt.date) -> list[dict]:
        """Per category: the monthly budget, what it has taken, what is left."""
        rows = self.conn.execute(
            """SELECT a.id, a.name, b.amount AS budget
               FROM accounts a LEFT JOIN budgets b ON b.category_id = a.id
               WHERE a.type = 'category' AND a.name != ?
               ORDER BY a.name""",
            (UNCATEGORIZED,),
        ).fetchall()
        status = []
        for row in rows:
            spent = Decimal(0)
            for posting in self.conn.execute(
                """SELECT p.amount FROM postings p
                   JOIN transactions t ON t.id = p.transaction_id
                   WHERE p.account_id = ? AND t.status = 'BOOK'
                     AND CAST(t.amount AS REAL) < 0
                     AND t.date >= ? AND t.date <= ?""",
                (row["id"], month_start.isoformat(), month_end.isoformat()),
            ):
                spent += parse_decimal(posting["amount"])
            budget = parse_decimal(row["budget"]) if row["budget"] else None
            status.append(
                {
                    "id": row["id"],
                    "category": row["name"],
                    "budget": format_decimal(budget) if budget is not None else None,
                    "spent": format_decimal(spent),
                    "remaining": format_decimal(budget - spent) if budget is not None else None,
                }
            )
        return status

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

    def record_reading(
        self,
        question: str,
        answer: str,
        model: str,
        fingerprint: str,
        refused: str | None = None,
    ) -> None:
        """Keep a reading, or the refusal of one, with what it was based on."""
        with self.conn:
            self.conn.execute(
                """INSERT INTO assistant_readings
                       (question, answer, model, fingerprint, created_at, refused)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (question, fingerprint) DO UPDATE SET
                       answer = excluded.answer,
                       model = excluded.model,
                       created_at = excluded.created_at,
                       refused = excluded.refused""",
                (
                    question,
                    answer,
                    model,
                    fingerprint,
                    dt.datetime.now().replace(microsecond=0).isoformat(sep=" "),
                    refused,
                ),
            )

    def reading(self, question: str, fingerprint: str) -> sqlite3.Row | None:
        """The answer already given to this question about this data, if any."""
        return self.conn.execute(
            """SELECT * FROM assistant_readings
               WHERE question = ? AND fingerprint = ? AND refused IS NULL""",
            (question, fingerprint),
        ).fetchone()

    def readings(self, limit: int = 10) -> list[dict]:
        """What was asked and what came back, newest first, refusals included."""
        return [
            dict(row)
            for row in self.conn.execute(
                """SELECT question, answer, model, created_at, refused
                   FROM assistant_readings ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
        ]

    def record_budget_proposal(self, category: str, amount: str, source: str) -> None:
        """Remember a proposed monthly budget; a person decides, nothing is applied."""
        with self.conn:
            self.conn.execute(
                """INSERT INTO budget_proposals (category, amount, source, created_at, decision)
                   VALUES (?, ?, ?, ?, 'pending')
                   ON CONFLICT (category) DO UPDATE SET
                       amount = excluded.amount,
                       source = excluded.source,
                       created_at = excluded.created_at,
                       decision = 'pending'""",
                (
                    category,
                    amount,
                    source,
                    dt.datetime.now().replace(microsecond=0).isoformat(sep=" "),
                ),
            )

    def budget_proposals(self, decision: str = "pending") -> list[dict]:
        return [
            dict(row)
            for row in self.conn.execute(
                """SELECT category, amount, source, created_at FROM budget_proposals
                   WHERE decision = ? ORDER BY category""",
                (decision,),
            )
        ]

    def budget_proposal(self, category: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM budget_proposals WHERE category = ?", (category,)
        ).fetchone()

    def decide_budget_proposal(self, category: str, decision: str) -> None:
        if decision not in ("accepted", "dismissed"):
            raise ValueError(f"unknown decision {decision!r}")
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE budget_proposals SET decision = ? WHERE category = ? AND decision = 'pending'",
                (decision, category),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"no budget proposal for {category!r}")

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
               AND account_id IN (SELECT id FROM accounts WHERE type = 'category')""",
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
        """The recorded link this leg belongs to, whichever side it is."""
        return self.conn.execute(
            """SELECT * FROM transfer_links
               WHERE leg_a = ? OR leg_b = ? ORDER BY leg_a LIMIT 1""",
            (transaction_id, transaction_id),
        ).fetchone()

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
        link = self.transfer_link(transaction_id)
        if link is None:
            return {
                "kind": "pair" if target == TRANSFER_CLEARING else "passthrough",
                "target": target,
                "state": "confirmed",
                "leg_id": None,
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
        if self.transfer_link(transaction_id) is not None:
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
        link = self.transfer_link(leg_a)
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
        link = self.transfer_link(transaction_id)
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

    # -- invariants and reporting -----------------------------------------

    def unbalanced(self) -> list[int]:
        totals: dict[int, Decimal] = {}
        counts: dict[int, int] = {}
        for row in self.conn.execute("SELECT transaction_id, amount FROM postings"):
            totals[row["transaction_id"]] = totals.get(row["transaction_id"], Decimal(0)) + parse_decimal(row["amount"])
            counts[row["transaction_id"]] = counts.get(row["transaction_id"], 0) + 1
        ids = set(totals) | set(counts) | {row["id"] for row in self.conn.execute("SELECT id FROM transactions")}
        return sorted(
            tid for tid in ids
            if totals.get(tid, Decimal(0)) != 0 or counts.get(tid, 0) < 2
        )

    def validate(self) -> None:
        broken = self.unbalanced()
        if broken:
            raise ValueError(f"transactions whose postings do not sum to zero: {broken}")

    def spend_between(self, start: dt.date, end: dt.date) -> Decimal:
        """Money actually spent in the period: category postings, so transfers are out.

        Only transactions that moved money out of an account count, so incoming
        payments do not net against spending. Refunds are phase 3 work.
        """
        total = Decimal(0)
        for row in self.conn.execute(
            """SELECT p.amount FROM postings p
               JOIN transactions t ON t.id = p.transaction_id
               JOIN accounts a ON a.id = p.account_id
               WHERE a.type = 'category' AND t.status = 'BOOK'
                 AND CAST(t.amount AS REAL) < 0
                 AND t.date >= ? AND t.date <= ?""",
            (start.isoformat(), end.isoformat()),
        ):
            total += parse_decimal(row["amount"])
        return total

    def movement(self, account_id: int, as_of: dt.date, *, settled: bool = False) -> Decimal:
        """Sum of the postings on the account up to the date, opening excluded.

        `settled=True` leaves the pending movements out — the same split the two
        declared figures make. An opening derived from one of them has to be
        derived with the postings that figure contains, or the pending sum ends
        up folded into the opening.
        """
        return self._postings_sum(account_id, as_of, settled=settled)

    def balance(self, account_id: int, as_of: dt.date, *, settled: bool = False) -> Decimal:
        """What the account holds on the date, by the ledger's own arithmetic.

        The bank declares two figures for the same date and they differ by the
        pending movements: `settled=False` counts them, matching its *available*
        balance, while `settled=True` leaves them out for its *booked* one.
        """
        account = self.account(account_id)
        opening = parse_decimal(account["opening_balance"]) if account["opening_balance"] else Decimal(0)
        return opening + self._postings_sum(
            account_id, as_of, after=account["opening_date"], settled=settled
        )

    def _postings_sum(self, account_id: int, as_of: dt.date, *, after: str | None = None,
                      settled: bool = False) -> Decimal:
        """The postings up to the date, optionally only those after an opening date.

        One query behind both figures, so `movement` and `balance` cannot drift
        apart: the invariant is their difference, and it is nonsense if the two
        sides count different movements.
        """
        total = Decimal(0)
        for row in self.conn.execute(
            """SELECT p.amount FROM postings p
               JOIN transactions t ON t.id = p.transaction_id
               WHERE p.account_id = ? AND t.date <= ?
                 AND (? IS NULL OR t.date > ?)
                 AND (? = 0 OR t.status = 'BOOK')""",
            (account_id, as_of.isoformat(), after, after, 1 if settled else 0),
        ):
            total += parse_decimal(row["amount"])
        return total

    def check_balance(
        self,
        account_id: int,
        declared: Decimal,
        as_of: dt.date,
        *,
        kind: str = "available",
        source: str = "",
    ) -> BalanceCheck:
        account = self.account(account_id)
        opening = parse_decimal(account["opening_balance"]) if account["opening_balance"] else Decimal(0)
        return BalanceCheck(
            account_id=account_id,
            as_of=as_of,
            opening=opening,
            declared=declared,
            computed=self.balance(account_id, as_of, settled=kind == "booked"),
            kind=kind,
            source=source,
        )

    def declarations(self, account_id: int, as_of: dt.date | None = None) -> list[sqlite3.Row]:
        """Every balance declared for the account, optionally up to a date."""
        sql = "SELECT date, balance, source FROM account_balances WHERE account_id = ?"
        params: list = [account_id]
        if as_of is not None:
            sql += " AND date <= ?"
            params.append(as_of.isoformat())
        return list(self.conn.execute(sql, params))

    def declaration_for(self, account_id: int, as_of: dt.date) -> sqlite3.Row | None:
        """The declaration to assert against for that date: the newest, deterministically."""
        rows = self.declarations(account_id, as_of)
        return max(rows, key=_declaration_order) if rows else None

    def declared_checks(self, account_id: int) -> list[BalanceCheck]:
        """The newest declaration of each kind, each against the figure that means the same.

        One check per kind at most, and never a choice between two rows of the
        same date made by row order: that is what turned a booked balance into a
        difference the size of the pending movements.
        """
        newest: dict[str, sqlite3.Row] = {}
        for row in self.declarations(account_id):
            kind = balance_kind(row["source"])
            if kind not in newest or _declaration_order(row) > _declaration_order(newest[kind]):
                newest[kind] = row
        return [
            self.check_balance(
                account_id,
                parse_decimal(row["balance"]),
                dt.date.fromisoformat(row["date"]),
                kind=kind,
                source=row["source"],
            )
            for kind, row in sorted(newest.items())
        ]

    def record_declared_balance(self, account_id: int, date: dt.date, balance: Decimal, source: str) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO account_balances (account_id, date, balance, source)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (account_id, date, source) DO UPDATE SET
                       balance = excluded.balance""",
                (account_id, date.isoformat(), format_decimal(balance), source),
            )

    def anchor_opening(
        self, account_id: int, as_of: dt.date, declared: Decimal, kind: str
    ) -> tuple[Decimal, dt.date]:
        """Set the opening so the declared figure holds on the date it refers to.

        Everything the bank reported up to then is already inside the declared
        balance — the pending movements only if the declared figure contains them
        too, which is what ``kind`` says. The movement is opening-independent, so
        anchoring twice changes nothing.

        ``opening_balance`` is the balance *before* ``opening_date`` and
        ``balance()`` adds only the postings strictly after it, so the opening is
        dated the day before the first movement. Returns what it wrote, because
        the command line and the app both print it.
        """
        opening = declared - self.movement(account_id, as_of, settled=kind == "booked")
        first = self.conn.execute(
            "SELECT MIN(date) AS first FROM transactions WHERE account_id = ? AND date <= ?",
            (account_id, as_of.isoformat()),
        ).fetchone()["first"]
        opening_date = dt.date.fromisoformat(first) - dt.timedelta(days=1) if first else as_of
        with self.conn:
            self.conn.execute(
                "UPDATE accounts SET opening_balance = ?, opening_date = ? WHERE id = ?",
                (format_decimal(opening), opening_date.isoformat(), account_id),
            )
        return opening, opening_date
