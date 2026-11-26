"""Ledger schema: accounts, transactions, postings, transfer links, balances, budgets."""
import datetime as dt
import json
import os
import sqlite3
from contextlib import contextmanager, nullcontext
from pathlib import Path

from amonhen.settings import UNCATEGORIZED

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
    -- Money in on an income category is income; on any other it is a refund.
    income INTEGER NOT NULL DEFAULT 0,
    -- Money in on a contribution category covers every expense: it takes the
    -- total down and no category with it.
    contribution INTEGER NOT NULL DEFAULT 0,
    -- What a category is about, in a person's words.
    description TEXT,
    -- Real-account flag: the broker, whose cash is declared by hand.
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
-- What a sync, a probable duplicate and the movements filtered by account read:
-- one account's rows over some days. With the date index alone SQLite walked every
-- account's rows of those days; this one also answers the newest day of an account
-- without reading a row.
CREATE INDEX IF NOT EXISTS transactions_account_date ON transactions(account_id, date);

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
CREATE INDEX IF NOT EXISTS postings_transaction ON postings(transaction_id);

CREATE TABLE IF NOT EXISTS transfer_links (
    leg_a INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    leg_b INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    confidence TEXT NOT NULL,
    method TEXT NOT NULL,
    confirmed_by_human INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (leg_a, leg_b)
);
CREATE INDEX IF NOT EXISTS transfer_links_leg_b ON transfer_links(leg_b);

-- A rule is a piece of text the description contains, the conditions that
-- narrow it (an account, a range of amounts), and what follows from it: a
-- category, a deletion, a transfer to a destination, or a tag. `key` is the text
-- as it is matched (spaces collapsed, lower case) and `pattern` keeps what a
-- person typed, for the list. `target` is the category, the destination or the
-- tag, NULL for a deletion. One rule per text and conditions, and one per tag
-- among the tag rules, which add up instead of competing: the unique index is in
-- `_allow_tag_rules`, because it needs the columns a ledger written before them
-- does not have yet.
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL,
    pattern TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'category'
        CHECK (action IN ('category', 'delete', 'transfer', 'tag')),
    target TEXT,
    account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
    amount_min TEXT,
    amount_max TEXT
);

-- Desiderata 5.13. A tag is a free label on a movement, which keeps its category.
-- It may carry the same two flags a category does, and every reading asks one
-- predicate (`ledger.RARE_SQL`, `ledger.ESSENTIAL_SQL`), so a tag is not a second
-- concept of rare: it is the same question asked of the movement.
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    episodic INTEGER NOT NULL DEFAULT 0,
    essential INTEGER NOT NULL DEFAULT 0
);

-- `by_rule` is who put it there: removing a rule takes back what the rule wrote,
-- and a tag a person wrote stays.
CREATE TABLE IF NOT EXISTS transaction_tags (
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    by_rule INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (transaction_id, tag_id)
);

CREATE INDEX IF NOT EXISTS transaction_tags_tag ON transaction_tags(tag_id);

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
    -- NULL while the expense waits for a category: it can be written first.
    category_id INTEGER REFERENCES accounts(id),
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

-- Desiderata 5.16. A goal is one row per version: changing it on a day closes the
-- row there (`valid_to`) and opens another in the same `series`, like a budget
-- default, so a plan reopened on a past day shows the goals it had then.
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY,
    series INTEGER,
    name TEXT NOT NULL,
    amount TEXT NOT NULL,
    target_date TEXT NOT NULL,
    liquidity TEXT NOT NULL CHECK (liquidity IN ('liquida', 'alla_data', 'vincolabile')),
    valid_from TEXT NOT NULL,
    valid_to TEXT
);

-- The facts the ledger cannot see (gross, the base of the fund contribution, the
-- rates), each true from a day on until the next row of the same key.
CREATE TABLE IF NOT EXISTS profile_facts (
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    PRIMARY KEY (key, valid_from)
);

-- One tax year, written by hand with where each value comes from. A missing year
-- is said, never filled from the year before.
CREATE TABLE IF NOT EXISTS tax_parameters (
    year INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source <> ''),
    PRIMARY KEY (year, key)
);

