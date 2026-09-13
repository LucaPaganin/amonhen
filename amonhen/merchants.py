"""Merchant normalization and the rules built on top of it.

Desiderata 5.5 steps 1 and 2: reduce the raw description to the merchant it
names, then apply the rules. A rule is a piece of text the description contains,
or a regular expression written between slashes, so one rule covers a family of
movements the bank spells differently — the merchant name being just one of the
texts a rule may hold. Both steps are deterministic, so they run inside ingest
without making it fail when something is unknown.
"""
import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Iterable, Sequence

from amonhen.ledger import UNCATEGORIZED_WHERE, Ledger
from amonhen.models import parse_decimal
from amonhen.settings import UNCATEGORIZED

SEPARATOR = " | "

# The slashes that make a pattern an expression instead of a piece of text.
_REGEX_DELIMITER = "/"

# Trailing text the bank appends after the merchant: card payments, SEPA
# details, dates, references. Anything from one of these on is not the merchant.
_TRAILING = (
    "Carta N.",
    "Addebito SDD",
    "Dt-ord:",
    "Data operazione",
    "Data inserimento",
    "Info-Cli:",
    "Banca Ord:",
    "Mand ",
    "Causale:",
)
# Whole segments that carry no merchant information when joined with " | ".
_METADATA_SEGMENT = re.compile(
    r"^(CARD_PAYMENT|TRANSFER|ATM|TOPUP|FEE|SEPA[ _A-Z]*|VISA \d+|MASTERCARD \d+|"
    r"IBAN:.*|MCC:.*|Ref:.*|Currency:.*|\d{2}/\d{2}/\d{4}.*)$",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Rule:
    """A text the description contains, and the category that follows from it.

    A pattern written between slashes is a regular expression instead: one rule
    for a family the bank spells in too many ways to list (`/amazon (eu|payments)/`).
    """

    key: str
    pattern: str
    category: str

    @property
    def expression(self) -> str | None:
        """The expression this rule matches with, or None when it is plain text."""
        return _expression_of(self.pattern)


def merchant_name(description: str) -> str:
    """Reduce a raw description to the merchant it names.

    `"L Ortobello S.n.c. Di Ah | CARD_PAYMENT | VISA 7883"` becomes
    `"L Ortobello S.n.c. Di Ah"`; a description with no merchant part is
    returned as it is, so an unknown row still gets a stable name.
    """
    text = description or ""
    for marker in _TRAILING:
        position = text.find(marker)
        if position > 0:
            text = text[:position]
    for segment in text.split(SEPARATOR):
        candidate = _WHITESPACE.sub(" ", segment).strip()
        if candidate and not _METADATA_SEGMENT.match(candidate):
            return candidate
    return _WHITESPACE.sub(" ", text).strip() or "Unknown"


def rule_key(text: str) -> str:
    """The text as the rules compare it: trimmed, spaces collapsed, lower case.

    A pattern typed by a human can carry stray runs of spaces while the
    descriptions only ever produce single ones, and a pattern that never comes
    back would silently match nothing.
    """
    return _WHITESPACE.sub(" ", text.strip()).lower()


def rule_pattern(text: str) -> tuple[str, str | None]:
    """The key that identifies a rule, and the expression it matches with.

    A pattern written between slashes -- `/amazon (eu|payments)/` -- is a
    regular expression, one rule for a family the bank spells in too many ways
    to list; anything else is the piece of text it looks like. The key of plain
    text is the text lower case, because that is how it is compared; the key of
    an expression is the pattern as typed, because inside one the case is part
    of it -- `\\D` is not `\\d`.
    """
    typed = _WHITESPACE.sub(" ", text.strip())
    expression = _expression_of(typed)
    if expression is None:
        return typed.lower(), None
    return typed, expression


def _expression_of(pattern: str) -> str | None:
    """What is between the slashes of a pattern, or None when it is plain text.

    A lone slash and `//` are text: an empty expression matches everything, and
    a pattern that merely holds a slash must not become one by accident.
    """
    if (
        len(pattern) > 2
        and pattern.startswith(_REGEX_DELIMITER)
        and pattern.endswith(_REGEX_DELIMITER)
    ):
        return pattern[1:-1]
    return None


@lru_cache(maxsize=None)
def _expression(source: str) -> re.Pattern[str]:
    """The compiled expression for a rule's source, once per source.

    Compiling at every match would recompile the whole book for every movement,
    and a sync runs it against every description in the ledger.
    """
    return re.compile(source, re.IGNORECASE)


def _matches(rule: Rule, text: str) -> bool:
    """Whether the rule claims a description, as the rules compare texts."""
    source = rule.expression
    if source is None:
        return bool(rule.key) and rule.key in text
    return _expression(source).search(text) is not None


def matching_rule(description: str, rules: Iterable[Rule]) -> Rule | None:
    """The rule that decides for this description, or None when no rule does.

    The description is compared as the bank writes it, so a rule can hold text
    the merchant name drops — `"addebito sdd"`, a card's metadata — and not only
    the name reduced from it. An expression sees the same text: spaces collapsed
    and lower case.

    The longest pattern wins, counted on what it says: the text, or the
    expression between the slashes. `"amazon prime"` is a statement about fewer
    descriptions than `"amazon"`, so where both match the narrower one speaks;
    between two patterns of the same length the alphabetical order keeps the
    answer the same between two runs. An expression is no exception: one written
    to name a family (`/amazon (eu|payments)/`) is longer than the words it
    replaces and takes their movements, while a broader one steals nothing from a
    narrower text that still matches.
    """
    candidates = _candidate_rules(description, rules)
    if not candidates:
        return None
    return min(candidates, key=lambda rule: (-len(rule.expression or rule.key), rule.key))


@dataclass(frozen=True)
class Stake:
    """What a merchant's waiting movements are worth, for one decision.

    A proposal is about a merchant, not about one movement: the queue cannot
    show "the amount" of it, so it shows what a yes would settle.
    """

    total: Decimal
    movements: int
    first_date: str
    last_date: str


def uncovered_spending(ledger: Ledger) -> dict[str, Stake]:
    """Per merchant, the spending the queue is still holding, keyed by name.

    The rows are the queue's own — settled outflows in the review bucket — so a
    figure shown on a proposal never disagrees with the list underneath it. A
    merchant with nothing left waiting is absent: the proposal is then a
    decision about nothing, and the queue says so instead of showing a zero.
    """
    stakes: dict[str, Stake] = {}
    for row in ledger.conn.execute(
        f"SELECT t.description, t.date, t.amount FROM transactions t {UNCATEGORIZED_WHERE}"
        " ORDER BY t.date",
        (UNCATEGORIZED,),
    ):
        merchant = merchant_name(row["description"])
        # Spending, so the sign is dropped: the queue holds outflows only.
        total = abs(parse_decimal(row["amount"]))
        stake = stakes.get(merchant)
        if stake is None:
            stakes[merchant] = Stake(total, 1, row["date"], row["date"])
        else:
            stakes[merchant] = Stake(
                stake.total + total, stake.movements + 1, stake.first_date, row["date"]
            )
    return stakes


class RuleBook:
    """The `rules` table: which text belongs to which category."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def rules(self) -> list[Rule]:
        return [
            Rule(row["key"], row["pattern"], row["category"])
            for row in self.conn.execute(
                "SELECT key, pattern, category FROM rules ORDER BY category, pattern"
            )
        ]

    def set_rule(self, pattern: str, category: str, ledger: Ledger) -> int:
        """Create or change a rule, and make the movements agree with it now.

        Everything the rule explains carries its category afterwards, whether it
        was waiting in the queue or another rule used to hold it: that is what
        lets one broad rule replace a pile of merchant rules. A category no rule
        matching the description would assign is a person's decision and stays.
        An expression that does not compile is refused here, with the reason: a
        rule that could never match must not reach the ledger.
        Returns how many movements the rule holds afterwards.
        """
        if category == UNCATEGORIZED:
            raise ValueError("a rule cannot point at the review bucket: it would categorize nothing")
        key, expression = rule_pattern(pattern)
        if not key:
            raise ValueError("a rule needs a text to look for")
        if expression is not None:
            try:
                _expression(expression)
            except re.error as exc:
                raise ValueError(f"espressione non valida: {exc}") from exc
        ledger.category(category)
        rule = Rule(key, _WHITESPACE.sub(" ", pattern.strip()), category)
        before = self.rules()
        with self.conn:
            self.conn.execute(
                """INSERT INTO rules (key, pattern, category) VALUES (?, ?, ?)
                   ON CONFLICT (key) DO UPDATE SET
                       pattern = excluded.pattern, category = excluded.category""",
                (rule.key, rule.pattern, category),
            )
        after = self.rules()
        _apply_rules(ledger, before, after)
        # A pending proposal this rule has just answered: leaving it would leave
        # the queue asking about a movement the rule has already decided.
        for row in ledger.suggestions("pending"):
            if _matches(rule, rule_key(row["merchant"])):
                ledger.decide_suggestion(row["merchant"], "dismissed")
        return rule_usage(ledger, after).get(rule.key, 0)

    def remove_rule(self, pattern: str, ledger: Ledger) -> int | None:
        """Drop a rule, and let the rules that still match take its movements.

        Returns how many movements it held, or None when there was no rule. A
        movement no remaining rule explains goes back to the queue.
        """
        key = rule_pattern(pattern)[0]
        before = self.rules()
        if not any(rule.key == key for rule in before):
            return None
        held = rule_usage(ledger, before).get(key, 0)
        with self.conn:
            self.conn.execute("DELETE FROM rules WHERE key = ?", (key,))
        _apply_rules(ledger, before, self.rules())
        return held


def rule_usage(ledger: Ledger, rules: Sequence[Rule]) -> dict[str, int]:
    """How many movements each rule holds right now, by the rule's key."""
    usage: dict[str, int] = {}
    for _, description, category in _categorized_transactions(ledger):
        rule = matching_rule(description, rules)
        if rule is None or rule.category != category:
            continue
        usage[rule.key] = usage.get(rule.key, 0) + 1
    return usage


def categorize(ledger: Ledger, book: RuleBook) -> int:
    """Apply the rules to the movements nobody has decided yet.

    The rules have not changed, so nothing moves: what waited in `Uncategorized`
    takes the category of the rule that explains it, and a merchant no rule
    knows is left there rather than guessed.
    """
    rules = book.rules()
    return _apply_rules(ledger, rules, rules)


def _candidate_rules(description: str, rules: Sequence[Rule]) -> list[Rule]:
    """Every rule that claims the description: the text it contains, or the
    expression that matches it."""
    text = rule_key(description)
    return [rule for rule in rules if _matches(rule, text)]


def _categorized_transactions(ledger: Ledger) -> list[tuple[int, str, str]]:
    """(transaction id, description, category) for every movement holding exactly one.

    A split carries several category postings and a transfer leg none, so the
    join keeps exactly one and both shapes stay out of a rule's reach: neither
    is a rule's work, and neither should a rule move.
    """
    rows = ledger.conn.execute(
        """SELECT t.id AS id, t.description AS description, a.name AS category
           FROM transactions t
           JOIN postings p ON p.transaction_id = t.id
           JOIN accounts a ON a.id = p.account_id
           WHERE a.type = 'category'
           GROUP BY t.id
           HAVING COUNT(*) = 1"""
    ).fetchall()
    return [(row["id"], row["description"], row["category"]) for row in rows]


def _apply_rules(ledger: Ledger, before: Sequence[Rule], after: Sequence[Rule]) -> int:
    """Make the movements say what the rules say, and answer how many changed.

    A movement the rules decided carries the category of the rule that decides
    it now; one still waiting in the queue is decided for the first time; one
    whose rule is gone goes back to the queue. A category that no rule matching
    the description would assign it is a person's decision: the rules fill the
    empty, follow their own changes, and never overrule that.
    """
    changed = 0
    for transaction_id, description, category in _categorized_transactions(ledger):
        # Whose work it was, not who decides it now: a legacy rule shadowed by a
        # longer text still held this movement, and it must follow the winner.
        theirs = any(rule.category == category for rule in _candidate_rules(description, before))
        if category != UNCATEGORIZED and not theirs:
            continue
        winner = matching_rule(description, after)
        wanted = winner.category if winner else UNCATEGORIZED
        if wanted == category:
            continue
        ledger.set_category(transaction_id, ledger.category(wanted))
        changed += 1
    return changed
