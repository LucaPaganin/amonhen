"""Merchant normalization and the rules built on it (desiderata 5.5)."""
import datetime as dt
from decimal import Decimal

import pytest

from amonhen.merchants import (
    Rule,
    RuleBook,
    categorize,
    matching_rule,
    merchant_name,
    rule_usage,
    uncovered_spending,
)
from amonhen.models import Account, IncomingTransaction


def test_merchant_name_drops_the_transaction_metadata_segments():
    assert merchant_name("L Ortobello S.n.c. Di Ah | CARD_PAYMENT | VISA 7883") == "L Ortobello S.n.c. Di Ah"
    assert merchant_name("Amazon | Amazon") == "Amazon"
    assert merchant_name("EKOM | Cart") == "EKOM"


def test_merchant_name_cuts_the_bank_appended_details():
    assert (
        merchant_name("MICROSOFTG123 MSBILL.INFO IE Carta N. ***** 055 Data operazione 27/12/2025")
        == "MICROSOFTG123 MSBILL.INFO IE"
    )
    assert merchant_name("Enea Energia Addebito SDD fattura 42") == "Enea Energia"


def test_merchant_name_keeps_a_plain_description_intact():
    assert merchant_name("To Conto deposito senza vincoli") == "To Conto deposito senza vincoli"
    assert merchant_name("Supermercato Gulliver") == "Supermercato Gulliver"


def test_merchant_name_never_returns_empty():
    assert merchant_name("") == "Unknown"
    assert merchant_name("CARD_PAYMENT | VISA 1234") == "CARD_PAYMENT | VISA 1234"


def make_txn(ledger, account_id, date, amount, description):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(date),
        amount=Decimal(amount),
        description=description,
        status="BOOK",
        source="import",
        balancing_account_id=ledger.uncategorized(),
        raw={},
    )


def test_the_stake_of_a_merchant_is_the_spending_still_waiting(ledger):
    """A proposal decides a merchant, not one movement, so the queue answers
    with how much is waiting, how many movements, and when they ran."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-08-03", "-12.34", "EKOM | CARD_PAYMENT | VISA 7883"))
    ledger.record(make_txn(ledger, account, "2026-08-05", "-7.66", "EKOM | CARD_PAYMENT | VISA 4455"))
    ledger.record(make_txn(ledger, account, "2026-08-06", "-3.00", "EKOM | Cart"))
    # A month earlier, so the span is not the same day twice.
    ledger.record(make_txn(ledger, account, "2026-07-30", "-1.00", "EKOM | Cart"))
    # Money in is not spending the proposal would settle.
    ledger.record(make_txn(ledger, account, "2026-08-08", "120.00", "EKOM | Rimborso"))
    decided, _ = ledger.record(make_txn(ledger, account, "2026-08-04", "-50.00", "EKOM | Cart"))
    ledger.set_category(decided, ledger.category("Shopping"))

    stake = uncovered_spending(ledger)["EKOM"]

    assert stake.movements == 4
    assert stake.total == Decimal("24.00")
    assert stake.first_date == "2026-07-30"
    assert stake.last_date == "2026-08-06"


def test_a_merchant_with_nothing_waiting_has_no_stake(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(make_txn(ledger, account, "2026-08-03", "-12.34", "EKOM | Cart"))
    ledger.set_category(transaction_id, ledger.category("Shopping"))

    assert uncovered_spending(ledger) == {}


def test_a_rule_catches_every_description_that_contains_it(ledger):
    """One rule covers a family of movements, not one merchant name: the whole
    point of matching the text instead of the normalized merchant."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-08-03", "-42.50", "Enea Energia Addebito SDD fattura 42"))
    ledger.record(make_txn(ledger, account, "2026-08-04", "-7.20", "Sorgenia Addebito SDD 7"))
    book = RuleBook(ledger.conn)

    count = book.set_rule("addebito sdd", "Bollette", ledger)

    assert count == 2
    assert ledger.spend_between(dt.date(2026, 8, 1), dt.date(2026, 8, 31)) == Decimal("49.70")


