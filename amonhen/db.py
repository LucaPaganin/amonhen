"""Ledger schema: accounts, transactions, postings, transfer links, balances."""
import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK (type IN ('real', 'virtual', 'category')),
    institution TEXT,
    iban TEXT,
    external_uid TEXT,
    currency TEXT NOT NULL DEFAULT 'EUR',
    opening_balance TEXT,
    opening_date TEXT,
    -- Category flags: a rare event is accrued instead of averaged, and an
    -- essential category is the part of spending that could not be cut.
    episodic INTEGER NOT NULL DEFAULT 0,
    essential INTEGER NOT NULL DEFAULT 0,
    -- Real-account flag: a transfer into it is savings, not spending.
    investment INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS accounts_external_uid
    ON accounts(external_uid) WHERE external_uid IS NOT NULL;

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    date TEXT NOT NULL,
    amount TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('BOOK', 'PDNG')),
    external_id TEXT,
    content_hash TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('psd2', 'import')),
    source_file TEXT,
    raw_payload TEXT NOT NULL,
    counterparty TEXT,
    counterparty_account TEXT,
    currency TEXT NOT NULL DEFAULT 'EUR',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS transactions_content_hash ON transactions(content_hash);

CREATE UNIQUE INDEX IF NOT EXISTS transactions_external_id
    ON transactions(account_id, external_id) WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS transactions_date ON transactions(date);

CREATE TABLE IF NOT EXISTS postings (
    id INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    amount TEXT NOT NULL,
    note TEXT
);

CREATE INDEX IF NOT EXISTS postings_account ON postings(account_id);

CREATE TABLE IF NOT EXISTS transfer_links (
    leg_a INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    leg_b INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    confidence TEXT NOT NULL,
    method TEXT NOT NULL,
    confirmed_by_human INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (leg_a, leg_b)
);

-- A rule is a piece of text the description contains, and the category that
-- follows from it. `key` is that text as it is matched (spaces collapsed, lower
-- case) and `pattern` keeps what a person typed, for the list.
CREATE TABLE IF NOT EXISTS rules (
    key TEXT PRIMARY KEY,
    pattern TEXT NOT NULL,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_balances (
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    date TEXT NOT NULL,
    balance TEXT NOT NULL,
    source TEXT NOT NULL,
    -- One row per declaration: the bank reports several figures for the same
    -- date (available and booked), and they have to coexist to be checked.
    PRIMARY KEY (account_id, date, source)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    category_id INTEGER PRIMARY KEY REFERENCES accounts(id),
    amount TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Proposals are never applied on their own: a classifier or an LLM writes a
-- merchant -> category pair here and a human accepts or dismisses it.
CREATE TABLE IF NOT EXISTS merchant_suggestions (
    merchant TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT 'pending'
        CHECK (decision IN ('pending', 'accepted', 'dismissed'))
);

-- Desiderata 5.9: a reading of the numbers already computed is kept with the
-- model that wrote it and the fingerprint of the data it read, so a reading can
-- be read again in six months knowing what it was based on. A refused reading
-- has no answer text and carries the reason instead: the figures a model
-- produced on its own are the thing that rule exists to catch.
CREATE TABLE IF NOT EXISTS assistant_readings (
    id INTEGER PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    model TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    refused TEXT,
    UNIQUE (question, fingerprint)
);

-- A proposal the assistant may make that is not a merchant -> category pair.
-- Like merchant_suggestions, nothing here is applied: a person decides.
CREATE TABLE IF NOT EXISTS budget_proposals (
    category TEXT PRIMARY KEY,
    amount TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT 'pending'
        CHECK (decision IN ('pending', 'accepted', 'dismissed'))
);
"""

# Columns added after the first release. A single-user local ledger does not
# need a migration framework, only a check before use.
_ADDED_COLUMNS = (
    ("accounts", "episodic", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "essential", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "investment", "INTEGER NOT NULL DEFAULT 0"),
)


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _add_missing_columns(conn)
    _migrate_rules(conn)
    _widen_balance_key(conn)
    _drop_obsolete(conn)
    conn.commit()
    _restrict_to_owner(conn)


def _migrate_rules(conn: sqlite3.Connection) -> None:
    """Move the merchant rules into the rules table, and drop the table they lived in.

    A rule used to be a merchant name matched exactly against the normalization
    of the description; it is now a piece of text the description contains, so
    the same name keeps its category and reaches the descriptions carrying it.
    The `merchants` table was the normalization cache and the rule store at
    once: the cache had no reader, so it goes with the rules.
    """
    tables = {row["name"] for row in conn.execute("PRAGMA table_list")}
    if "merchants" not in tables:
        return
    conn.execute(
        """INSERT OR IGNORE INTO rules (key, pattern, category)
           SELECT raw_pattern, normalized_name, default_category
           FROM merchants WHERE default_category IS NOT NULL AND raw_pattern <> ''"""
    )
    conn.execute("DROP TABLE merchants")


def _widen_balance_key(conn: sqlite3.Connection) -> None:
    """Let a date hold every figure the bank declared for it.

    `account_balances` was keyed by (account, date), so a booked balance
    overwrote the available one recorded minutes earlier and the two halves of
    the 5.4 assertion could never both exist. Rebuilt rather than patched: a
    primary key is not something ALTER TABLE can widen.
    """
    key = {row["name"]: row["pk"] for row in conn.execute("PRAGMA table_info(account_balances)")}
    if key.get("source") == 3:
        return
    conn.executescript(
        """
        ALTER TABLE account_balances RENAME TO account_balances_legacy;
        CREATE TABLE account_balances (
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            date TEXT NOT NULL,
            balance TEXT NOT NULL,
            source TEXT NOT NULL,
            PRIMARY KEY (account_id, date, source)
        );
        INSERT INTO account_balances (account_id, date, balance, source)
            SELECT account_id, date, balance, source FROM account_balances_legacy;
        DROP TABLE account_balances_legacy;
        """
    )


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, column, definition in _ADDED_COLUMNS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _drop_obsolete(conn: sqlite3.Connection) -> None:
    """Take out what an earlier version of this schema left behind.

    A ledger created before the balance table existed carries an unused
    ``net_worth_snapshots``, and one created before the mortgage was dropped
    still carries its setting.
    """
    conn.execute("DROP TABLE IF EXISTS net_worth_snapshots")
    conn.execute("DELETE FROM settings WHERE key = 'mortgage_monthly'")


def _restrict_to_owner(conn: sqlite3.Connection) -> None:
    """The ledger holds bank payloads, so keep it readable only by its owner."""
    for _, name, file in conn.execute("PRAGMA database_list"):
        if name == "main" and file:
            try:
                os.chmod(file, 0o600)
            except OSError:
                pass


def open_ledger_db(path: str | Path) -> sqlite3.Connection:
    conn = connect(path)
    initialize(conn)
    return conn
