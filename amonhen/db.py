"""Ledger schema: accounts, transactions, postings, transfer links, balances, budgets."""
import os
import sqlite3
from contextlib import contextmanager, nullcontext
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
    created_at TEXT NOT NULL,
    -- A note a person wrote on this movement. It is local: the bank never
    -- sends one, and no ingest path writes this column, which is why a sync
    -- cannot overwrite what someone wrote.
    notes TEXT
);

CREATE INDEX IF NOT EXISTS transactions_content_hash ON transactions(content_hash);

CREATE UNIQUE INDEX IF NOT EXISTS transactions_external_id
    ON transactions(account_id, external_id) WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS transactions_date ON transactions(date);

-- A movement a person deleted. The row is copied here whole — payload, note and
-- the identity the ledger deduplicates by — and this is what keeps the next sync
-- from putting it back: without it a delete would be undone by the following
-- run, which is why deleting used to mean editing the database by hand.
CREATE TABLE IF NOT EXISTS deleted_transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    -- The identity the ledger dedupes by: the bank's own id when the row had
    -- one, otherwise the content hash exactly as the row carried it (suffixes
    -- for repeated identical content included), so two identical movements on
    -- one day stay distinguishable here too.
    key TEXT NOT NULL,
    date TEXT NOT NULL,
    amount TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    external_id TEXT,
    content_hash TEXT NOT NULL,
    source TEXT NOT NULL,
    source_file TEXT,
    raw_payload TEXT NOT NULL,
    counterparty TEXT,
    counterparty_account TEXT,
    currency TEXT NOT NULL,
    notes TEXT,
    deleted_at TEXT NOT NULL,
    -- Set when the movement came back, by the account's own flag or by hand.
    restored_at TEXT,
    UNIQUE (account_id, key)
);

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

-- A rule is a piece of text the description contains, the conditions that
-- narrow it (an account, a range of amounts), and what follows from it: a
-- category, a deletion, or a transfer to a destination. `key` is the text as it
-- is matched (spaces collapsed, lower case) and `pattern` keeps what a person
-- typed, for the list. `target` is the category or the destination, NULL for a
-- deletion. One rule per text and conditions: the unique index is in
-- `_generalize_rules`, because it needs the columns a ledger written before
-- them does not have yet.
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL,
    pattern TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'category'
        CHECK (action IN ('category', 'delete', 'transfer')),
    target TEXT,
    account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
    amount_min TEXT,
    amount_max TEXT
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

-- Desiderata 5.12. A category's default ceiling holds from `from_month` (YYYY-MM)
-- until the next row, so changing it never rewrites a month already lived; a
-- NULL amount removes the default from that month on. One month may override
-- the default for itself, and the items are the expenses planned inside it.
CREATE TABLE IF NOT EXISTS budgets (
    category_id INTEGER NOT NULL REFERENCES accounts(id),
    from_month TEXT NOT NULL,
    amount TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (category_id, from_month)
);

CREATE TABLE IF NOT EXISTS budget_months (
    category_id INTEGER NOT NULL REFERENCES accounts(id),
    month TEXT NOT NULL,
    amount TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (category_id, month)
);

CREATE TABLE IF NOT EXISTS budget_items (
    id INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES accounts(id),
    month TEXT NOT NULL,
    description TEXT NOT NULL,
    amount TEXT NOT NULL,
    date TEXT,
    priority TEXT NOT NULL CHECK (priority IN ('essential', 'important', 'deferrable')),
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS budget_items_month ON budget_items(month, category_id);

-- A movement a period sync did not write because the ledger already holds one
-- on the same account, day and amount that came from the other ingest path
-- under a different description: the content hash cannot tell a re-worded
-- duplicate from a second movement, so a person does, one by one. `key` is the
-- identity the ledger would have written it under (the bank's id, or the
-- content hash with its occurrence), so running the same period again holds
-- nothing twice and asks nothing already answered.
CREATE TABLE IF NOT EXISTS held_transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    key TEXT NOT NULL,
    occurrence INTEGER NOT NULL,
    date TEXT NOT NULL,
    amount TEXT NOT NULL,
    description TEXT NOT NULL,
    movement TEXT NOT NULL,
    twin_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT 'pending'
        CHECK (decision IN ('pending', 'written', 'discarded')),
    UNIQUE (account_id, key)
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
    ("transactions", "notes", "TEXT"),
    ("accounts", "reimport_deleted", "INTEGER NOT NULL DEFAULT 0"),
    # An account no bank reports a balance for — a deposit only reachable
    # through the movements to and from it — is worth what its postings say.
    ("accounts", "computed_balance", "INTEGER NOT NULL DEFAULT 0"),
    # The movement this row is the other half of, written by a transfer rule
    # towards an account added by hand: no bank prints this side, so the rule
    # does, and the row goes when the movement it mirrors goes.
    ("transactions", "mirror_of", "INTEGER REFERENCES transactions(id) ON DELETE CASCADE"),
)


