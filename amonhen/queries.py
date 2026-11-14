"""The reads the screens need, written in SQL next to the ledger they read.

They used to live in the HTTP routes, where a page of movements or the review
queue was a query built inside the function that answered the request. Here each
read is a function that takes a `Ledger` and answers rows or plain values, so the
SQL that knows the schema sits with the persistence and the routes only turn the
answer into a payload. What a missing row means (a 404, a 422) stays the caller's
to say: these functions answer `None`.

Writes are not here: they keep the ledger's invariants and live on `Ledger`.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from amonhen.ledger import CREDITS_WHERE, TRANSFER_CLEARING, UNCATEGORIZED_WHERE, Ledger
from amonhen.models import parse_decimal
from amonhen.settings import UNCATEGORIZED

# -- one row ----------------------------------------------------------------------


def account(ledger: Ledger, account_id: int) -> sqlite3.Row | None:
    return ledger.conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()


def real_account(ledger: Ledger, account_id: int) -> sqlite3.Row | None:
    return ledger.conn.execute(
        "SELECT * FROM accounts WHERE id = ? AND type = 'real'", (account_id,)
    ).fetchone()


def transaction(ledger: Ledger, transaction_id: int) -> sqlite3.Row | None:
    return ledger.conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone()


def deleted_movement(ledger: Ledger, deleted_id: int) -> sqlite3.Row | None:
    return ledger.conn.execute(
        "SELECT * FROM deleted_transactions WHERE id = ?", (deleted_id,)
    ).fetchone()


def held_movement(ledger: Ledger, held_id: int) -> sqlite3.Row | None:
    """The account and day of a held probable duplicate, which its decision needs."""
    return ledger.conn.execute(
        "SELECT account_id, date FROM held_transactions WHERE id = ?", (held_id,)
    ).fetchone()


def suggestion(ledger: Ledger, merchant: str) -> sqlite3.Row | None:
    return ledger.conn.execute(
        "SELECT category FROM merchant_suggestions WHERE merchant = ?", (merchant,)
    ).fetchone()


# -- accounts and categories ---------------------------------------------------------------


def real_account_ids(ledger: Ledger) -> list[sqlite3.Row]:
    return ledger.conn.execute("SELECT id FROM accounts WHERE type = 'real' ORDER BY name").fetchall()


def posted_on(ledger: Ledger, account_id: int) -> Decimal:
    """What the postings on an account add up to, cents-exact."""
    total = Decimal(0)
    for row in ledger.conn.execute("SELECT amount FROM postings WHERE account_id = ?", (account_id,)):
        total += parse_decimal(row["amount"])
    return total


def virtual_account_usage(ledger: Ledger) -> list[sqlite3.Row]:
    """Every virtual account but the clearing one, with how many movements reach it
    and over which days."""
    return ledger.conn.execute(
        """SELECT a.id, a.name, COUNT(p.id) AS movements,
                  MIN(t.date) AS first_date, MAX(t.date) AS last_date
           FROM accounts a
           LEFT JOIN postings p ON p.account_id = a.id
           LEFT JOIN transactions t ON t.id = p.transaction_id
           WHERE a.type = 'virtual' AND a.name <> ?
           GROUP BY a.id ORDER BY a.name""",
        (TRANSFER_CLEARING,),
    ).fetchall()


def category_rows(ledger: Ledger) -> list[sqlite3.Row]:
    return ledger.conn.execute(
        "SELECT id, name, episodic, essential, income, contribution, description"
        " FROM accounts WHERE type = 'category' ORDER BY name"
    ).fetchall()


def mirror_destinations(ledger: Ledger) -> list[str]:
    """The real accounts a transfer rule may write the other half on: added by hand,
    or connected but marked as not reporting their top-ups."""
    return [
        row["name"]
        for row in ledger.conn.execute(
            """SELECT name FROM accounts WHERE type = 'real'
               AND (external_uid IS NULL OR unreported_funding = 1)
               ORDER BY name"""
        )
    ]


# -- the review queue ------------------------------------------------------------------------


def uncategorized_backlog(ledger: Ledger) -> list[sqlite3.Row]:
    """Every movement waiting in the queue, newest first.

    Three columns only: a long uncategorized history must not drag every raw
    payload into memory just to be counted.
    """
    return ledger.conn.execute(
        f"SELECT t.id, t.description, t.account_id FROM transactions t {UNCATEGORIZED_WHERE}"
        " ORDER BY t.date DESC, t.id DESC",
        (UNCATEGORIZED,),
    ).fetchall()


def queue_rows(ledger: Ledger, ids: list[int]) -> list[sqlite3.Row]:
    """The full rows for the selected ids of the queue, most recent first.

    The ids were already ordered, so this is one bounded query rather than a
    scan of the whole backlog with every raw payload attached.
    """
    if not ids:
        return []
    placeholders = ", ".join("?" * len(ids))
    return list(
        ledger.conn.execute(
            f"""SELECT t.* FROM transactions t {UNCATEGORIZED_WHERE}
                AND t.id IN ({placeholders})
                ORDER BY t.date DESC, t.id DESC""",
            (UNCATEGORIZED, *ids),
        )
    )


def backlog_accounts(ledger: Ledger) -> list[sqlite3.Row]:
    """The accounts that actually have rows in the queue, so a filter offers only
    choices that can return something."""
    return ledger.conn.execute(
        f"""SELECT DISTINCT a.id, a.name FROM transactions t
            JOIN accounts a ON a.id = t.account_id {UNCATEGORIZED_WHERE}
            ORDER BY a.name""",
        (UNCATEGORIZED,),
    ).fetchall()


def proposed_transfers(ledger: Ledger, limit: int) -> tuple[int, list[sqlite3.Row]]:
    """How many pairs wait for a person, and the newest of them."""
    total = ledger.conn.execute(
        "SELECT COUNT(*) AS c FROM transfer_links WHERE confirmed_by_human = 0"
    ).fetchone()["c"]
    links = ledger.conn.execute(
        """SELECT * FROM transfer_links WHERE confirmed_by_human = 0
           ORDER BY leg_a DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return total, links


