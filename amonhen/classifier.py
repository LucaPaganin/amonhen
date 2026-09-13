"""A light statistical classifier for the merchants no rule covers.

Desiderata 5.5 step 3: once the rules have run, a small multinomial
logistic regression over character n-grams proposes a category for what is
left. It is deliberately deterministic -- the same samples always produce the
same model and the same prediction -- so a proposal can be re-derived and
reviewed rather than trusted blindly.

Nothing here writes a category. `propose_categories` only reads, and
`apply_proposals` records the survivors in the reviewable suggestion table with
source ``classifier``; a human accepts or dismisses them.
"""
from __future__ import annotations

import math
import zlib
from collections import defaultdict
from typing import TYPE_CHECKING, Iterable

from amonhen.merchants import RuleBook, matching_rule, merchant_name
from amonhen.settings import UNCATEGORIZED

if TYPE_CHECKING:
    from amonhen.ledger import Ledger

# Character n-grams hashed into a fixed-size space so the model stays bounded
# no matter how much text is fed to it.
NGRAM = 3
FEATURE_SPACE = 1 << 16
# Full-batch gradient descent with a fixed step count and learning rate: no
# randomness anywhere, so training is reproducible.
STEPS = 200
LEARNING_RATE = 0.5
L2 = 1e-4


def _features(text: str) -> dict[int, float]:
    """Hashed character-n-gram counts of a whitespace-collapsed, case-folded text."""
    collapsed = " ".join(text.split()).casefold()
    padded = f" {collapsed} "
    if len(padded) < NGRAM:
        grams = [padded]
    else:
        grams = [padded[i:i + NGRAM] for i in range(len(padded) - NGRAM + 1)]
    counts: dict[int, float] = {}
    for gram in grams:
        index = zlib.crc32(gram.encode("utf-8")) % FEATURE_SPACE
        counts[index] = counts.get(index, 0.0) + 1.0
    return counts


def _softmax(scores: list[float]) -> list[float]:
    top = max(scores)
    exps = [math.exp(score - top) for score in scores]
    total = sum(exps)
    return [value / total for value in exps]


class CharNgramClassifier:
    """Multinomial logistic regression (softmax) over hashed character n-grams."""

    def __init__(self) -> None:
        self._categories: tuple[str, ...] = ()
        self._weights: list[dict[int, float]] = []
        self._bias: list[float] = []
        self._seen: set[int] = set()
        self._samples_seen = 0

    @property
    def categories(self) -> tuple[str, ...]:
        """The training categories, in a stable order."""
        return self._categories

    @property
    def samples_seen(self) -> int:
        """How many samples the last `fit` was given."""
        return self._samples_seen

    def fit(self, samples: Iterable[tuple[str, str]]) -> None:
        """Train on (text, category) pairs. Re-fitting replaces any earlier model."""
        rows = [(str(text), str(category)) for text, category in samples]
        self._samples_seen = len(rows)
        self._categories = tuple(sorted({category for _, category in rows}))
        self._weights = [{} for _ in self._categories]
        self._bias = [0.0 for _ in self._categories]
        self._seen = set()
        if not rows or not self._categories:
            return

        index_of = {category: index for index, category in enumerate(self._categories)}
        prepared: list[tuple[dict[int, float], int]] = []
        for text, category in rows:
            features = _features(text)
            if not features:
                continue
            self._seen.update(features)
            prepared.append((features, index_of[category]))
        if not prepared:
            return

        count = len(prepared)
        classes = len(self._categories)
        for _ in range(STEPS):
            probabilities = [
                _softmax([self._score(features, c) for c in range(classes)])
                for features, _ in prepared
            ]
            grad_bias = [0.0] * classes
            grad_weights: list[defaultdict[int, float]] = [defaultdict(float) for _ in range(classes)]
            for (features, label), probs in zip(prepared, probabilities):
                for c in range(classes):
                    error = probs[c] - (1.0 if c == label else 0.0)
                    if error == 0.0:
                        continue
                    grad_bias[c] += error
                    class_grad = grad_weights[c]
                    for index, frequency in features.items():
                        class_grad[index] += error * frequency
            scale = LEARNING_RATE / count
            for c in range(classes):
                weight = self._weights[c]
                decay = 1.0 - LEARNING_RATE * L2
                for index in weight:
                    weight[index] *= decay
                for index, gradient in grad_weights[c].items():
                    weight[index] = weight.get(index, 0.0) - scale * gradient
                self._bias[c] -= scale * grad_bias[c]

    def _score(self, features: dict[int, float], c: int) -> float:
        weight = self._weights[c]
        return self._bias[c] + sum(
            weight.get(index, 0.0) * frequency for index, frequency in features.items()
        )

    def predict(self, text: str) -> tuple[str, float] | None:
        """The most likely category and its probability, or None without evidence.

        Text whose n-grams never appeared in training carries no information for
        this model, so it answers None instead of a uniform guess.
        """
        if not self._categories:
            return None
        features = _features(text)
        if not features or not (features.keys() & self._seen):
            return None
        probabilities = _softmax(
            [self._score(features, c) for c in range(len(self._categories))]
        )
        best = 0
        for c in range(1, len(probabilities)):
            if probabilities[c] > probabilities[best]:
                best = c
        return self._categories[best], probabilities[best]


