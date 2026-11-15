"""What the ledger defines besides the class: the SQL fragments every reading shares
(the only definitions of spending, rare, essential, waiting), the balance types,
the result types, and the helpers the ledger's methods use."""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Iterator

from amonhen.dedup import content_hash
from amonhen.models import IncomingTransaction, RecordAction, format_decimal, parse_decimal
from amonhen.settings import UNCATEGORIZED

log = logging.getLogger("amonhen.ledger")

# A pending row becomes the settled transaction when the bank reports the same
# amount on the same account within this many days.
PENDING_WINDOW_DAYS = 3
TRANSFER_CLEARING = "Transfer clearing"
# A valuation is the one movement no bank reported: the difference between the cash
# a broker's account really holds and what its movements add up to. Its content hash
# starts with this, which is how the matcher and the rules leave it out; its other
# side sits on the virtual account below, so a purchase is neither income nor
# spending, and that account's balance is what went into the portfolio, net.
VALUATION_PREFIX = "valuation:"
INVESTMENTS_ACCOUNT = "Investimenti"

# What makes spending rare, or essential: its category's flag or a flag on one of
# the movement's tags. These two fragments are the only definition, and they expect
# a category posting's account as `a` and its transaction as `t`.
_FLAGGED_SQL = """(a.{flag} = 1 OR EXISTS (
    SELECT 1 FROM transaction_tags tt JOIN tags g ON g.id = tt.tag_id
    WHERE tt.transaction_id = t.id AND g.{flag} = 1
))"""
RARE_SQL = _FLAGGED_SQL.format(flag="episodic")
ESSENTIAL_SQL = _FLAGGED_SQL.format(flag="essential")

# What a category posting counts for as spending. Money out always does; money in
# does when a person put it in a category that is not income, because that is what
# a refund is: a posting of the opposite sign, which takes the spending down. The
# review bucket is nobody's decision yet, so a credit waiting there counts for
# nothing. The only definition, and like the two above it expects `a` and `t`.
SPENDING_SQL = f"""(CAST(t.amount AS REAL) < 0
    OR (a.income = 0 AND a.name <> '{UNCATEGORIZED}'))"""

# A category that holds money towards every expense of the account it reaches. It
# is part of the spending above, so what is left to pay is net of it, and it is
# never a spending of its own: not rare, not essential, not a row among the categories.
CONTRIBUTION_SQL = "a.contribution = 1"

# What waits in the review bucket: a posting on the `Uncategorized` category, and
# no leg of a transfer — linking a pair moves a leg's posting to the clearing
# account, which is virtual.
_WAITING_SQL = """
    AND EXISTS (
        SELECT 1 FROM postings p JOIN accounts a ON a.id = p.account_id
        WHERE p.transaction_id = t.id AND a.type = 'category' AND a.name = ?
    )
    AND NOT EXISTS (
        SELECT 1 FROM postings p JOIN accounts a ON a.id = p.account_id
        WHERE p.transaction_id = t.id AND a.type = 'virtual'
    )"""

# What one category can decide: a movement whose balancing side is a single
# posting. A split is what it leaves out: several category postings are the
# person's own division of the movement, and pointing it at one category would
# throw the parts away.
DECIDABLE_BY_ONE_CATEGORY = """
    AND (SELECT COUNT(*) FROM postings p JOIN accounts a ON a.id = p.account_id
         WHERE p.transaction_id = t.id AND a.type = 'category') = 1"""

# Settled spending still waiting. The queue counts its rows and a proposal's stake
# is read with this same fragment, so the two can never disagree about what is
# still undecided.
UNCATEGORIZED_WHERE = "WHERE t.status = 'BOOK' AND CAST(t.amount AS REAL) < 0" + _WAITING_SQL

# Settled money in still waiting, from a date on (section 5.5). Until somebody
# decides it counts as neither a refund nor a contribution. Takes the date, then
# the bucket's name.
CREDITS_WHERE = (
    "WHERE t.status = 'BOOK' AND CAST(t.amount AS REAL) > 0 AND t.date >= ?"
    + _WAITING_SQL
    + DECIDABLE_BY_ONE_CATEGORY
)

_TRANSACTION_COLUMNS = (
    "account_id", "date", "amount", "description", "status", "external_id",
    "content_hash", "source", "source_file", "raw_payload", "counterparty",
    "counterparty_account", "currency",
)


@dataclass(frozen=True)
class Deletion:
    """A movement taken out of the ledger, and what had to be undone with it."""

    transaction_id: int
    unlinked_pair: bool


@dataclass(frozen=True)
class DeletedTotal:
    """What a person deleted from an account: how much, and over how many rows."""

    amount: Decimal
    count: int


@dataclass(frozen=True)
class BalanceCheck:
    account_id: int
    as_of: dt.date
    opening: Decimal
    declared: Decimal
    computed: Decimal
    kind: str = "available"
    source: str = ""

    @property
    def difference(self) -> Decimal:
        return self.declared - self.computed

    # What a person deleted would have been part of this figure, and is not.
    # `Booked` carries only the settled movements and `available` all of them,
    # exactly like the two figures the bank declares.
    suppressed: Decimal = Decimal("0")
    suppressed_count: int = 0

    @property
    def ok(self) -> bool:
        return self.difference == 0

    @property
    def explained(self) -> bool:
        """The difference is the movements a person deleted, and nothing else.

        A check that fails for a decision taken by hand is not a defect: saying
        so is what keeps the panel's red for the differences nobody decided.
        """
        return not self.ok and self.suppressed_count > 0 and self.difference == self.suppressed


