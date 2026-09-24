"""Domain types shared by ingest, ledger and reporting."""
import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

AccountType = Literal["real", "virtual", "category"]
TransactionStatus = Literal["BOOK", "PDNG"]
SourceKind = Literal["psd2", "import"]
RecordAction = Literal[
    "inserted", "duplicate", "promoted", "updated", "suppressed", "reimported"
]


def parse_decimal(value: str | Decimal | int | float) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def format_decimal(value: Decimal) -> str:
    """Canonical two-decimal text used for storage and hashing."""
    return str(value.quantize(Decimal("0.01")))


@dataclass(frozen=True)
class Account:
    name: str
    type: AccountType
    id: int | None = None
    institution: str | None = None
    iban: str | None = None
    external_uid: str | None = None
    currency: str = "EUR"
    opening_balance: Decimal | None = None
    opening_date: dt.date | None = None


@dataclass(frozen=True)
class Posting:
    account_id: int
    amount: Decimal
    note: str | None = None


@dataclass(frozen=True)
class IncomingTransaction:
    """One transaction as reported by a single source, before it reaches the ledger.

    `amount` is signed from the account holder's perspective: negative means the
    money left the account. The ledger balances it against
    `balancing_account_id`, which is a category account for a spend and the
    transfer clearing account for an internal transfer.
    """

    account_id: int
    date: dt.date
    amount: Decimal
    description: str
    status: TransactionStatus
    source: SourceKind
    balancing_account_id: int
    external_id: str | None = None
    counterparty: str | None = None
    counterparty_account: str | None = None
    currency: str = "EUR"
    raw: dict[str, Any] = field(default_factory=dict)
    source_file: str | None = None
