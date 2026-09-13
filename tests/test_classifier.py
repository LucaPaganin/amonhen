"""The light classifier and its reviewable proposals (desiderata 5.5 steps 3-4)."""
import datetime as dt
from decimal import Decimal

from amonhen.classifier import (
    CharNgramClassifier,
    apply_proposals,
    propose_categories,
)
from amonhen.merchants import RuleBook
from amonhen.models import Account, IncomingTransaction

# Two disjoint alphabets: no n-gram can occur in both, so the synthetic
# categories are separable by construction and the test does not depend on
# whatever the hash happens to collide.
A_LETTERS = "abcdef"
B_LETTERS = "stuvwx"


def _text(letters, seed, length=14):
    """A deterministic string over `letters` that depends on the whole seed."""
    state = seed
    out = []
    for _ in range(length):
        state = (state * 31 + 17) % 1009
        out.append(letters[(state + seed) % len(letters)])
    return "".join(out)


def _separable_samples(count=30):
    samples = []
    for i in range(count):
        samples.append((_text(A_LETTERS, i), "Alpha"))
        samples.append((_text(B_LETTERS, i), "Beta"))
    return samples


def test_learns_two_disjoint_character_sets():
    classifier = CharNgramClassifier()
    classifier.fit(_separable_samples())

    alpha = classifier.predict(_text(A_LETTERS, 999))
    beta = classifier.predict(_text(B_LETTERS, 999))

    assert classifier.categories == ("Alpha", "Beta")
    assert classifier.samples_seen == 60
    assert alpha is not None and alpha[0] == "Alpha" and alpha[1] > 0.5
    assert beta is not None and beta[0] == "Beta" and beta[1] > 0.5


def test_unseen_features_are_not_decided():
    classifier = CharNgramClassifier()
    classifier.fit(_separable_samples())

    assert classifier.predict("zzzzzz") is None
    assert CharNgramClassifier().predict("anything") is None


def test_single_category_fits_and_training_is_deterministic():
    single = CharNgramClassifier()
    single.fit([("aaaa", "Only"), ("bbbb", "Only")])

    assert single.categories == ("Only",)
    result = single.predict("aaaa")
    assert result is not None and result[0] == "Only" and 0.0 <= result[1] <= 1.0

    first = CharNgramClassifier()
    second = CharNgramClassifier()
    first.fit(_separable_samples())
    second.fit(_separable_samples())
    probes = [_text(A_LETTERS, 7), _text(B_LETTERS, 9), "zzzz", ""]
    assert [first.predict(text) for text in probes] == [second.predict(text) for text in probes]


def test_probability_is_bounded_and_category_is_known():
    classifier = CharNgramClassifier()
    classifier.fit(_separable_samples())

    for seed in range(40):
        letters = A_LETTERS if seed % 2 == 0 else B_LETTERS
        prediction = classifier.predict(_text(letters, seed))
        if prediction is None:
            continue
        category, confidence = prediction
        assert 0.0 <= confidence <= 1.0
        assert category in classifier.categories


def _make_txn(ledger, account_id, amount, description):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date(2026, 8, 1),
        amount=Decimal(amount),
        description=description,
        status="BOOK",
        source="import",
        balancing_account_id=ledger.uncategorized(),
        raw={},
    )


def _seed_ledger(ledger):
    """Categorized history: A-text merchants are Groceries, B-text are Travel."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    for i in range(12):
        for letters, category in ((A_LETTERS, "Groceries"), (B_LETTERS, "Travel")):
            description = _text(letters, i)
            transaction_id, _ = ledger.record(_make_txn(ledger, account, "-10.00", description))
            ledger.set_category(transaction_id, ledger.category(category))
    return account


def test_propose_skips_covered_and_apply_only_records_the_confident(ledger):
    account = _seed_ledger(ledger)

    categorized_merchant = _text(A_LETTERS, 3)  # already carries a category
    ruled_merchant = _text(A_LETTERS, 400)
    pending_merchant = _text(B_LETTERS, 401)
    incoming_merchant = _text(B_LETTERS, 402)
    fresh_a = _text(A_LETTERS, 500)
    fresh_b = _text(B_LETTERS, 501)

    RuleBook(ledger.conn).set_rule(ruled_merchant, "Groceries", ledger)
    ledger.record_suggestion(pending_merchant, "Travel", "llm")

    candidate_ids = [
        ledger.record(_make_txn(ledger, account, "-12.00", fresh_a))[0],
        ledger.record(_make_txn(ledger, account, "-13.00", fresh_b))[0],
        ledger.record(_make_txn(ledger, account, "-14.00", ruled_merchant))[0],
        ledger.record(_make_txn(ledger, account, "-15.00", pending_merchant))[0],
        ledger.record(_make_txn(ledger, account, "-16.00", categorized_merchant))[0],
        ledger.record(_make_txn(ledger, account, "200.00", incoming_merchant))[0],
    ]

    before = len(ledger.suggestions())
    proposals = propose_categories(ledger, min_samples=6, min_confidence=0.6)

    assert len(ledger.suggestions()) == before  # proposing writes nothing
    by_merchant = {merchant: category for merchant, category, _ in proposals}
    assert by_merchant.get(fresh_a) == "Groceries"
    assert by_merchant.get(fresh_b) == "Travel"
    assert categorized_merchant not in by_merchant
    assert ruled_merchant not in by_merchant
    assert pending_merchant not in by_merchant
    assert incoming_merchant not in by_merchant

    unsure = ("unsure merchant", "Groceries", 0.1)
    recorded = apply_proposals(ledger, proposals + [unsure], min_confidence=0.6)

    assert recorded == len(proposals)
    rows = {row["merchant"]: row for row in ledger.suggestions()}
    assert rows[fresh_a]["source"] == "classifier"
    assert rows[fresh_b]["source"] == "classifier"
    assert rows[pending_merchant]["source"] == "llm"
    assert unsure[0] not in rows

    # A suggestion is never a category: the proposed transactions stay open.
    for transaction_id in candidate_ids:
        assert ledger.category_of(transaction_id) == "Uncategorized"


def test_propose_needs_enough_samples_to_train(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    transaction_id, _ = ledger.record(_make_txn(ledger, account, "-10.00", _text(A_LETTERS, 1)))
    ledger.set_category(transaction_id, ledger.category("Groceries"))
    ledger.record(_make_txn(ledger, account, "-5.00", _text(A_LETTERS, 50)))

    assert propose_categories(ledger, min_samples=20) == []


def test_coverage_measures_the_rules_and_the_classifier_reach(ledger):
    import datetime as dt
    from decimal import Decimal

    from amonhen.classifier import coverage
    from amonhen.merchants import RuleBook
    from amonhen.models import Account, IncomingTransaction

    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    for description in ("SUPERMERCATO GULLIVER", "ASPITGENOVA OVEST", "ASPITSAVONA VADO"):
        ledger.record(
            IncomingTransaction(
                account_id=account,
                date=dt.date(2026, 9, 1),
                amount=Decimal("-10.00"),
                description=description,
                status="BOOK",
                source="import",
                balancing_account_id=ledger.uncategorized(),
                raw={},
            )
        )
    # One rule on one of the three merchants: the coverage says how far it reaches.
    RuleBook(ledger.conn).set_rule("SUPERMERCATO GULLIVER", "Spesa", ledger)

    share = coverage(ledger, [("ASPITGENOVA OVEST", "Trasporti", 0.9)])

    assert share == {"spending": 3, "categorized": 1, "uncovered": 2, "proposed": 1}
