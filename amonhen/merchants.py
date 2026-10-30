"""Merchant normalization and the rules built on top of it.

Desiderata 5.5 steps 1 and 2: reduce the raw description to the merchant it
names, then apply the rules. A rule is a piece of text the description contains,
or a regular expression written between slashes, so one rule covers a family of
movements the bank spells differently — the merchant name being just one of the
texts a rule may hold. A rule may be narrowed to an account and a range of
amounts, and does one of three things: assign a category, delete the movement,
or record it as a transfer to a destination. Every step is deterministic, so it
runs inside ingest without making it fail when something is unknown.
"""
import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Iterable, Sequence

from amonhen.db import deferred_commits
from amonhen.ledger import TRANSFER_CLEARING, UNCATEGORIZED_WHERE, Ledger
from amonhen.models import format_decimal, parse_decimal
from amonhen.settings import UNCATEGORIZED

# What a rule does to a movement it matches. Where several kinds match, a
# deletion wins over a transfer and a transfer over a category: a movement that
# is gone has no category, and a transfer is not spending to categorize.
ACTIONS = ("category", "delete", "transfer")

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

# What one category can decide: a movement whose balancing side is a single
# posting. It rides on `UNCATEGORIZED_WHERE`, whose rows are the queue's, and it
# is shared by the stake and by the acceptance so the two cannot disagree about
# what a merchant's yes would settle. A split is what it leaves out: several
# category postings are the person's own division of the movement, and pointing
# it at one category would throw the parts away.
DECIDABLE_BY_ONE_CATEGORY = """
    AND (SELECT COUNT(*) FROM postings p JOIN accounts a ON a.id = p.account_id
         WHERE p.transaction_id = t.id AND a.type = 'category') = 1"""


@dataclass(frozen=True)
class Rule:
    """A text the description contains, its conditions, and what follows from it.

    A pattern written between slashes is a regular expression instead: one rule
    for a family the bank spells in too many ways to list (`/amazon (eu|payments)/`).
    `target` is the category for a category rule and the destination for a
    transfer; a deletion has none. The amounts bound the movement's size, sign
    left out: a person says "between 5 and 10 euro", not "between -10 and -5".
    """

    key: str
    pattern: str
    target: str | None
    action: str = "category"
    account_id: int | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    id: int | None = None

    @property
    def expression(self) -> str | None:
        """The expression this rule matches with, or None when it is plain text."""
        return _expression_of(self.pattern)

    @property
    def conditions(self) -> int:
        """How many conditions narrow the text: the tie-break between two rules."""
        return sum(
            value is not None for value in (self.account_id, self.amount_min, self.amount_max)
        )


@dataclass(frozen=True)
class Movement:
    """What a rule's conditions read of a movement besides its description."""

    account_id: int
    amount: Decimal


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


def _matches(rule: Rule, text: str, movement: Movement | None = None) -> bool:
    """Whether the rule claims a description, as the rules compare texts.

    Without a movement only the text is compared: that is the question "does a
    rule know this merchant", which the proposals ask about a name, not a row.
    """
    source = rule.expression
    if source is None:
        found = bool(rule.key) and rule.key in text
    else:
        found = _expression(source).search(text) is not None
    if not found or movement is None:
        return found
    if rule.account_id is not None and movement.account_id != rule.account_id:
        return False
    size = abs(movement.amount)
    if rule.amount_min is not None and size < rule.amount_min:
        return False
    if rule.amount_max is not None and size > rule.amount_max:
        return False
    return True


