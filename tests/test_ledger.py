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


def test_a_note_survives_the_promotion_of_its_movement(ledger):
    """A note is local, and the promotion rewrites the row it hangs on.

    The bank's booked row replaces date, description and provider id of the
    pending one. What a person wrote about the movement has to be there after.
    """
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(
        make_txn(ledger, account, "2026-01-10", "-12.30", "Netflix", status="PDNG", external_id="p1")
    )
    ledger.set_notes(transaction_id, "da chiedere a Netflix")

    _, action = ledger.record(
        make_txn(ledger, account, "2026-01-12", "-12.30", "NETFLIX.COM", external_id="b1")
    )

    assert action == "promoted"
    row = ledger.conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    assert row["notes"] == "da chiedere a Netflix"
    assert row["description"] == "NETFLIX.COM"


def test_a_note_survives_the_import_of_the_same_movement(ledger):
    """The import path is the other way into the ledger; it writes the row too."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(
        make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", external_id="e1")
    )
    ledger.set_notes(transaction_id, "rimborso a meta")

    ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", external_id="e1"))

    assert ledger.conn.execute("SELECT notes FROM transactions").fetchone()["notes"] == "rimborso a meta"


def test_a_note_can_be_cleared_and_an_empty_one_is_nothing(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom"))

    ledger.set_notes(transaction_id, "  ")
    assert ledger.conn.execute("SELECT notes FROM transactions").fetchone()["notes"] is None

    ledger.set_notes(transaction_id, "  spesa di prova  ")
    assert ledger.conn.execute("SELECT notes FROM transactions").fetchone()["notes"] == "spesa di prova"

    ledger.set_notes(transaction_id, None)
    assert ledger.conn.execute("SELECT notes FROM transactions").fetchone()["notes"] is None


def test_a_note_on_a_movement_that_does_not_exist_is_refused(ledger):
    with pytest.raises(KeyError):
        ledger.set_notes(9999, "qualcosa")


def test_deleting_a_movement_takes_it_out_and_remembers_it(ledger):
    """The row goes; what it carried stays, or the next sync writes it back."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(
        make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", external_id="e1")
    )
    ledger.set_notes(transaction_id, "doppione")

    deletion = ledger.delete_transaction(transaction_id)

    assert deletion.transaction_id == transaction_id
    assert deletion.unlinked_pair is False
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 0
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM postings").fetchone()["c"] == 0
    tombstone = ledger.conn.execute("SELECT * FROM deleted_transactions").fetchone()
    assert (tombstone["key"], tombstone["amount"], tombstone["notes"], tombstone["restored_at"]) == (
        "e1", "-42.50", "doppione", None
    )


def test_a_deleted_movement_is_not_written_back(ledger):
    """What a delete means: the next sync sees the movement and leaves it out."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    txn = make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", external_id="e1")
    transaction_id, _ = ledger.record(txn)
    ledger.delete_transaction(transaction_id)

    id_again, action = ledger.record(txn)

    assert action == "suppressed"
    assert id_again == 0
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 0


def test_a_deleted_movement_without_a_provider_id_is_remembered_by_its_hash(ledger):
    """The import path has no provider id, and its rows must stay deleted too."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    txn = make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", source="import")
    transaction_id, _ = ledger.record(txn)
    ledger.delete_transaction(transaction_id)

    _, action = ledger.record(txn)

    assert action == "suppressed"


def test_deleting_one_of_two_identical_movements_keeps_the_other(ledger):
    """Four identical top-ups in one day are real, so a tombstone is exact.

    The second row carries a suffixed hash; deleting it must not swallow the
    first, which is the row the bank will report again tomorrow.
    """
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    first = make_txn(ledger, account, "2026-01-05", "-250.00", "Top up")
    second = make_txn(ledger, account, "2026-01-05", "-250.00", "Top up")
    ledger.record_batch([first, second])
    rows = ledger.conn.execute("SELECT id FROM transactions ORDER BY id").fetchall()
    assert len(rows) == 2

    ledger.delete_transaction(rows[1]["id"])
    actions = ledger.record_batch([first, second])

    assert actions == {"duplicate": 1, "suppressed": 1}
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 1


