"""Schema upgrades: a ledger already in use has to come out the other side whole."""
import datetime as dt
from decimal import Decimal

from amonhen.db import connect, initialize


def test_a_date_can_hold_every_figure_the_bank_declared_for_it(tmp_path):
    """The two halves of the 5.4 assertion are different numbers for one date."""
    path = tmp_path / "legacy.db"
    conn = connect(path)
    initialize(conn)
    account = conn.execute(
        "INSERT INTO accounts (name, type) VALUES ('Revolut personale', 'real')"
    ).lastrowid
    # The same ledger as it was written before the key was widened.
    conn.executescript(
        """
        DROP TABLE account_balances;
        CREATE TABLE account_balances (
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            date TEXT NOT NULL,
            balance TEXT NOT NULL,
            source TEXT NOT NULL,
            PRIMARY KEY (account_id, date)
        );
        """
    )
    conn.execute("INSERT INTO account_balances VALUES (?, '2026-09-12', '67.56', 'eb:ITAV')", (account,))
    conn.commit()

    initialize(conn)

    key = {row["name"]: row["pk"] for row in conn.execute("PRAGMA table_info(account_balances)")}
    assert key["source"] == 3
    # What was recorded before the upgrade is still there.
    assert [tuple(row) for row in conn.execute("SELECT * FROM account_balances")] == [
        (account, "2026-09-12", "67.56", "eb:ITAV")
    ]

    # And the booked figure for the same date now fits next to the available one.
    conn.execute("INSERT INTO account_balances VALUES (?, '2026-09-12', '101.52', 'eb:ITBD')", (account,))
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM account_balances").fetchone()[0] == 2
    conn.close()


def test_a_ledger_written_before_the_note_gains_the_column(tmp_path):
    """The operator's ledger exists before this column does.

    A fresh database gets `notes` from the schema; one already in use only gets
    it from the added-columns pass, and without that the app would fail on the
    real ledger with "no such column: notes".
    """
    from amonhen.ledger import Ledger

    path = tmp_path / "legacy-notes.db"
    conn = connect(path)
    initialize(conn)
    # The tables as an earlier version wrote them: the same movement, no note,
    # and an account that cannot yet say whether deleted movements come back.
    conn.executescript(
        """
        DROP TABLE transactions;
        DROP TABLE accounts;
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL CHECK (type IN ('real', 'virtual', 'category')),
            institution TEXT,
            iban TEXT,
            external_uid TEXT,
            currency TEXT NOT NULL DEFAULT 'EUR',
            opening_balance TEXT,
            opening_date TEXT,
            episodic INTEGER NOT NULL DEFAULT 0,
            essential INTEGER NOT NULL DEFAULT 0,
            investment INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE transactions (
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
        """
    )
    # Written the way the old code could write it: the ledger the operator has
    # cannot be written by today's `record`, which already reads both columns.
    account = conn.execute(
        "INSERT INTO accounts (name, type) VALUES ('Revolut', 'real')"
    ).lastrowid
    transaction_id = conn.execute(
        """INSERT INTO transactions
               (account_id, date, amount, description, status, content_hash, source, raw_payload, created_at)
           VALUES (?, '2026-01-05', '-42.50', 'Ekom', 'BOOK', 'hash-1', 'psd2', '{}', '2026-01-05T00:00:00') """,
        (account,),
    ).lastrowid
    conn.commit()

    initialize(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(transactions)")}
    assert "notes" in columns
    account_columns = {row["name"] for row in conn.execute("PRAGMA table_info(accounts)")}
    assert "reimport_deleted" in account_columns
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    # The movement that was already there came through untouched.
    assert (row["description"], row["amount"], row["notes"]) == ("Ekom", "-42.50", None)

    # And the writes the app needs now work on it: the note, and the flag that
    # decides whether a deletion here can come back.
    ledger = Ledger(conn)
    ledger.set_notes(transaction_id, "nota su un ledger vecchio")
    ledger.set_reimport_deleted(account, True)
    assert conn.execute("SELECT notes FROM transactions").fetchone()["notes"] == (
        "nota su un ledger vecchio"
    )
    assert ledger.deleted_total(account, dt.date(2026, 1, 31), "available").count == 0
    conn.close()


def test_the_merchant_rules_survive_as_patterns(tmp_path):
    """A rule used to be a merchant name; the descriptions have to keep reaching it."""
    path = tmp_path / "legacy-rules.db"
    conn = connect(path)
    initialize(conn)
    # The rules table as an earlier version wrote it: the normalization cache,
    # with the rule hanging off the row the merchant name was keyed by.
    conn.executescript(
        """
        DROP TABLE rules;
        CREATE TABLE merchants (
            raw_pattern TEXT PRIMARY KEY,
            normalized_name TEXT NOT NULL,
            default_category TEXT
        );
        INSERT INTO merchants VALUES
            ('ekom', 'EKOM', 'Groceries'),
            ('bar centrale', 'Bar Centrale', NULL),
            ('', '', 'Spesa');
        """
    )
    conn.commit()

    initialize(conn)

    # The blank key came from a rule added before the pattern had to be a text;
    # the new code refuses to create one, so it is not carried over.
    assert [tuple(row) for row in conn.execute("SELECT key, pattern, category FROM rules")] == [
        ("ekom", "EKOM", "Groceries")
    ]
    assert not list(conn.execute("SELECT name FROM sqlite_master WHERE name = 'merchants'"))

    # Running it again neither duplicates the rule nor needs the old table.
    initialize(conn)

    assert conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 1
    conn.close()


def test_a_legacy_rule_shadowed_by_a_longer_text_hands_its_movement_over(tmp_path):
    """Keys matched exactly once; as substrings a longer one can decide instead."""
    from amonhen.ledger import Ledger
    from amonhen.merchants import RuleBook, categorize, rule_usage
    from amonhen.models import Account, IncomingTransaction

    path = tmp_path / "legacy-shadow.db"
    conn = connect(path)
    initialize(conn)
    ledger = Ledger(conn)
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    movement = ledger.record(
        IncomingTransaction(
            account_id=account,
            date=dt.date(2026, 8, 3),
            amount=Decimal("-42.50"),
            description="EKOM | Cart",
            status="BOOK",
            source="import",
            balancing_account_id=ledger.category("Groceries"),
            raw={},
        )
    )[0]
    # The rules as an earlier version wrote them: `ekom` held this movement, and
    # `cart` was a rule for another description that happens to sit inside it.
    conn.executescript(
        """
        DROP TABLE rules;
        CREATE TABLE merchants (
            raw_pattern TEXT PRIMARY KEY,
            normalized_name TEXT NOT NULL,
            default_category TEXT
        );
        INSERT INTO merchants VALUES
            ('ekom', 'EKOM', 'Groceries'),
            ('cart', 'Cart', 'Household');
        """
    )
    conn.commit()

    initialize(conn)
    book = RuleBook(conn)

    # `cart` decides it now (same length, earlier alphabetically), and a movement
    # cannot stay on the category of the rule that lost it: the weight would read
    # zero and the rule would look dead while still holding it.
    assert categorize(ledger, book) == 1
    assert ledger.category_of(movement) == "Household"
    assert rule_usage(ledger, book.rules()) == {"cart": 1}

    # And removing the winning rule gives it back to the one that still matches.
    assert book.remove_rule("cart", ledger) == 1
    assert ledger.category_of(movement) == "Groceries"