def _training_samples(ledger: "Ledger") -> list[tuple[str, str]]:
    """(merchant text, category) for every settled transaction a human categorized.

    Transfer legs are skipped: their clearing side is not a category, and the
    category side of a rejected link is inconclusive. A split has more than one
    label, so it is left out rather than taught as noise.
    """
    rows = ledger.conn.execute(
        """SELECT t.id, t.description, a.name AS category
           FROM transactions t
           JOIN postings p ON p.transaction_id = t.id
           JOIN accounts a ON a.id = p.account_id
           WHERE t.status = 'BOOK'
             AND a.type = 'category'
             AND a.name != ?
             AND NOT EXISTS (
                 SELECT 1 FROM postings v JOIN accounts va ON va.id = v.account_id
                 WHERE v.transaction_id = t.id AND va.type = 'virtual')
           ORDER BY t.id""",
        (UNCATEGORIZED,),
    ).fetchall()
    labels: dict[int, tuple[str, set[str]]] = {}
    for row in rows:
        entry = labels.get(row["id"])
        if entry is None:
            labels[row["id"]] = (merchant_name(row["description"]), {row["category"]})
        else:
            entry[1].add(row["category"])
    samples = []
    for transaction_id in sorted(labels):
        text, categories = labels[transaction_id]
        if len(categories) != 1:
            continue
        samples.append((text, next(iter(categories))))
    return samples


def _uncategorized_merchants(ledger: "Ledger") -> list[str]:
    """Distinct merchants of settled spending that still sits in Uncategorized."""
    rows = ledger.conn.execute(
        """SELECT t.description
           FROM transactions t
           WHERE t.status = 'BOOK'
             AND CAST(t.amount AS REAL) < 0
             AND NOT EXISTS (
                 SELECT 1 FROM postings p JOIN accounts a ON a.id = p.account_id
                 WHERE p.transaction_id = t.id AND a.type = 'category' AND a.name != ?)
             AND NOT EXISTS (
                 SELECT 1 FROM postings v JOIN accounts va ON va.id = v.account_id
                 WHERE v.transaction_id = t.id AND va.type = 'virtual')
           ORDER BY t.id""",
        (UNCATEGORIZED,),
    ).fetchall()
    merchants: dict[str, None] = {}
    for row in rows:
        merchants.setdefault(merchant_name(row["description"]), None)
    return list(merchants)