def test_deleting_a_leg_takes_the_pair_with_it(ledger):
    """The other half cannot stay out of the spending with nothing saying why."""
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    joint = ledger.ensure_account(Account(name="Conto cointestato", type="real"))
    out = ledger.record(make_txn(ledger, revolut, "2026-01-10", "-840.00", "Bonifico"))[0]
    into = ledger.record(make_txn(ledger, joint, "2026-01-10", "840.00", "Bonifico"))[0]
    ledger.link_transfer_pair(out, into, "high", "manual")
    assert ledger.category_of(into) is None

    deletion = ledger.delete_transaction(out)

    assert deletion.unlinked_pair is True
    # The surviving leg is spending again, and nothing points at the clearing.
    assert ledger.category_of(into) == "Uncategorized"
    assert ledger.transfer_target(into) is None
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transfer_links").fetchone()["c"] == 0
    ledger.validate()


def test_deleting_a_pending_movement_suppresses_the_booked_one(ledger):
    """A card authorization and its settlement are the same movement.

    The bank reports the pending row first and books it days later; deleting the
    pending one and watching the booked one come back would make a delete look
    like it had failed. The two hold the same provider reference, and that is
    what the tombstone matches.
    """
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(
        make_txn(ledger, account, "2026-01-10", "-12.30", "Cart Srl", status="PDNG", external_id="p1")
    )
    ledger.delete_transaction(transaction_id)

    _, action = ledger.record(
        make_txn(ledger, account, "2026-01-12", "-12.30", "Cart Srl", external_id="p1")
    )

    assert action == "suppressed"
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 0


def test_a_deleted_movement_stays_deleted_when_the_other_path_delivers_it(ledger):
    """The overlap between sync and import is a designed state, not a corner.

    An export carries no identifier, so a movement deleted from one path
    arrives from the other under a different identity: same content, different
    key. Without this the next sync quietly undoes the deletion, and the ledger
    agrees with the bank again — which makes the panel that exists to catch it
    report green.
    """
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    imported = make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", source="import")
    transaction_id, _ = ledger.record(imported)
    ledger.delete_transaction(transaction_id)

    _, action = ledger.record(
        make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", external_id="e1")
    )

    assert action == "suppressed"


def test_a_deleted_movement_stays_deleted_when_the_import_delivers_it(ledger):
    """The other direction: deleted with the bank's id, re-delivered by export."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(
        make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", external_id="e1")
    )
    ledger.delete_transaction(transaction_id)

    _, action = ledger.record(
        make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", source="import")
    )

    assert action == "suppressed"


def test_a_deleted_pending_movement_is_not_settled_into_the_ledger(ledger):
    """The bank books it days later under a new reference and a new date.

    That is the promotion the ledger already models; for a deletion it is the
    same movement, so the settlement must not bring it back. Nothing else can be
    swallowed this way: the twin of a same-status movement is never matched on
    content alone.
    """
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(
        make_txn(ledger, account, "2026-01-10", "-12.30", "Cart Srl", status="PDNG", external_id="p1")
    )
    ledger.delete_transaction(transaction_id)

    _, action = ledger.record(
        make_txn(ledger, account, "2026-01-12", "-12.30", "CART SRL", external_id="b1")
    )

    assert action == "suppressed"
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 0


def test_a_deleted_movement_is_not_found_again(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom"))

    ledger.delete_transaction(transaction_id)

    with pytest.raises(KeyError):
        ledger.delete_transaction(transaction_id)
    with pytest.raises(KeyError):
        ledger.set_notes(transaction_id, "tardi")


def test_an_account_can_take_its_deleted_movements_back(ledger):
    """Off is what deleting means; on is the one account that wants them again."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    txn = make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", external_id="e1")
    transaction_id, _ = ledger.record(txn)
    ledger.set_notes(transaction_id, "cancellato per sbaglio")
    ledger.delete_transaction(transaction_id)

    assert ledger.record(txn)[1] == "suppressed"

    ledger.set_reimport_deleted(account, True)
    again, action = ledger.record(txn)

    assert action == "reimported"
    row = ledger.conn.execute("SELECT * FROM transactions WHERE id = ?", (again,)).fetchone()
    assert row["external_id"] == "e1"
    # The note comes back with the movement: losing it would make the flag an
    # expensive way to undo a mistake.
    assert row["notes"] == "cancellato per sbaglio"
    tombstone = ledger.conn.execute("SELECT * FROM deleted_transactions").fetchone()
    assert tombstone["restored_at"] is not None

    # A second sync sees the movement already there.
    assert ledger.record(txn)[1] == "duplicate"
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 1

    # Turning the flag off again does not take back what came home.
    ledger.set_reimport_deleted(account, False)
    assert ledger.record(txn)[1] == "duplicate"
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 1