def matching_rule(
    description: str, rules: Iterable[Rule], movement: Movement | None = None
) -> Rule | None:
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

    Between two rules of the same text, the one with more conditions is the
    narrower statement and wins too.
    """
    candidates = _candidate_rules(description, rules, movement)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda rule: (
            -len(rule.expression or rule.key),
            -rule.conditions,
            rule.key,
            rule.id or 0,
        ),
    )


@dataclass(frozen=True)
class StakeMovement:
    """One movement a proposal would decide, as the bank printed it."""

    id: int
    date: str
    amount: Decimal
    description: str
    account: str


@dataclass(frozen=True)
class Stake:
    """What a merchant's waiting movements are worth, for one decision.

    A proposal is about a merchant, not about one movement: the queue cannot
    show "the amount" of it, so it shows what a yes would settle — and the
    movements themselves, oldest first, because a merchant's name alone is not
    enough to say yes to: the date and the amount are what a person recognises.
    """

    total: Decimal
    movements: int
    first_date: str
    last_date: str
    items: tuple[StakeMovement, ...] = ()


def uncovered_spending(ledger: Ledger) -> dict[str, Stake]:
    """Per merchant, the spending the queue is still holding, keyed by name.

    The rows are the queue's own — settled outflows in the review bucket — so a
    figure shown on a proposal never disagrees with the list underneath it. A
    merchant with nothing left waiting is absent: the proposal is then a
    decision about nothing, and the queue says so instead of showing a zero.
    """
    stakes: dict[str, Stake] = {}
    for row in ledger.conn.execute(
        "SELECT t.id, t.description, t.date, t.amount, a.name AS account"
        f" FROM transactions t JOIN accounts a ON a.id = t.account_id {UNCATEGORIZED_WHERE}"
        f" {DECIDABLE_BY_ONE_CATEGORY} ORDER BY t.date, t.id",
        (UNCATEGORIZED,),
    ):
        merchant = merchant_name(row["description"])
        # Spending, so the sign is dropped: the queue holds outflows only.
        total = abs(parse_decimal(row["amount"]))
        item = StakeMovement(row["id"], row["date"], total, row["description"], row["account"])
        stake = stakes.get(merchant)
        if stake is None:
            stakes[merchant] = Stake(total, 1, row["date"], row["date"], (item,))
        else:
            stakes[merchant] = Stake(
                stake.total + total,
                stake.movements + 1,
                stake.first_date,
                row["date"],
                stake.items + (item,),
            )
    return stakes


class RuleBook:
    """The `rules` table: which text, under which conditions, does what."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def rules(self) -> list[Rule]:
        return [
            Rule(
                key=row["key"],
                pattern=row["pattern"],
                target=row["target"],
                action=row["action"],
                account_id=row["account_id"],
                amount_min=_amount_or_none(row["amount_min"]),
                amount_max=_amount_or_none(row["amount_max"]),
                id=row["id"],
            )
            for row in self.conn.execute(
                """SELECT id, key, pattern, action, target, account_id, amount_min, amount_max
                   FROM rules ORDER BY action, target, pattern, id"""
            )
        ]

    def rule(self, rule_id: int) -> Rule:
        for rule in self.rules():
            if rule.id == rule_id:
                return rule
        raise KeyError(f"rule {rule_id} not found")

    def set_rule(
        self,
        pattern: str,
        target: str | None,
        ledger: Ledger,
        *,
        action: str = "category",
        account_id: int | None = None,
        amount_min: Decimal | None = None,
        amount_max: Decimal | None = None,
        rule_id: int | None = None,
    ) -> int:
        """Create or change a rule, and make the movements agree with it now.

        Everything the rule explains follows it afterwards, whether it was
        waiting in the queue or another rule used to hold it: that is what lets
        one broad rule replace a pile of merchant rules. A category no rule
        matching the description would assign is a person's decision and stays.
        A rule that deletes takes the movements it matches out of the ledger now,
        into the trash, and every later sync does the same with the new ones.
        Without `rule_id` a rule with the same text and conditions is the one
        changed, so writing the same rule twice is one rule.
        Returns how many movements the rule holds afterwards.
        """
        rule = self.checked(
            pattern,
            target,
            ledger,
            action=action,
            account_id=account_id,
            amount_min=amount_min,
            amount_max=amount_max,
            rule_id=rule_id,
        )
        before = self.rules()
        values = (
            rule.key,
            rule.pattern,
            rule.action,
            rule.target,
            rule.account_id,
            _amount_text(rule.amount_min),
            _amount_text(rule.amount_max),
        )
        if rule_id is None:
            rule_id = self._same_identity(rule)
        try:
            with self.conn:
                if rule_id is None:
                    rule_id = self.conn.execute(
                        """INSERT INTO rules
                               (key, pattern, action, target, account_id, amount_min, amount_max)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        values,
                    ).lastrowid
                else:
                    self.conn.execute(
                        """UPDATE rules SET key = ?, pattern = ?, action = ?, target = ?,
                               account_id = ?, amount_min = ?, amount_max = ?
                           WHERE id = ?""",
                        (*values, rule_id),
                    )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "una regola con lo stesso testo e le stesse condizioni c'è già"
            ) from exc
        after = self.rules()
        apply_rule_changes(ledger, before, after)
        # A pending proposal this rule has just answered: leaving it would leave
        # the queue asking about a movement the rule has already decided.
        for row in ledger.suggestions("pending"):
            if _matches(rule, rule_key(row["merchant"])):
                ledger.decide_suggestion(row["merchant"], "dismissed")
        return rule_usage(ledger, after).get(rule_id, 0)

    def checked(
        self,
        pattern: str,
        target: str | None,
        ledger: Ledger,
        *,
        action: str = "category",
        account_id: int | None = None,
        amount_min: Decimal | None = None,
        amount_max: Decimal | None = None,
        rule_id: int | None = None,
    ) -> Rule:
        """The rule as it would be stored, or the reason it cannot be.

        Writes nothing but a category it names, which `Ledger.category` creates.
        """
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action!r}")
        if rule_id is not None:
            self.rule(rule_id)
        key, expression = rule_pattern(pattern)
        if not key:
            raise ValueError("a rule needs a text to look for")
        if expression is not None:
            try:
                _expression(expression)
            except re.error as exc:
                raise ValueError(f"espressione non valida: {exc}") from exc
        target = (target or "").strip() or None
        if action == "category":
            if target is None:
                raise ValueError("a category rule needs a category")
            if target == UNCATEGORIZED:
                raise ValueError(
                    "a rule cannot point at the review bucket: it would categorize nothing"
                )
            ledger.category(target)
        elif action == "transfer":
            if target is None:
                raise ValueError("a transfer rule needs a destination")
            if target == TRANSFER_CLEARING:
                raise ValueError(f"{TRANSFER_CLEARING!r} is the pairing account, not a destination")
            existing = ledger.find_account(name=target)
            if existing is not None and existing["type"] == "real":
                # An account added by hand takes the other half the rule
                # writes; a connected one reports its own.
                ledger.mirror_target(target)
                if account_id is not None and existing["id"] == account_id:
                    raise ValueError("a movement cannot be a transfer to its own account")
            elif existing is not None and existing["type"] != "virtual":
                raise ValueError(f"{target!r} already names a {existing['type']} account")
        else:
            target = None
        if account_id is not None and ledger.account(account_id)["type"] != "real":
            raise ValueError(f"account {account_id} is not a real account")
        for bound in (amount_min, amount_max):
            if bound is not None and bound < 0:
                raise ValueError("an amount bound is a size: it cannot be negative")
        if amount_min is not None and amount_max is not None and amount_min > amount_max:
            raise ValueError("the minimum amount is above the maximum")
        return Rule(
            key=key,
            pattern=_WHITESPACE.sub(" ", pattern.strip()),
            target=target,
            action=action,
            account_id=account_id,
            amount_min=amount_min,
            amount_max=amount_max,
            id=rule_id,
        )

    def _same_identity(self, rule: Rule) -> int | None:
        identity = (rule.key, rule.account_id, rule.amount_min, rule.amount_max)
        for existing in self.rules():
            if (existing.key, existing.account_id, existing.amount_min, existing.amount_max) == identity:
                return existing.id
        return None

    def remove_rule(self, pattern: str, ledger: Ledger) -> int | None:
        """Drop the rule for a text that has no conditions — the command line's form.

        Returns how many movements it held, or None when there was no such rule.
        """
        key = rule_pattern(pattern)[0]
        for rule in self.rules():
            if rule.key == key and rule.conditions == 0 and rule.id is not None:
                return self.remove(rule.id, ledger)
        return None

    def remove(self, rule_id: int, ledger: Ledger) -> int:
        """Drop a rule, and let the rules that still match take its movements.

        Returns how many movements it held. A movement no remaining rule explains
        goes back to the queue — a transfer the rule recorded as well. What a
        deleting rule took stays in the trash, where it can be restored now.
        """
        before = self.rules()
        if not any(rule.id == rule_id for rule in before):
            raise KeyError(f"rule {rule_id} not found")
        held = rule_usage(ledger, before).get(rule_id, 0)
        with self.conn:
            self.conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        apply_rule_changes(ledger, before, self.rules())
        return held


def preview(ledger: Ledger, rule: Rule, limit: int = 20) -> dict:
    """The movements a rule would take, before it is written.

    Every movement on a real account whose text and conditions it matches —
    including the ones another rule decides now, because this one may take them.
    A deletion is the reason this exists: what it removes is shown first.
    """
    found = [
        row
        for row in _movement_rows(ledger)
        if _matches(rule, rule_key(row["description"]), _movement_of(row))
    ]
    found.sort(key=lambda row: (row["date"], row["id"]), reverse=True)
    return {"count": len(found), "items": found[:limit]}


def deleting_rule(ledger: Ledger, description: str, account_id: int, amount: Decimal) -> Rule | None:
    """The deleting rule that would take this movement again, if there is one."""
    deleting = _by_action(RuleBook(ledger.conn).rules())["delete"]
    return matching_rule(description, deleting, Movement(account_id, amount))


def _amount_or_none(text: str | None) -> Decimal | None:
    return None if text is None else parse_decimal(text)


def _amount_text(amount: Decimal | None) -> str | None:
    return None if amount is None else format_decimal(amount)


def rule_usage(ledger: Ledger, rules: Sequence[Rule]) -> dict[int, int]:
    """How many movements each rule holds right now, by the rule's id.

    A category rule holds the movements it decides and that carry its category;
    a transfer rule the ones recorded to its destination that it matches; a
    deleting rule the deleted movements, still in the trash, that it matches.
    """
    usage: dict[int, int] = {}

    def count(rule: Rule | None) -> None:
        if rule is not None and rule.id is not None:
            usage[rule.id] = usage.get(rule.id, 0) + 1

    by_action = _by_action(rules)
    for row in _movement_rows(ledger):
        if not _decidable(row):
            continue
        movement = _movement_of(row)
        kind = "category" if row["side_type"] == "category" else "transfer"
        rule = matching_rule(row["description"], by_action[kind], movement)
        if rule is not None and rule.target == row["side_name"]:
            count(rule)
    for row in _movement_rows(ledger):
        if row["mirror_account"] is not None:
            rule = matching_rule(row["description"], by_action["transfer"], _movement_of(row))
            if rule is not None and rule.target == row["mirror_account"]:
                count(rule)
    if by_action["delete"]:
        for row in ledger.deleted_transactions():
            movement = Movement(row["account_id"], parse_decimal(row["amount"]))
            count(matching_rule(row["description"], by_action["delete"], movement))
    return usage


def categorize(ledger: Ledger, book: RuleBook) -> int:
    """Apply the rules to what the ledger holds now, and say how many changed.

    The rules have not changed, so nothing a rule already decided moves: what
    waited in `Uncategorized` takes the category of the rule that explains it, a
    merchant no rule knows is left there rather than guessed, and what a deleting
    or transfer rule matches — a movement the last sync brought in — is deleted
    or recorded to its destination.
    """
    rules = book.rules()
    return apply_rule_changes(ledger, rules, rules)


def apply_rule_changes(ledger: Ledger, before: Sequence[Rule], after: Sequence[Rule]) -> int:
    """Make the movements say what the rules say, in the order the actions win.

    Deletions first, because a deleted movement has nothing left to decide; then
    the transfers, because a leg recorded to a destination has no category; then
    the categories, which see what the two before them left. One transaction:
    on the NAS every commit is a flush, and a rule can touch hundreds of rows.
    """
    with deferred_commits(ledger.conn):
        changed = _apply_deletions(ledger, after)
        changed += _apply_transfers(ledger, before, after)
        changed += _apply_categories(ledger, before, after)
    return changed


def waiting_transactions(ledger: Ledger, merchant: str) -> list[int]:
    """The ids of a merchant's queue rows that one category can decide.

    The predicate is the queue's, so a decision covers what the figure beside
    the proposal was about. What neither counts is a movement a single category
    cannot take: a split carries several category postings, its parts are a
    decision of the person, and pointing the movement at one category would
    throw them away. Such a row waits in the queue with the rest and is decided
    by opening it.
    """
    return [
        row["id"]
        for row in ledger.conn.execute(
            f"SELECT t.id, t.description FROM transactions t {UNCATEGORIZED_WHERE}"
            f" {DECIDABLE_BY_ONE_CATEGORY} ORDER BY t.date",
            (UNCATEGORIZED,),
        )
        if merchant_name(row["description"]) == merchant
    ]


def accept_merchant(
    ledger: Ledger, merchant: str, category: str, *, rule: str | None = None
) -> dict:
    """Decide one merchant's waiting movements, writing a rule only when asked.

    An acceptance is a decision about the movements the queue was holding: they
    take the chosen category one by one, as a person's own decision, and a
    person's decision is what the rules never overrule. The text of a rule is a
    statement about the movements the bank has not printed yet, and a rule for
    every accepted proposal would grow a rule for every spelling of every shop,
    so one is written only when `rule` carries the text someone wrote for it —
    and then the movements follow it instead.

    Returns what the decision did: the category, the rule if one was written,
    and how many movements it holds.
    """
    if category == UNCATEGORIZED:
        raise ValueError("a decision cannot point at the review bucket: it would decide nothing")
    if rule is not None:
        # `set_rule` refuses the review bucket, the empty text and an expression
        # that does not compile, and resolves the category itself: a rule that is
        # refused must not leave a category account behind for the pickers to offer.
        held = RuleBook(ledger.conn).set_rule(rule, category, ledger)
        return {"category": category, "rule": rule, "movements": held}
    account = ledger.category(category)
    decided = 0
    for transaction_id in waiting_transactions(ledger, merchant):
        ledger.set_category(transaction_id, account)
        decided += 1
    return {"category": category, "rule": None, "movements": decided}


def _candidate_rules(
    description: str, rules: Iterable[Rule], movement: Movement | None = None
) -> list[Rule]:
    """Every rule that claims the description: the text it contains, or the
    expression that matches it — and, given a movement, its conditions."""
    text = rule_key(description)
    return [rule for rule in rules if _matches(rule, text, movement)]


def _by_action(rules: Iterable[Rule]) -> dict[str, list[Rule]]:
    grouped: dict[str, list[Rule]] = {action: [] for action in ACTIONS}
    for rule in rules:
        grouped[rule.action].append(rule)
    return grouped


def _movement_rows(ledger: Ledger) -> list[sqlite3.Row]:
    """Every movement on a real account, with the side a rule may decide.

    `side_type` and `side_name` name the balancing posting when there is exactly
    one besides the real leg — a category, or a virtual account (a destination,
    or the clearing account of a pair, which `linked` tells apart); a split has
    several. Neither a split nor a paired leg is a rule's to decide or to move —
    except the pair a transfer rule wrote itself, whose other half is on the
    account `mirror_account` names. That other half is not a movement at all
    for the rules, and is left out: it carries the description it copied. A
    rejected pair pairs the leg with nothing, so it does not count as `linked`:
    otherwise the leg the matcher got wrong could never reach its rule.
    """
    return ledger.conn.execute(
        """SELECT t.id, t.date, t.amount, t.description, t.account_id,
                  r.name AS account,
                  (SELECT COUNT(*) FROM postings p JOIN accounts a ON a.id = p.account_id
                    WHERE p.transaction_id = t.id AND a.type IN ('category', 'virtual')) AS sides,
                  (SELECT a.type FROM postings p JOIN accounts a ON a.id = p.account_id
                    WHERE p.transaction_id = t.id AND a.type IN ('category', 'virtual')
                    LIMIT 1) AS side_type,
                  (SELECT a.name FROM postings p JOIN accounts a ON a.id = p.account_id
                    WHERE p.transaction_id = t.id AND a.type IN ('category', 'virtual')
                    LIMIT 1) AS side_name,
                  EXISTS (SELECT 1 FROM transfer_links l
                           WHERE (l.leg_a = t.id OR l.leg_b = t.id)
                             AND l.confirmed_by_human <> -1) AS linked,
                  (SELECT a.name FROM transactions m JOIN accounts a ON a.id = m.account_id
                    WHERE m.mirror_of = t.id) AS mirror_account,
                  t.status
           FROM transactions t JOIN accounts r ON r.id = t.account_id
           WHERE r.type = 'real' AND t.mirror_of IS NULL AND t.content_hash NOT LIKE 'valuation:%'
           ORDER BY t.date, t.id"""
    ).fetchall()


def _movement_of(row: sqlite3.Row) -> Movement:
    return Movement(row["account_id"], parse_decimal(row["amount"]))


def _decidable(row: sqlite3.Row) -> bool:
    """One balancing side and no pair: what a single rule may decide or move."""
    return row["sides"] == 1 and not row["linked"]


def _apply_deletions(ledger: Ledger, rules: Sequence[Rule]) -> int:
    """Take what a deleting rule matches out of the ledger, into the trash.

    Every movement, a split or a transfer leg included: a person asked for that
    text to be gone, and `delete_transaction` already knows how to take one leg
    of a pair without leaving the other hanging.
    """
    deleting = _by_action(rules)["delete"]
    if not deleting:
        return 0
    deleted = 0
    for row in _movement_rows(ledger):
        if matching_rule(row["description"], deleting, _movement_of(row)) is None:
            continue
        ledger.delete_transaction(row["id"])
        deleted += 1
    return deleted


def _apply_transfers(ledger: Ledger, before: Sequence[Rule], after: Sequence[Rule]) -> int:
    """Record what a transfer rule matches to its destination, and let go of
    what a transfer rule no longer claims.

    A leg goes to the destination whatever category it carried: the rule says
    the money is not spending, which no category can say. A destination that is
    a real account added by hand gets the other half written on it
    (`Ledger.mirror_transfer`), once the bank has settled the movement — a
    pending row is rewritten when it is booked, and the half would be left
    behind. A leg a removed rule had recorded goes back to the queue, where the
    category rules find it, and the half it wrote goes with the rule.
    """
    old = _by_action(before)["transfer"]
    new = _by_action(after)["transfer"]
    if not old and not new:
        return 0
    real = {
        row["name"]
        for row in ledger.conn.execute("SELECT name FROM accounts WHERE type = 'real'")
    }
    changed = 0
    for row in _movement_rows(ledger):
        mirrored = row["mirror_account"]
        if not (_decidable(row) or mirrored is not None):
            continue
        movement = _movement_of(row)
        winner = matching_rule(row["description"], new, movement)
        if mirrored is not None:
            current = mirrored
        else:
            current = row["side_name"] if row["side_type"] == "virtual" else None
        if winner is not None:
            if winner.target == current:
                continue
            to_real = winner.target in real
            if to_real and (row["status"] != "BOOK" or winner.target == row["account"]):
                continue
            if mirrored is not None:
                ledger.drop_mirror(row["id"])
            if to_real:
                ledger.mirror_transfer(row["id"], winner.target)
            else:
                ledger.move_to_virtual_account(row["id"], winner.target)
            changed += 1
            continue
        theirs = current is not None and any(
            rule.target == current
            for rule in _candidate_rules(row["description"], old, movement)
        )
        if theirs:
            if mirrored is not None:
                ledger.drop_mirror(row["id"])
            else:
                ledger.set_category(row["id"], ledger.uncategorized())
            changed += 1
    return changed


def _apply_categories(ledger: Ledger, before: Sequence[Rule], after: Sequence[Rule]) -> int:
    """Make the categories say what the category rules say.

    A movement the rules decided carries the category of the rule that decides
    it now; one still waiting in the queue is decided for the first time; one
    whose rule is gone goes back to the queue. A category that no rule matching
    the description would assign it is a person's decision: the rules fill the
    empty, follow their own changes, and never overrule that.
    """
    old = _by_action(before)["category"]
    new = _by_action(after)["category"]
    changed = 0
    for row in _movement_rows(ledger):
        if not _decidable(row) or row["side_type"] != "category":
            continue
        category = row["side_name"]
        movement = _movement_of(row)
        # Whose work it was, not who decides it now: a legacy rule shadowed by a
        # longer text still held this movement, and it must follow the winner.
        theirs = any(
            rule.target == category
            for rule in _candidate_rules(row["description"], old, movement)
        )
        if category != UNCATEGORIZED and not theirs:
            continue
        winner = matching_rule(row["description"], new, movement)
        wanted = winner.target if winner else UNCATEGORIZED
        if wanted == category:
            continue
        ledger.set_category(row["id"], ledger.category(wanted))
        changed += 1
    return changed