# EB tags every balance it declares with a type, and the types fall into two
# groups that are different numbers for the same date — the ones that include
# the pending movements and the ones that leave them out. The order inside each
# group is what to prefer when the bank declares several: the interim figures
# describe now, the closing ones the end of a statement period. This list is the
# one section 5.4 of the spec names: a type outside it and outside the forecasts
# is read by nothing.
BANK_BALANCE_TYPES = (
    ("ITAV", "available"), ("CLAV", "available"), ("OPAV", "available"),
    ("ITBD", "booked"), ("CLBD", "booked"), ("OPBD", "booked"), ("PRCD", "booked"),
)
# The last two are not EB types: they are the words a figure a person wrote is
# tagged with, so that row lands in the bucket of the figure it stands for.
BALANCE_TYPES = (*BANK_BALANCE_TYPES, ("AVAILABLE", "available"), ("BOOKED", "booked"))
BALANCE_KINDS = dict(BALANCE_TYPES)
BALANCE_TYPE_ORDER = {name: index for index, (name, _kind) in enumerate(BALANCE_TYPES)}

# What a bank expects an account to hold on a coming date. It describes a future
# that has not happened, so it is neither checked against the ledger nor a point of
# the net worth: it is kept for `Ledger.overdraft_forecast` alone.
FORECAST_SOURCES_SQL = "('eb:FWAV', 'eb:XPCD')"

_COUNTED_BANK_SOURCES = tuple(f"eb:{name}" for name, _kind in BANK_BALANCE_TYPES)
_COUNTED_BANK_SOURCES_SQL = "(" + ", ".join(f"'{source}'" for source in _COUNTED_BANK_SOURCES) + ")"

# What counts as a balance: every figure a person wrote, and of the bank's only the
# types above. A type nobody has read the definition of may be a forecast, a credit
# line or a statement note, so it stays out instead of being guessed: that guess is
# how `FWAV` once failed the check and bent the liquidity curve with nobody told.
COUNTED_SOURCES_SQL = f"(source NOT LIKE 'eb:%' OR source IN {_COUNTED_BANK_SOURCES_SQL})"
UNRECOGNIZED_SOURCES_SQL = (
    f"(source LIKE 'eb:%' AND source NOT IN {_COUNTED_BANK_SOURCES_SQL}"
    f" AND source NOT IN {FORECAST_SOURCES_SQL})"
)


def bank_balance_source(balance_type: str | None) -> str:
    """The `eb:<TYPE>` tag a balance from the bank is recorded under."""
    return f"eb:{(balance_type or 'unknown').strip().upper()}"


def balance_kind(source: str) -> str:
    """Which of the bank's two figures a counted balance is.

    Comparing a declaration against the wrong figure invents a difference that
    is exactly the pending sum, so the type decides which computed balance it is
    asserted against. A figure a person wrote that names neither counts as
    available, which is the figure the ledger's own arithmetic produces. A bank's
    type outside the list has no kind at all, and `COUNTED_SOURCES_SQL` keeps it
    from reaching here.
    """
    if source.startswith("eb:") and source not in _COUNTED_BANK_SOURCES:
        raise ValueError(f"{source} is not a balance this ledger reads")
    return BALANCE_KINDS.get(_balance_type(source), "available")


def _balance_type(source: str) -> str:
    """The EB type inside a `eb:<TYPE>` source tag, or "" for anything else."""
    return source.partition(":")[2].strip().upper()


def _source_priority(source: str) -> int:
    """Smaller is better; a type we do not recognise loses to every one we do."""
    return BALANCE_TYPE_ORDER.get(_balance_type(source), len(BALANCE_TYPE_ORDER))


def _declaration_order(row: sqlite3.Row) -> tuple[str, bool, int]:
    """Newest date first, then the bank's own number, then the type we trust more."""
    return (row["date"], row["source"].startswith("eb:"), -_source_priority(row["source"]))


@dataclass(frozen=True)
class _Plan:
    """What `Ledger.record` decided about one movement, before writing it."""

    action: RecordAction
    digest: str
    row: sqlite3.Row | None = None
    tombstone: sqlite3.Row | None = None


def _numbered(
    transactions: Iterable[IncomingTransaction],
) -> Iterator[tuple[IncomingTransaction, int]]:
    """Each movement with its occurrence among identical ones in the batch."""
    occurrences: dict[str, int] = {}
    for txn in transactions:
        key = content_hash(txn.account_id, txn.date, txn.amount, txn.description)
        occurrences[key] = occurrences.get(key, 0) + 1
        yield txn, occurrences[key]


def _movement_json(txn: IncomingTransaction) -> str:
    """A held movement as it arrived, minus what the ledger assigns on writing."""
    return json.dumps(
        {
            "date": txn.date.isoformat(),
            "amount": format_decimal(txn.amount),
            "description": txn.description,
            "status": txn.status,
            "source": txn.source,
            "external_id": txn.external_id,
            "counterparty": txn.counterparty,
            "counterparty_account": txn.counterparty_account,
            "currency": txn.currency,
            "raw": txn.raw,
            "source_file": txn.source_file,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _movement_from_json(text: str, account_id: int, balancing_account_id: int) -> IncomingTransaction:
    data = json.loads(text)
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(data["date"]),
        amount=parse_decimal(data["amount"]),
        description=data["description"],
        status=data["status"],
        source=data["source"],
        balancing_account_id=balancing_account_id,
        external_id=data.get("external_id"),
        counterparty=data.get("counterparty"),
        counterparty_account=data.get("counterparty_account"),
        currency=data.get("currency") or "EUR",
        raw=data.get("raw") or {},
        source_file=data.get("source_file"),
    )