def test_the_reimport_flag_is_refused_on_something_that_is_not_an_account(ledger):
    category = ledger.category("Spesa")

    with pytest.raises(ValueError):
        ledger.set_reimport_deleted(category, True)


def test_deleting_a_movement_that_came_back_starts_the_tombstone_over(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    txn = make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", external_id="e1")
    transaction_id, _ = ledger.record(txn)
    ledger.delete_transaction(transaction_id)
    ledger.set_reimport_deleted(account, True)
    again, _ = ledger.record(txn)

    ledger.set_reimport_deleted(account, False)
    ledger.delete_transaction(again)

    tombstones = ledger.conn.execute("SELECT * FROM deleted_transactions").fetchall()
    assert len(tombstones) == 1
    assert tombstones[0]["restored_at"] is None
    assert ledger.record(txn)[1] == "suppressed"


def test_a_deleted_movement_comes_back_whole(ledger):
    """Restoring is the delete undone: the note, the payload and the balance."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    txn = make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom", external_id="e1")
    transaction_id, _ = ledger.record(txn)
    ledger.set_notes(transaction_id, "da riavere")
    before = ledger.balance(account, dt.date(2026, 1, 31))
    ledger.delete_transaction(transaction_id)
    deleted_id = ledger.deleted_transactions()[0]["id"]

    restored = ledger.restore_deleted(deleted_id)

    row = ledger.conn.execute("SELECT * FROM transactions WHERE id = ?", (restored,)).fetchone()
    assert (row["external_id"], row["amount"], row["notes"]) == ("e1", "-42.50", "da riavere")
    assert ledger.balance(account, dt.date(2026, 1, 31)) == before
    # One movement, not two: the identity it was deleted by is the identity it
    # comes back with. The note comes back; the category does not — that is a
    # decision the ingest or a person takes again, and pretending otherwise
    # would put a movement back on a category nobody chose.
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 1
    assert ledger.category_of(restored) == "Uncategorized"
    assert ledger.deleted_transactions() == []
    ledger.validate()


def test_a_movement_that_came_back_is_out_of_the_trash(ledger):
    """The list is what is still deleted, not what was deleted once."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom"))
    ledger.delete_transaction(transaction_id)
    ledger.set_reimport_deleted(account, True)
    ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom"))

    assert ledger.deleted_transactions() == []


def test_restoring_twice_is_refused(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(make_txn(ledger, account, "2026-01-05", "-42.50", "Ekom"))
    ledger.delete_transaction(transaction_id)
    deleted_id = ledger.deleted_transactions()[0]["id"]
    ledger.restore_deleted(deleted_id)

    with pytest.raises(ValueError):
        ledger.restore_deleted(deleted_id)
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 1


def test_a_restored_pending_movement_is_still_settled_when_the_bank_does(ledger):
    """The tombstone keeps its veto after a restore, and the promotion precedes it."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(
        make_txn(ledger, account, "2026-01-10", "-12.30", "Cart Srl", status="PDNG", external_id="p1")
    )
    ledger.delete_transaction(transaction_id)
    restored = ledger.restore_deleted(ledger.deleted_transactions()[0]["id"])
    assert ledger.conn.execute("SELECT status FROM transactions").fetchone()["status"] == "PDNG"

    promoted, action = ledger.record(
        make_txn(ledger, account, "2026-01-12", "-12.30", "CART SRL", external_id="b1")
    )

    assert (promoted, action) == (restored, "promoted")


def test_restoring_something_that_was_never_deleted_is_refused(ledger):
    with pytest.raises(KeyError):
        ledger.restore_deleted(999)


def test_a_deletion_explains_the_difference_it_leaves(ledger):
    """Deleting a movement the bank still counts makes the ledger disagree.

    The disagreement is the deleted amount and nothing else, and saying so is
    what keeps a red panel for the differences nobody decided.
    """
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-01-05", "-10.00", "Bar"))
    gone = ledger.record(make_txn(ledger, account, "2026-01-06", "-3.00", "Ekom"))[0]
    ledger.record(make_txn(ledger, account, "2026-01-12", "-12.30", "Netflix", status="PDNG"))
    # What the bank declares: everything, the deleted movement included.
    declared = ledger.balance(account, dt.date(2026, 1, 31))
    ledger.delete_transaction(gone)

    available = ledger.check_balance(account, declared, dt.date(2026, 1, 31), kind="available")
    booked = ledger.check_balance(account, declared, dt.date(2026, 1, 31), kind="booked")

    assert (available.difference, available.suppressed, available.suppressed_count) == (
        Decimal("-3.00"), Decimal("-3.00"), 1
    )
    assert available.explained and not available.ok
    # The same figure against the booked side is not explained by the deletion:
    # the rest of that difference is the pending movement it never had.
    assert not booked.explained and booked.suppressed_count == 1
    assert ledger.balance(account, dt.date(2026, 1, 31)) - declared == Decimal("3.00")


def test_a_pending_deletion_is_not_part_of_the_booked_figure(ledger):
    """The two declared figures count different movements, deletions included."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-01-05", "-10.00", "Bar"))
    pending = ledger.record(
        make_txn(ledger, account, "2026-01-12", "-12.30", "Netflix", status="PDNG")
    )[0]
    declared = ledger.balance(account, dt.date(2026, 1, 31), settled=True)
    ledger.delete_transaction(pending)

    available = ledger.check_balance(account, declared, dt.date(2026, 1, 31), kind="available")
    booked = ledger.check_balance(account, declared, dt.date(2026, 1, 31), kind="booked")

    assert (available.suppressed, available.suppressed_count) == (Decimal("-12.30"), 1)
    assert (booked.suppressed, booked.suppressed_count) == (Decimal("0.00"), 0)