def test_the_longest_pattern_decides_when_two_rules_match(ledger):
    """`amazon prime` is a statement about fewer descriptions than `amazon`."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    prime = ledger.record(make_txn(ledger, account, "2026-08-03", "-4.99", "AMAZON PRIME | CARD_PAYMENT"))[0]
    plain = ledger.record(make_txn(ledger, account, "2026-08-04", "-20.00", "AMAZON EU SARL"))[0]
    book = RuleBook(ledger.conn)

    book.set_rule("amazon", "Shopping", ledger)
    book.set_rule("amazon prime", "Abbonamenti", ledger)

    assert ledger.category_of(prime) == "Abbonamenti"
    assert ledger.category_of(plain) == "Shopping"


def test_two_patterns_of_the_same_length_keep_the_answer_the_same():
    """Neither is narrower, so the alphabetical order decides, not the order written."""
    rules = [
        Rule(key="carta", pattern="CARTA", category="Uno"),
        Rule(key="verde", pattern="verde", category="Due"),
    ]

    assert matching_rule("PAGAMENTO CARTA VERDE 12", rules).category == "Uno"
    assert matching_rule("PAGAMENTO CARTA VERDE 12", reversed(rules)).category == "Uno"


def test_a_new_narrower_rule_takes_what_the_broader_one_held(ledger):
    """A rule change cannot leave a movement under a rule that no longer decides it."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    prime = ledger.record(make_txn(ledger, account, "2026-08-03", "-4.99", "AMAZON PRIME"))[0]
    plain = ledger.record(make_txn(ledger, account, "2026-08-04", "-20.00", "AMAZON EU SARL"))[0]
    book = RuleBook(ledger.conn)
    book.set_rule("amazon", "Shopping", ledger)

    count = book.set_rule("amazon prime", "Abbonamenti", ledger)

    assert count == 1
    assert ledger.category_of(prime) == "Abbonamenti"
    assert ledger.category_of(plain) == "Shopping"


def test_a_category_no_matching_rule_assigns_is_left_alone(ledger):
    """The rules fill the empty and follow their own work; a person's category stays."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ekom = ledger.record(make_txn(ledger, account, "2026-08-03", "-42.50", "EKOM"))[0]
    hand_made = ledger.record(make_txn(ledger, account, "2026-08-04", "-9.00", "EKOM | Cart"))[0]
    book = RuleBook(ledger.conn)
    book.set_rule("ekom", "Groceries", ledger)
    ledger.set_category(hand_made, ledger.category("Household"))

    count = book.set_rule("ekom", "Travel", ledger)

    assert count == 1
    assert ledger.category_of(ekom) == "Travel"
    assert ledger.category_of(hand_made) == "Household"


def test_removing_a_rule_gives_its_movements_to_the_rule_that_still_matches(ledger):
    """Removing the narrow rule is reversible by re-creating it, not by hand."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    prime = ledger.record(make_txn(ledger, account, "2026-08-03", "-4.99", "AMAZON PRIME"))[0]
    book = RuleBook(ledger.conn)
    book.set_rule("amazon", "Shopping", ledger)
    book.set_rule("amazon prime", "Abbonamenti", ledger)

    held = book.remove_rule("amazon prime", ledger)

    assert held == 1
    assert ledger.category_of(prime) == "Shopping"


def test_a_pattern_that_covers_nothing_is_still_removable(ledger):
    """The count column is how a dead rule shows itself; 0 is not "no rule"."""
    book = RuleBook(ledger.conn)

    assert book.set_rule("kart", "Groceries", ledger) == 0
    assert book.remove_rule("KART", ledger) == 0
    assert book.remove_rule("kart", ledger) is None