def waiting_credits(ledger: Ledger, since: str, limit: int) -> tuple[int, list[sqlite3.Row]]:
    """How many credits from `since` on wait for a decision, and the newest of them."""
    waiting = (since, UNCATEGORIZED)
    total = ledger.conn.execute(
        f"SELECT COUNT(*) AS c FROM transactions t {CREDITS_WHERE}", waiting
    ).fetchone()["c"]
    credits = ledger.conn.execute(
        f"""SELECT t.* FROM transactions t {CREDITS_WHERE}
            ORDER BY t.date DESC, t.id DESC LIMIT ?""",
        (*waiting, limit),
    ).fetchall()
    return total, credits


# -- the list of movements -----------------------------------------------------------------


@dataclass(frozen=True)
class TransactionFilter:
    """What the list of movements is narrowed by. Every field is optional."""

    from_date: str | dt.date | None = None
    to_date: str | dt.date | None = None
    account_id: int | None = None
    category: str | None = None
    status: str | None = None
    search: str | None = None
    transfer: bool | None = None
    virtual_account_id: int | None = None
    tag: str | None = None
    amount_min: str | None = None
    amount_max: str | None = None


@dataclass(frozen=True)
class TransactionPage:
    total: int
    hidden: int
    rows: list[sqlite3.Row]


def transaction_page(
    ledger: Ledger, filters: TransactionFilter, *, everyday: bool, limit: int, offset: int
) -> TransactionPage:
    """A page of movements, newest first.

    `everyday` leaves out what only moves own money: the legs of a transfer, and
    everything on a deposit whose balance is its movements. `hidden` counts what
    that left out, so the list never looks shorter than the ledger without saying so.
    """
    where, params = _transaction_where(filters, everyday=everyday)
    count = (
        "SELECT COUNT(*) AS c FROM transactions t"
        " JOIN accounts a ON a.id = t.account_id "
    )
    total = ledger.conn.execute(count + where, params).fetchone()["c"]
    hidden = 0
    if everyday:
        unfiltered, unfiltered_params = _transaction_where(filters)
        hidden = ledger.conn.execute(count + unfiltered, unfiltered_params).fetchone()["c"] - total
    rows = ledger.conn.execute(
        f"""SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id
            {where} ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()
    return TransactionPage(total, hidden, rows)


def _transaction_where(filters: TransactionFilter, *, everyday: bool = False) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if filters.from_date:
        clauses.append("t.date >= ?")
        params.append(filters.from_date)
    if filters.to_date:
        clauses.append("t.date <= ?")
        params.append(filters.to_date)
    if filters.account_id is not None:
        clauses.append("t.account_id = ?")
        params.append(filters.account_id)
    if filters.status:
        clauses.append("t.status = ?")
        params.append(filters.status)
    if filters.category:
        clauses.append(
            """EXISTS (SELECT 1 FROM postings p JOIN accounts c ON c.id = p.account_id
                       WHERE p.transaction_id = t.id AND c.type = 'category' AND c.name = ?)"""
        )
        params.append(filters.category)
    if filters.search:
        # A note is the one word a person wrote on a movement, so a search that
        # could not find it would make marking a movement pointless.
        search = filters.search
        clauses.append("(t.description LIKE ? OR t.counterparty LIKE ? OR t.notes LIKE ?)")
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if filters.transfer is not None:
        # A leg's balancing side sits on a virtual account, so this is the same
        # test `Ledger.is_transfer` makes.
        leg = """EXISTS (SELECT 1 FROM postings p JOIN accounts v ON v.id = p.account_id
                         WHERE p.transaction_id = t.id AND v.type = 'virtual')"""
        clauses.append(leg if filters.transfer else f"NOT {leg}")
    if filters.virtual_account_id is not None:
        # The movements a virtual account holds are the ones posted to it.
        clauses.append(
            "EXISTS (SELECT 1 FROM postings p WHERE p.transaction_id = t.id AND p.account_id = ?)"
        )
        params.append(filters.virtual_account_id)
    if filters.tag:
        clauses.append(
            """EXISTS (SELECT 1 FROM transaction_tags tt JOIN tags g ON g.id = tt.tag_id
                       WHERE tt.transaction_id = t.id AND g.name = ?)"""
        )
        params.append(filters.tag)
    # A size, like a rule's conditions: both ends count, and the sign does not. The
    # bound is cast by SQLite too, so an amount typed exactly is an amount found.
    if filters.amount_min is not None:
        clauses.append("ABS(CAST(t.amount AS REAL)) >= CAST(? AS REAL)")
        params.append(filters.amount_min)
    if filters.amount_max is not None:
        clauses.append("ABS(CAST(t.amount AS REAL)) <= CAST(? AS REAL)")
        params.append(filters.amount_max)
    if everyday:
        clauses.append(
            """a.computed_balance = 0 AND NOT EXISTS (
                   SELECT 1 FROM postings p JOIN accounts v ON v.id = p.account_id
                   WHERE p.transaction_id = t.id AND v.type = 'virtual')"""
        )
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params