-- The three scenarios a projection runs under, written by hand: a yearly real
-- return and the inflation beside it. Never estimated from the past, and an
-- absent one is said, not replaced.
CREATE TABLE IF NOT EXISTS scenarios (
    name TEXT PRIMARY KEY CHECK (name IN ('prudente', 'centrale', 'favorevole')),
    real_return TEXT NOT NULL,
    inflation TEXT NOT NULL
);

-- Desiderata 5.16, the portfolio. It lives outside the ledger and writes no posting,
-- so spending, runway and the 5.4 check cannot see market noise (docs/investments.md).
-- `terms` holds what one instrument needs and the others do not (a BTP's nominal,
-- start, rates, tax and bonus), as written text.
CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('etf', 'btp', 'fondo_pensione', 'immobile')),
    isin TEXT,
    class TEXT,
    source TEXT NOT NULL,
    ownership TEXT NOT NULL DEFAULT '1',
    horizon TEXT,
    terms TEXT
);

CREATE TABLE IF NOT EXISTS instrument_trades (
    id INTEGER PRIMARY KEY,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    units TEXT NOT NULL,
    price TEXT NOT NULL,
    amount TEXT NOT NULL,
    fees TEXT NOT NULL DEFAULT '0.00',
    source TEXT NOT NULL,
    reference TEXT NOT NULL,
    UNIQUE (instrument_id, source, reference)
);

-- A contribution to the pension fund is born withheld (from a payslip, valued at cost
-- as money in transit) and becomes invested when a statement shows its value date,
-- unit value and units; a payment made straight to the fund is born invested.
CREATE TABLE IF NOT EXISTS pension_contributions (
    id INTEGER PRIMARY KEY,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    period TEXT NOT NULL,
    own TEXT NOT NULL,
    employer TEXT NOT NULL,
    tfr TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('trattenuto', 'investito')),
    payslip TEXT,
    value_date TEXT,
    unit_value TEXT,
    units TEXT,
    UNIQUE (instrument_id, payslip)
);

-- One value per instrument and month end, with where it came from.
CREATE TABLE IF NOT EXISTS prices (
    instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (instrument_id, date)
);

-- The month-end series: units, value, and what was paid in net of what came back.
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    month TEXT NOT NULL,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    units TEXT NOT NULL,
    value TEXT NOT NULL,
    paid TEXT NOT NULL,
    PRIMARY KEY (month, instrument_id)
);

-- A document read from Paperless, once: the id is Paperless's own, and a document
-- already here is never read again, whatever its outcome, even when the write-back
-- of that outcome moves its modification date.
CREATE TABLE IF NOT EXISTS documents (
    paperless_id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    read_at TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('importato', 'errore')),
    layout TEXT,
    error TEXT
);

-- A movement and the document that justifies it (fattura, ricevuta, bolletta)
-- read from Paperless: the id is Paperless's, the rest is a snapshot so the
-- movement can show its paperwork without asking Paperless again.
CREATE TABLE IF NOT EXISTS transaction_documents (
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    paperless_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    created TEXT,
    kind TEXT,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (transaction_id, paperless_id)
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

-- Desiderata 5.17: a service with an agreed price, given or received, whose
-- sessions are events on a Google calendar. The ledger's movements stay what
-- they are: a service only reads them, through the payments linked below.
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('lezione', 'seduta', 'altro')),
    direction TEXT NOT NULL CHECK (direction IN ('entrata', 'uscita')),
    -- Unsigned, cents-exact text, like every amount: the price of a new session.
    rate TEXT NOT NULL,
    calendar_id TEXT NOT NULL,
    -- The event title: a text the title carries, case-insensitive, or `/an expression/`.
    title_pattern TEXT NOT NULL,
    -- The text a movement's description carries to pay this service; NULL links
    -- payments by hand only.
    match_text TEXT,
    -- How the price is charged: `sessione` (a flat price, whatever the length)
    -- or `ora` (the price times the event's hours, `default_hours` when the
    -- event carries no end).
    billing TEXT NOT NULL DEFAULT 'sessione',
    default_hours TEXT NOT NULL DEFAULT '1.00',
    -- How far this service's calendar is read, when it is not the ledger's own
    -- default (`CALENDAR_LOOKBACK_DAYS`, `CALENDAR_AHEAD_DAYS`).
    lookback_days INTEGER,
    ahead_days INTEGER,
    active INTEGER NOT NULL DEFAULT 1
);