class LedgerConnection(sqlite3.Connection):
    """A connection whose commits a batch can hold back until it ends.

    The ledger writes each movement inside its own ``with conn:``, which is right
    for one movement and ruinous for a sync: on the NAS's btrfs every commit is a
    flush to disk, and the first sync of 750 movements took five and a half
    minutes holding the lock the whole time. Inside ``deferred_commits`` the inner
    blocks neither commit nor roll back; the batch commits once at its end, and an
    error anywhere rolls back the whole batch rather than leaving half of it.
    """

    _deferred = 0

    def __exit__(self, exc_type, exc, tb):
        if self._deferred:
            return False
        return super().__exit__(exc_type, exc, tb)

    def commit(self) -> None:
        if self._deferred:
            return
        super().commit()

    @contextmanager
    def deferred_commits(self):
        self._deferred += 1
        try:
            yield
        except BaseException:
            self._deferred -= 1
            if not self._deferred:
                self.rollback()
            raise
        self._deferred -= 1
        if not self._deferred:
            super().commit()


def deferred_commits(conn: sqlite3.Connection):
    """One transaction for everything inside, on a connection ``connect`` made.

    A plain ``sqlite3.Connection`` (a test that built its own) keeps its commits.
    """
    if isinstance(conn, LedgerConnection):
        return conn.deferred_commits()
    return nullcontext()


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the ledger with the settings the server and the CLI share.

    WAL lets the app keep reading while a sync writes — with the rollback journal
    every commit locked readers out, and a page opened during the first sync
    answered 500 with "database is locked" — and ``synchronous = NORMAL`` is the
    setting WAL is designed for: a commit no longer waits on a flush, which only
    the checkpoint does, and a power cut can lose the last commits but never
    corrupt the file. The journal mode is stored in the file, so the WAL files
    (``-wal``, ``-shm``) sit beside the ledger from the first connection on.
    """
    conn = sqlite3.connect(str(path), factory=LedgerConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _add_missing_columns(conn)
    _migrate_rules(conn)
    _generalize_rules(conn)
    _widen_balance_key(conn)
    _date_budgets(conn)
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
    # A ledger old enough to hold `merchants` may have had no rules table, in
    # which case the schema has just created the general one.
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(rules)")}
    target = "target" if "target" in columns else "category"
    conn.execute(
        f"""INSERT OR IGNORE INTO rules (key, pattern, {target})
           SELECT raw_pattern, normalized_name, default_category
           FROM merchants WHERE default_category IS NOT NULL AND raw_pattern <> ''"""
    )
    conn.execute("DROP TABLE merchants")


def _generalize_rules(conn: sqlite3.Connection) -> None:
    """Give a rule an action and conditions, keeping every rule it already had.

    A rule was a text and a category, keyed by the text. It can now delete or
    move to a destination, and be narrowed to an account or a range of amounts,
    so the same text may hold several rules and the key moves to an id. Every old
    rule becomes a category rule with no condition: it decides what it decided.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(rules)")}
    if "action" not in columns:
        conn.executescript(
            """
            ALTER TABLE rules RENAME TO rules_legacy;
            CREATE TABLE rules (
                id INTEGER PRIMARY KEY,
                key TEXT NOT NULL,
                pattern TEXT NOT NULL,
                action TEXT NOT NULL DEFAULT 'category'
                    CHECK (action IN ('category', 'delete', 'transfer')),
                target TEXT,
                account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
                amount_min TEXT,
                amount_max TEXT
            );
            INSERT INTO rules (key, pattern, action, target)
                SELECT key, pattern, 'category', category FROM rules_legacy;
            DROP TABLE rules_legacy;
            """
        )
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS rules_identity ON rules (
               key, COALESCE(account_id, 0), COALESCE(amount_min, ''), COALESCE(amount_max, '')
           )"""
    )


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


def _date_budgets(conn: sqlite3.Connection) -> None:
    """Turn the single budget per category into a default that has always held.

    A budget was one amount for every month, keyed by category alone. Rebuilt
    rather than patched, like the balance key: each old amount becomes a default
    valid from `0000-00`, which every YYYY-MM compares greater than, so every
    month reads what it read before.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(budgets)")}
    if "from_month" in columns:
        return
    conn.executescript(
        """
        ALTER TABLE budgets RENAME TO budgets_legacy;
        CREATE TABLE budgets (
            category_id INTEGER NOT NULL REFERENCES accounts(id),
            from_month TEXT NOT NULL,
            amount TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (category_id, from_month)
        );
        INSERT INTO budgets (category_id, from_month, amount, updated_at)
            SELECT category_id, '0000-00', amount, updated_at FROM budgets_legacy;
        DROP TABLE budgets_legacy;
        """
    )


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, column, definition in _ADDED_COLUMNS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS transactions_mirror_of ON transactions(mirror_of)"
        " WHERE mirror_of IS NOT NULL"
    )


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