def test_a_restored_movement_stops_explaining_anything(ledger):
    """It is in the ledger again, so it is no longer a difference."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-01-05", "-10.00", "Bar"))
    gone = ledger.record(make_txn(ledger, account, "2026-01-06", "-3.00", "Ekom"))[0]
    declared = ledger.balance(account, dt.date(2026, 1, 31))
    ledger.delete_transaction(gone)
    ledger.restore_deleted(ledger.deleted_transactions()[0]["id"])

    check = ledger.check_balance(account, declared, dt.date(2026, 1, 31))

    assert check.ok
    assert (check.suppressed_count, check.suppressed) == (0, Decimal("0.00"))


def test_a_deletion_after_the_declared_date_explains_nothing(ledger):
    """The figure is checked on a date: what was deleted later is not part of it."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-01-05", "-10.00", "Bar"))
    declared = ledger.balance(account, dt.date(2026, 1, 20))
    gone = ledger.record(make_txn(ledger, account, "2026-01-25", "-3.00", "Ekom"))[0]
    ledger.delete_transaction(gone)

    check = ledger.check_balance(account, declared, dt.date(2026, 1, 20))

    assert check.ok
    assert (check.suppressed_count, check.suppressed) == (0, Decimal("0.00"))


def test_a_deletion_before_the_opening_explains_nothing(ledger):
    """`balance` folds what sits before the opening date into the opening.

    A movement the figure never held cannot be the reason the figure disagrees,
    and counting it here would turn a true difference into a permanent red.
    """
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    early = ledger.record(make_txn(ledger, account, "2026-01-05", "-30.00", "Bar"))[0]
    late = ledger.record(make_txn(ledger, account, "2026-01-15", "-10.00", "Ekom"))[0]
    ledger.conn.execute(
        "UPDATE accounts SET opening_balance = '100.00', opening_date = '2026-01-10' WHERE id = ?",
        (account,),
    )
    declared = ledger.balance(account, dt.date(2026, 1, 31))
    ledger.delete_transaction(early)
    ledger.delete_transaction(late)

    check = ledger.check_balance(account, declared, dt.date(2026, 1, 31))

    assert (check.difference, check.suppressed, check.suppressed_count) == (
        Decimal("-10.00"), Decimal("-10.00"), 1
    )
    assert check.explained


def test_a_difference_the_deletions_do_not_explain_is_still_a_mismatch(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    gone = ledger.record(make_txn(ledger, account, "2026-01-06", "-3.00", "Ekom"))[0]
    declared = ledger.balance(account, dt.date(2026, 1, 31))
    ledger.delete_transaction(gone)

    # The bank's figure is off by more than what was deleted: a gap nobody
    # decided, and it must not hide behind the explanation.
    check = ledger.check_balance(account, declared - Decimal("5.00"), dt.date(2026, 1, 31))

    assert not check.ok and not check.explained


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