-- One row per calendar event a service's title matched, keyed by Google's
-- event id (the instance id for a recurring one). The sync writes start and
-- summary; amount is the rate when first seen, and a person may change it.
CREATE TABLE IF NOT EXISTS service_sessions (
    event_id TEXT PRIMARY KEY,
    service_id INTEGER NOT NULL REFERENCES services(id),
    start TEXT NOT NULL,
    "end" TEXT,
    summary TEXT NOT NULL,
    -- The length the calendar gave, in hours; NULL when the event has no end.
    hours TEXT,
    amount TEXT NOT NULL,
    -- 1 when a person corrected the amount: a duration change must not undo it.
    amount_by_hand INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('valida', 'annullata')),
    synced_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS service_sessions_service ON service_sessions(service_id, start);

-- A session closed by hand, with no movement behind it: cash that never reached
-- the bank, a lesson that did not happen, an agreement. The note is not optional:
-- with no payment to read, it is the only thing that explains why the session
-- stopped being owed.
CREATE TABLE IF NOT EXISTS service_closures (
    event_id TEXT PRIMARY KEY REFERENCES service_sessions(event_id) ON DELETE CASCADE,
    note TEXT NOT NULL,
    closed_at TEXT NOT NULL
);

-- Which movement pays which service. `by_rule` says a sync linked it from the
-- service's text; a link made by hand (0) is never undone by a sync. A deleted
-- movement takes its link with it; restored, the rule links it again.
CREATE TABLE IF NOT EXISTS service_payments (
    transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
    service_id INTEGER NOT NULL REFERENCES services(id),
    by_rule INTEGER NOT NULL DEFAULT 0
);
"""

# Columns added after the first release. A single-user local ledger does not
# need a migration framework, only a check before use.
_ADDED_COLUMNS = (
    ("accounts", "episodic", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "essential", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "investment", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "contribution", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "description", "TEXT"),
    ("transactions", "notes", "TEXT"),
    ("accounts", "reimport_deleted", "INTEGER NOT NULL DEFAULT 0"),
    # An account no bank reports a balance for — a deposit only reachable
    # through the movements to and from it — is worth what its postings say.
    ("accounts", "computed_balance", "INTEGER NOT NULL DEFAULT 0"),
    # A connected wallet that reports a purchase but not the money that paid for
    # it (PayPal on a card): a transfer rule may write that half on it.
    ("accounts", "unreported_funding", "INTEGER NOT NULL DEFAULT 0"),
    # The movement this row is the other half of, written by a transfer rule
    # towards an account added by hand: no bank prints this side, so the rule
    # does, and the row goes when the movement it mirrors goes.
    ("transactions", "mirror_of", "INTEGER REFERENCES transactions(id) ON DELETE CASCADE"),
    # The tags a person wrote on a deleted movement, as a JSON list: like the
    # note, they are the one thing the bank cannot send back.
    ("deleted_transactions", "tags", "TEXT"),
    # What a payment's description must carry to belong to a service, and how
    # far that service's calendar is read: both are per service, not per ledger.
    ("services", "match_text", "TEXT"),
    ("services", "lookback_days", "INTEGER"),
    ("services", "ahead_days", "INTEGER"),
    # A service may charge by the hour, where the event's own length is the
    # quantity billed: the price stays per hour, the session keeps its hours.
    ("services", "billing", "TEXT NOT NULL DEFAULT 'sessione'"),
    ("services", "default_hours", "TEXT NOT NULL DEFAULT '1.00'"),
    ("service_sessions", "end", "TEXT"),
    ("service_sessions", "hours", "TEXT"),
    ("service_sessions", "amount_by_hand", "INTEGER NOT NULL DEFAULT 0"),
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
    """Bring the file to the schema this code reads.

    Two kinds of work. At every start, the checks that cost nothing: the tables
    and indexes (`IF NOT EXISTS`), the columns added over time, and the file's
    permissions. Once per ledger, the migrations that rebuild a table or rewrite
    data, in `MIGRATIONS`: `PRAGMA user_version` counts how many of them this file
    has had, so a restart runs none of them, and a ledger written by an older
    release (version 0) runs each once, in the order they were written. Every
    migration still checks what it finds, so a file that already had one is left
    as it is; and a file newer than this code (a rollback) is left alone.
    """
    conn.executescript(SCHEMA)
    _add_missing_columns(conn)
    applied = conn.execute("PRAGMA user_version").fetchone()[0]
    for migration in MIGRATIONS[applied:]:
        migration(conn)
    if applied < len(MIGRATIONS):
        conn.execute(f"PRAGMA user_version = {len(MIGRATIONS)}")
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


def _allow_tag_rules(conn: sqlite3.Connection) -> None:
    """Let a rule put a tag, and let tag rules share a text with any other rule.

    The action is under a CHECK, which ALTER TABLE cannot widen, so the table is
    rebuilt and every rule keeps its id. A tag adds to what a text already does:
    the index keys a tag rule by its tag too, so "euronics" can assign a category
    and a tag at once, while the other actions stay one rule per text and
    conditions.
    """
    definition = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'rules'"
    ).fetchone()["sql"]
    if "'tag'" not in definition:
        conn.executescript(
            """
            ALTER TABLE rules RENAME TO rules_legacy;
            CREATE TABLE rules (
                id INTEGER PRIMARY KEY,
                key TEXT NOT NULL,
                pattern TEXT NOT NULL,
                action TEXT NOT NULL DEFAULT 'category'
                    CHECK (action IN ('category', 'delete', 'transfer', 'tag')),
                target TEXT,
                account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
                amount_min TEXT,
                amount_max TEXT
            );
            INSERT INTO rules (id, key, pattern, action, target, account_id, amount_min, amount_max)
                SELECT id, key, pattern, action, target, account_id, amount_min, amount_max
                FROM rules_legacy;
            DROP TABLE rules_legacy;
            """
        )
    # Every start and every sync pass come through here, the server's two at the
    # same moment: an index already in its final shape is left alone, or the two
    # race between the drop and the create and the sync dies on it.
    index = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'rules_identity'"
    ).fetchone()
    if index is not None and "'tag'" in index["sql"]:
        return
    conn.execute("DROP INDEX IF EXISTS rules_identity")
    conn.execute(
        """CREATE UNIQUE INDEX rules_identity ON rules (
               key, COALESCE(account_id, 0), COALESCE(amount_min, ''), COALESCE(amount_max, ''),
               CASE action WHEN 'tag' THEN target ELSE '' END
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


def _unassigned_budget_items(conn: sqlite3.Connection) -> None:
    """Let a planned expense exist before its category does.

    `category_id` was NOT NULL, and SQLite cannot drop a constraint in place:
    the table is rebuilt with the same rows and ids.
    """
    column = next(
        (row for row in conn.execute("PRAGMA table_info(budget_items)") if row["name"] == "category_id"),
        None,
    )
    if column is None or not column["notnull"]:
        return
    conn.executescript(
        """
        ALTER TABLE budget_items RENAME TO budget_items_legacy;
        DROP INDEX IF EXISTS budget_items_month;
        CREATE TABLE budget_items (
            id INTEGER PRIMARY KEY,
            category_id INTEGER REFERENCES accounts(id),
            month TEXT NOT NULL,
            description TEXT NOT NULL,
            amount TEXT NOT NULL,
            date TEXT,
            priority TEXT NOT NULL CHECK (priority IN ('essential', 'important', 'deferrable')),
            note TEXT,
            created_at TEXT NOT NULL
        );
        INSERT INTO budget_items
            SELECT id, category_id, month, description, amount, date, priority, note, created_at
            FROM budget_items_legacy;
        DROP TABLE budget_items_legacy;
        CREATE INDEX IF NOT EXISTS budget_items_month ON budget_items(month, category_id);
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


def _add_income_flag(conn: sqlite3.Connection) -> None:
    """Say which categories are income, once, from what they already hold.

    A category with money in and none out has only ever been income. Marked here
    and not left to a person, because from this version an unmarked category
    counts its credits as refunds: the first start would take every salary off
    the spending. The server and its sync loop open the ledger together, so the
    one that loses the race on the column has nothing left to do.
    """
    if any(row["name"] == "income" for row in conn.execute("PRAGMA table_info(accounts)")):
        return
    try:
        conn.execute("ALTER TABLE accounts ADD COLUMN income INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError as exc:
        if "duplicate column" in str(exc):
            return
        raise
    conn.execute(
        """UPDATE accounts SET income = 1
           WHERE type = 'category' AND name <> ?
             AND EXISTS (SELECT 1 FROM postings p JOIN transactions t ON t.id = p.transaction_id
                          WHERE p.account_id = accounts.id AND CAST(t.amount AS REAL) > 0)
             AND NOT EXISTS (SELECT 1 FROM postings p JOIN transactions t ON t.id = p.transaction_id
                              WHERE p.account_id = accounts.id AND CAST(t.amount AS REAL) < 0)""",
        (UNCATEGORIZED,),
    )


def _describe_bare_codes(conn: sqlite3.Connection) -> None:
    """Re-describe the movements whose description was a bare bank code.

    PayPal's movements arrived described as `PAYMENT`, the code every one of
    them carries, while the shop or the person was in the counterparty. The
    normalizer now prefers the counterparty; the rows written before are
    re-derived from their own payload, and the hash follows the description (a
    suffixed hash keeps its suffix). Idempotent: a row re-described no longer
    matches its code.
    """
    from amonhen.dedup import content_hash
    from amonhen.models import parse_decimal
    from amonhen.adapters.enable_banking.normalize import describe

    rows = conn.execute(
        """SELECT id, account_id, date, amount, description, content_hash, counterparty, raw_payload
           FROM transactions
           WHERE source = 'psd2' AND raw_payload IS NOT NULL AND json_valid(raw_payload)
             AND description = json_extract(raw_payload, '$.bank_transaction_code.code')"""
    ).fetchall()
    for row in rows:
        try:
            raw = json.loads(row["raw_payload"])
        except ValueError:
            continue
        description = describe(raw, row["counterparty"] or "")
        if description == row["description"]:
            continue
        digest = content_hash(
            row["account_id"],
            dt.date.fromisoformat(row["date"]),
            parse_decimal(row["amount"]),
            description,
        )
        _, colon, suffix = row["content_hash"].partition(":")
        if colon:
            digest = f"{digest}:{suffix}"
        conn.execute(
            "UPDATE transactions SET description = ?, content_hash = ? WHERE id = ?",
            (description, digest, row["id"]),
        )


def _drop_obsolete(conn: sqlite3.Connection) -> None:
    """Take out what an earlier version of this schema left behind.

    A ledger created before the balance table existed carries an unused
    ``net_worth_snapshots``, and one created before the mortgage was dropped
    still carries its setting. The assistant left two tables and its daily count
    of calls.
    """
    conn.execute("DROP TABLE IF EXISTS net_worth_snapshots")
    conn.execute("DROP TABLE IF EXISTS assistant_readings")
    conn.execute("DROP TABLE IF EXISTS budget_proposals")
    conn.execute("DELETE FROM settings WHERE key = 'mortgage_monthly'")
    conn.execute("DELETE FROM settings WHERE key LIKE 'assistant_calls:%'")


def _restrict_to_owner(conn: sqlite3.Connection) -> None:
    """The ledger holds bank payloads, so keep it readable only by its owner."""
    for _, name, file in conn.execute("PRAGMA database_list"):
        if name == "main" and file:
            try:
                os.chmod(file, 0o600)
            except OSError:
                pass


def _rename_payment_flag(conn: sqlite3.Connection) -> None:
    """The flag that tells a link by rule from a link by hand, said honestly.

    It counted links made from the counterparty's IBAN; the rule is a text in the
    description now, so the column is `by_rule`. The values mean the same thing.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(service_payments)")}
    if "by_iban" in columns and "by_rule" not in columns:
        conn.execute("ALTER TABLE service_payments RENAME COLUMN by_iban TO by_rule")


# The migrations, in the order they were written; a new one goes at the end, and
# none is ever removed or moved, because its position is the version it brings a
# ledger to.
MIGRATIONS = (
    _add_income_flag,
    _migrate_rules,
    _generalize_rules,
    _allow_tag_rules,
    _widen_balance_key,
    _date_budgets,
    _unassigned_budget_items,
    _drop_obsolete,
    _describe_bare_codes,
    _rename_payment_flag,
)


def open_ledger_db(path: str | Path) -> sqlite3.Connection:
    conn = connect(path)
    initialize(conn)
    return conn