def _covered_merchants(ledger: "Ledger") -> set[str]:
    """Merchants a pending proposal already covers."""
    return {
        row["merchant"].strip().casefold()
        for row in ledger.conn.execute(
            "SELECT merchant FROM merchant_suggestions WHERE decision = 'pending'"
        )
    }


def propose_categories(
    ledger: "Ledger",
    *,
    min_samples: int = 20,
    min_confidence: float = 0.6,
    limit: int = 50,
) -> list[tuple[str, str, float]]:
    """Propose (merchant, category, confidence) for the uncategorized spending.

    Trains on what a human already categorized, then predicts per merchant.
    Merchants a rule or a pending suggestion already covers are left alone, and
    nothing is written. Below `min_samples` training rows there is too little to
    learn from, so the result is empty.
    """
    training = _training_samples(ledger)
    if len(training) < min_samples:
        return []
    classifier = CharNgramClassifier()
    classifier.fit(training)
    if not classifier.categories:
        return []

    covered = _covered_merchants(ledger)
    # A merchant a human already categorized needs no proposal: what is left is
    # only the tail of something already decided.
    covered.update(text.strip().casefold() for text, _ in training)
    rules = RuleBook(ledger.conn).rules()
    proposals: dict[str, tuple[str, float]] = {}
    for merchant in _uncategorized_merchants(ledger):
        if merchant.strip().casefold() in covered or matching_rule(merchant, rules) is not None:
            continue
        prediction = classifier.predict(merchant)
        if prediction is None:
            continue
        category, confidence = prediction
        if confidence < min_confidence:
            continue
        current = proposals.get(merchant)
        if current is None or confidence > current[1]:
            proposals[merchant] = (category, confidence)

    ranked = sorted(
        (
            (merchant, category, confidence)
            for merchant, (category, confidence) in proposals.items()
        ),
        key=lambda item: (-item[2], item[0]),
    )
    return ranked[:limit]


def apply_proposals(
    ledger: "Ledger",
    proposals: Iterable[tuple[str, str, float]],
    min_confidence: float = 0.6,
) -> int:
    """Record the confident proposals in the review queue; return how many.

    Only suggestions are written. A proposal never becomes a category here --
    that is the human's decision on the review screen.
    """
    recorded = 0
    for merchant, category, confidence in proposals:
        if confidence < min_confidence:
            continue
        ledger.record_suggestion(merchant, category, "classifier")
        recorded += 1
    return recorded


def coverage(ledger: "Ledger", proposals: Iterable[tuple[str, str, float]]) -> dict[str, int]:
    """How much of the settled spending is covered, with and without proposals.

    Desiderata 5.5 expects the rules to cover most of the traffic and the
    statistical stage to work on what is left, so both shares are measured
    rather than assumed.
    """
    from amonhen.merchants import merchant_name
    from amonhen.settings import UNCATEGORIZED

    rows = ledger.conn.execute(
        """SELECT t.id, t.description,
                  EXISTS (
                      SELECT 1 FROM postings p JOIN accounts a ON a.id = p.account_id
                      WHERE p.transaction_id = t.id AND a.type = 'category' AND a.name != ?
                  ) AS categorized
           FROM transactions t
           WHERE t.status = 'BOOK' AND CAST(t.amount AS REAL) < 0
             AND NOT EXISTS (
                 SELECT 1 FROM postings p JOIN accounts a ON a.id = p.account_id
                 WHERE p.transaction_id = t.id AND a.type = 'virtual'
             )""",
        (UNCATEGORIZED,),
    ).fetchall()

    proposed_merchants = {merchant for merchant, _, _ in proposals}
    spending = len(rows)
    categorized = sum(1 for row in rows if row["categorized"])
    uncovered = spending - categorized
    reachable = sum(
        1 for row in rows if not row["categorized"] and merchant_name(row["description"]) in proposed_merchants
    )
    return {
        "spending": spending,
        "categorized": categorized,
        "uncovered": uncovered,
        "proposed": reachable,
    }