def test_a_rule_counts_the_movements_it_holds(ledger):
    """The list says how much a rule weighs; a split is a human act, not its work."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    for day in ("2026-08-03", "2026-08-04"):
        ledger.record(make_txn(ledger, account, day, "-42.50", "EKOM | Cart"))
    split_id = ledger.record(make_txn(ledger, account, "2026-08-05", "-30.00", "EKOM"))[0]
    book = RuleBook(ledger.conn)
    book.set_rule("ekom", "Groceries", ledger)

    assert rule_usage(ledger, book.rules())["ekom"] == 3

    ledger.set_splits(
        split_id,
        [(ledger.category("Groceries"), Decimal("20.00")), (ledger.category("Travel"), Decimal("10.00"))],
    )
    book.set_rule("ekom", "Travel", ledger)

    assert rule_usage(ledger, book.rules())["ekom"] == 2
    assert ledger.splits(split_id) != []


def test_a_rule_dismisses_every_proposal_it_answers(ledger):
    """Leaving one pending would leave the queue asking about categorized movements."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-08-03", "-42.50", "Enea Energia Addebito SDD"))
    ledger.record_suggestion("Enea Energia", "Bollette", "classifier")
    ledger.record_suggestion("Bar Centrale", "Ristoranti", "classifier")

    RuleBook(ledger.conn).set_rule("energia", "Bollette", ledger)

    assert [row["merchant"] for row in ledger.suggestions("pending")] == ["Bar Centrale"]


def test_a_rule_cannot_point_at_the_review_bucket(ledger):
    """It would take movements out of the queue while categorizing nothing."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-08-03", "-42.50", "EKOM"))
    book = RuleBook(ledger.conn)

    with pytest.raises(ValueError):
        book.set_rule("EKOM", "Uncategorized", ledger)

    with pytest.raises(ValueError):
        book.set_rule("   ", "Groceries", ledger)

    assert categorize(ledger, book) == 0


def test_a_pattern_with_stray_spaces_still_matches(ledger):
    """A text typed by a human must reach the descriptions, which have single spaces."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    cart = ledger.record(make_txn(ledger, account, "2026-08-03", "-42.50", "Cart  Srl"))[0]
    book = RuleBook(ledger.conn)

    book.set_rule("  Cart   Srl ", "Groceries", ledger)

    assert ledger.category_of(cart) == "Groceries"
    assert book.remove_rule("CART SRL", ledger) == 1


def test_removing_a_rule_sends_its_movements_back_to_the_queue(ledger):
    """Deleting a rule is reversible: re-creating it restores exactly those rows."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ekom = ledger.record(make_txn(ledger, account, "2026-08-03", "-42.50", "EKOM"))[0]
    book = RuleBook(ledger.conn)
    book.set_rule("EKOM", "Groceries", ledger)

    held = book.remove_rule("EKOM", ledger)

    assert held == 1
    assert ledger.category_of(ekom) == "Uncategorized"
    assert categorize(ledger, book) == 0
    assert book.remove_rule("EKOM", ledger) is None

    book.set_rule("EKOM", "Groceries", ledger)

    assert ledger.category_of(ekom) == "Groceries"


def test_an_unknown_merchant_stays_in_the_review_queue(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-08-03", "-42.50", "Never Seen Before"))
    book = RuleBook(ledger.conn)

    assert categorize(ledger, book) == 0
    assert ledger.category_of(1) == "Uncategorized"


def test_a_rule_is_not_applied_twice(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "2026-08-03", "-42.50", "EKOM"))
    book = RuleBook(ledger.conn)
    book.set_rule("EKOM", "Groceries", ledger)
    categorize(ledger, book)

    assert categorize(ledger, book) == 0


def test_rules_skip_transfer_legs(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    ledger.record(make_txn(ledger, revolut, "2026-08-15", "-840.00", "Bonifico"))
    ledger.record(make_txn(ledger, fineco, "2026-08-15", "840.00", "Bonifico"))
    from amonhen.transfers import link_transfers

    link_transfers(ledger)
    book = RuleBook(ledger.conn)
    book.set_rule("Bonifico", "Groceries", ledger)

    assert categorize(ledger, book) == 0
    assert ledger.spend_between(dt.date(2026, 8, 1), dt.date(2026, 8, 31)) == Decimal("0.00")
