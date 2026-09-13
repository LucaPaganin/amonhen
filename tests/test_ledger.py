"""Ledger invariants: balanced postings, idempotent ingest, spend and balances."""
import datetime as dt
from decimal import Decimal

import pytest

from amonhen.models import Account, IncomingTransaction

JAN = dt.date(2026, 1, 1)


def make_txn(ledger, account_id, date, amount, description, *, status="BOOK",
             external_id=None, balancing=None, source="psd2"):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(date),
        amount=Decimal(amount),
        description=description,
        status=status,
        source=source,
        balancing_account_id=balancing or ledger.uncategorized(),
        external_id=external_id,
        raw={"description": description},
    )


def test_postings_sum_to_zero(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))

    transaction_id, action = ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "ACME Srl"))

    assert action == "inserted"
    ledger.validate()
    postings = ledger.conn.execute(
        "SELECT amount FROM postings WHERE transaction_id = ?", (transaction_id,)
    ).fetchall()
    assert sum(Decimal(row["amount"]) for row in postings) == 0


def test_reimporting_the_same_period_does_not_duplicate(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    rows = [
        make_txn(ledger, account, "2026-01-05", "-42.50", "ACME Srl", external_id="e1"),
        make_txn(ledger, account, "2026-01-06", "-3.94", "Bar", external_id="e2"),
        make_txn(ledger, account, "2026-01-07", "1200.00", "Salary", external_id="e3"),
    ]
    for row in rows:
        ledger.record(row)

    actions = [ledger.record(row)[1] for row in rows]

    assert actions == ["duplicate", "duplicate", "duplicate"]
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 3


def test_import_overlap_matches_the_synced_row_by_content_hash(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", external_id="e1"))

    transaction_id, action = ledger.record(
        make_txn(ledger, account, "2026-01-05", "-42.50", "  ekom ", source="import")
    )

    assert action == "duplicate"
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 1


def test_pending_is_promoted_to_booked_without_a_second_row(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-01-10", "-12.30", "Netflix",
                           status="PDNG", external_id="p1"))

    transaction_id, action = ledger.record(
        make_txn(ledger, account, "2026-01-12", "-12.30", "NETFLIX.COM", external_id="b1")
    )

    assert action == "promoted"
    row = ledger.conn.execute("SELECT * FROM transactions").fetchone()
    assert row["id"] == transaction_id
    assert row["status"] == "BOOK"
    assert row["date"] == "2026-01-12"
    assert row["external_id"] == "b1"
    ledger.validate()


def test_late_pending_twin_after_the_booked_row_is_ignored(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-01-12", "-12.30", "NETFLIX.COM", external_id="b1"))

    _, action = ledger.record(make_txn(ledger, account, "2026-01-10", "-12.30", "Netflix",
                                       status="PDNG", external_id="p1"))

    assert action == "duplicate"
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 1


def test_two_distinct_transactions_with_the_same_amount_are_kept(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-01-13", "-12.30", "Spotify", external_id="s1"))

    _, action = ledger.record(make_txn(ledger, account, "2026-01-13", "-12.30", "Coffee", external_id="c1"))

    assert action == "inserted"
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 2


def test_identical_content_with_different_provider_ids_is_not_collapsed(ledger):
    """Four identical top-ups on one day happen; the hash must not drop three."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    rows = [
        make_txn(ledger, account, "2026-08-29", "250.00", "From Giulia B", external_id=f"r{n}")
        for n in range(4)
    ]

    actions = [ledger.record(row)[1] for row in rows]

    assert actions == ["inserted"] * 4
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 4


def test_identical_content_without_provider_ids_is_collapsed(ledger):
    """Without a provider id the content hash is the only discriminator."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    row = make_txn(ledger, account, "2026-08-29", "250.00", "From Giulia B")

    first, second = ledger.record(row), ledger.record(row)

    assert first[1] == "inserted"
    assert second[1] == "duplicate"
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 1


def test_spend_counts_category_postings_and_ignores_pending(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "ACME Srl"))
    ledger.record(make_txn(ledger, account, "2026-01-06", "-7.50", "Bar", status="PDNG"))

    total = ledger.spend_between(dt.date(2026, 1, 1), dt.date(2026, 1, 31))

    assert total == Decimal("42.50")


def test_balance_check_uses_the_opening_balance(ledger):
    account = ledger.ensure_account(
        Account(name="Revolut", type="real", opening_balance=Decimal("100.00"), opening_date=JAN)
    )
    ledger.record(make_txn(ledger, account, "2026-01-05", "-30.00", "ACME Srl"))
    ledger.record(make_txn(ledger, account, "2026-01-06", "10.00", "Refund"))

    check = ledger.check_balance(account, Decimal("80.00"), dt.date(2026, 2, 1))

    assert check.computed == Decimal("80.00")
    assert check.ok
    assert check.difference == 0


def test_balance_check_reports_the_difference(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real", opening_balance=Decimal("0.00")))
    ledger.record(make_txn(ledger, account, "2026-01-05", "-30.00", "ACME Srl"))

    check = ledger.check_balance(account, Decimal("0.00"), dt.date(2026, 2, 1))

    assert not check.ok
    assert check.difference == Decimal("30.00")


def test_declared_balances_are_upserted(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))

    ledger.record_declared_balance(account, JAN, Decimal("10.00"), "manual")
    ledger.record_declared_balance(account, JAN, Decimal("11.00"), "manual")

    row = ledger.conn.execute("SELECT balance FROM account_balances").fetchone()
    assert row["balance"] == "11.00"


def test_the_available_and_booked_figures_are_checked_against_their_own_number(ledger):
    """EB declares two numbers for one date; each is asserted against its own."""
    account = ledger.ensure_account(
        Account(name="Revolut", type="real", opening_balance=Decimal("100.00"), opening_date=JAN)
    )
    ledger.record(make_txn(ledger, account, "2026-01-05", "-30.00", "ACME Srl"))
    pending, _ = ledger.record(make_txn(ledger, account, "2026-01-06", "-20.00", "Bar Centrale"))
    ledger.conn.execute("UPDATE transactions SET status = 'PDNG' WHERE id = ?", (pending,))

    ledger.record_declared_balance(account, dt.date(2026, 1, 31), Decimal("50.00"), "eb:ITAV")
    ledger.record_declared_balance(account, dt.date(2026, 1, 31), Decimal("70.00"), "eb:ITBD")

    checks = {check.kind: check for check in ledger.declared_checks(account)}

    assert checks["available"].computed == Decimal("50.00")
    assert checks["booked"].computed == Decimal("70.00")
    assert [check.ok for check in checks.values()] == [True, True]


def test_a_wrong_declaration_says_which_figure_does_not_match(ledger):
    """The point of two assertions: knowing whether to look at the pending rows."""
    account = ledger.ensure_account(
        Account(name="Revolut", type="real", opening_balance=Decimal("100.00"), opening_date=JAN)
    )
    ledger.record(make_txn(ledger, account, "2026-01-05", "-30.00", "ACME Srl"))
    pending, _ = ledger.record(make_txn(ledger, account, "2026-01-06", "-20.00", "Bar Centrale"))
    ledger.conn.execute("UPDATE transactions SET status = 'PDNG' WHERE id = ?", (pending,))

    ledger.record_declared_balance(account, dt.date(2026, 1, 31), Decimal("60.00"), "eb:ITAV")
    ledger.record_declared_balance(account, dt.date(2026, 1, 31), Decimal("70.00"), "eb:ITBD")

    failed = [check for check in ledger.declared_checks(account) if not check.ok]

    assert [(check.kind, check.difference) for check in failed] == [("available", Decimal("10.00"))]


def test_a_hand_written_balance_never_displaces_the_banks_own_on_the_same_date(ledger):
    """Which row is compared must not depend on the order SQLite returns them in."""
    account = ledger.ensure_account(Account(name="Revolut", type="real", opening_balance=Decimal("70.00")))
    same_day = dt.date(2026, 1, 31)
    ledger.record_declared_balance(account, same_day, Decimal("999.00"), "manual")
    ledger.record_declared_balance(account, same_day, Decimal("70.00"), "eb:ITAV")

    row = ledger.declaration_for(account, same_day)

    assert (row["source"], row["balance"]) == ("eb:ITAV", "70.00")
    checks = ledger.declared_checks(account)
    assert [(check.kind, check.source, check.ok) for check in checks] == [("available", "eb:ITAV", True)]


def test_the_figure_we_trust_more_wins_when_the_bank_declares_two_of_a_kind(ledger):
    """A forecast is not the balance of today, and it must not displace the ITAV."""
    account = ledger.ensure_account(Account(name="Revolut", type="real", opening_balance=Decimal("70.00")))
    same_day = dt.date(2026, 1, 31)
    ledger.record_declared_balance(account, same_day, Decimal("999.00"), "eb:XPCD")
    ledger.record_declared_balance(account, same_day, Decimal("70.00"), "eb:ITAV")

    assert ledger.declaration_for(account, same_day)["source"] == "eb:ITAV"
    assert [
        (check.source, check.kind, check.ok) for check in ledger.declared_checks(account)
    ] == [("eb:ITAV", "available", True)]


def test_validate_detects_a_broken_transaction(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.conn.execute(
        "INSERT INTO transactions (account_id, date, amount, description, status, content_hash,"
        " source, raw_payload, created_at) VALUES (?, '2026-01-05', '-5.00', 'x', 'BOOK', 'h',"
        " 'psd2', '{}', '2026-01-05T00:00:00')",
        (account,),
    )
    ledger.conn.execute(
        "INSERT INTO postings (transaction_id, account_id, amount) VALUES (last_insert_rowid(), ?, '-5.00')",
        (account,),
    )
    ledger.conn.commit()

    with pytest.raises(ValueError, match="do not sum to zero"):
        ledger.validate()


def test_a_split_balances_the_transaction(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    household = ledger.category("Household")
    transaction_id, _ = ledger.record(make_txn(ledger, account, "2026-01-05", "-100.00", "Superstore"))

    # Category postings carry the opposite sign of the real account: +100 here.
    ledger.set_splits(transaction_id, [(groceries, Decimal("70.00")), (household, Decimal("30.00"))])

    ledger.validate()
    splits = {row["name"]: row["amount"] for row in ledger.splits(transaction_id)}
    assert splits == {"Groceries": "70.00", "Household": "30.00"}
    assert ledger.spend_between(dt.date(2026, 1, 1), dt.date(2026, 1, 31)) == Decimal("100.00")


def test_a_split_that_does_not_balance_is_refused(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    transaction_id, _ = ledger.record(make_txn(ledger, account, "2026-01-05", "-100.00", "Superstore"))

    with pytest.raises(ValueError, match="does not balance"):
        ledger.set_splits(transaction_id, [(groceries, Decimal("90.00"))])

    assert ledger.category_of(transaction_id) == "Uncategorized"


def test_a_split_needs_categories(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(make_txn(ledger, account, "2026-01-05", "-100.00", "Superstore"))

    with pytest.raises(ValueError, match="not a category"):
        ledger.set_splits(transaction_id, [(account, Decimal("100.00"))])


def test_splitting_replaces_a_single_category(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(make_txn(ledger, account, "2026-01-05", "-100.00", "Superstore"))
    ledger.set_category(transaction_id, ledger.category("Groceries"))

    ledger.set_splits(transaction_id, [(ledger.category("Household"), Decimal("100.00"))])

    assert [row["name"] for row in ledger.splits(transaction_id)] == ["Household"]
    ledger.validate()


def test_category_flags_and_settings_round_trip(ledger):
    groceries = ledger.category("Groceries")

    ledger.set_category_flag(groceries, "episodic", True)
    ledger.set_category_flag(groceries, "essential", True)
    ledger.set_setting("some_key", "800.00")

    row = ledger.account(groceries)
    assert row["episodic"] == 1 and row["essential"] == 1
    assert ledger.setting("some_key") == "800.00"
    assert ledger.setting("missing", "fallback") == "fallback"


def test_flags_are_refused_on_the_wrong_account_type(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))

    with pytest.raises(ValueError, match="not a category"):
        ledger.set_category_flag(account, "episodic", True)
    with pytest.raises(ValueError, match="not a real account"):
        ledger.set_investment(ledger.category("Groceries"), True)


def test_a_category_name_cannot_collide_with_another_account(ledger):
    ledger.ensure_account(Account(name="Revolut", type="real"))

    with pytest.raises(ValueError, match="not a category"):
        ledger.category("Revolut")


def test_a_category_needs_a_name(ledger):
    with pytest.raises(ValueError, match="needs a name"):
        ledger.category("")
    with pytest.raises(ValueError, match="needs a name"):
        ledger.category("   ")


def test_budget_status_reports_spent_and_remaining(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "EKOM"))
    ledger.set_category(1, groceries)
    ledger.set_budget(groceries, Decimal("100.00"))

    status = {row["category"]: row for row in ledger.budget_status(JAN, dt.date(2026, 1, 31))}

    assert status["Groceries"]["budget"] == "100.00"
    assert status["Groceries"]["spent"] == "42.50"
    assert status["Groceries"]["remaining"] == "57.50"


def test_a_budget_can_be_cleared_and_must_be_a_category(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    ledger.set_budget(groceries, Decimal("100.00"))

    ledger.set_budget(groceries, None)

    status = {row["category"]: row for row in ledger.budget_status(JAN, dt.date(2026, 1, 31))}
    assert status["Groceries"]["budget"] is None
    with pytest.raises(ValueError, match="not a category"):
        ledger.set_budget(account, Decimal("10.00"))
    with pytest.raises(ValueError, match="cannot be negative"):
        ledger.set_budget(groceries, Decimal("-1.00"))


def test_suggestions_are_recorded_pending_and_decided(ledger):
    ledger.record_suggestion("EKOM", "Groceries", "classifier")

    pending = ledger.suggestions()
    assert len(pending) == 1 and pending[0]["merchant"] == "EKOM"

    ledger.decide_suggestion("EKOM", "accepted")

    assert ledger.suggestions() == []
    assert [row["decision"] for row in ledger.suggestions("accepted")] == ["accepted"]
    with pytest.raises(KeyError):
        ledger.decide_suggestion("NOPE", "accepted")


def test_a_new_suggestion_for_the_same_merchant_replaces_the_decision(ledger):
    ledger.record_suggestion("EKOM", "Groceries", "classifier")
    ledger.decide_suggestion("EKOM", "dismissed")

    ledger.record_suggestion("EKOM", "Transport", "llm")

    pending = ledger.suggestions()
    assert len(pending) == 1
    assert pending[0]["category"] == "Transport"
    assert pending[0]["source"] == "llm"
