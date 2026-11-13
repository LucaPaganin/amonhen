"""The bank as the sync sees it: accounts, movements, balances, and how a call fails.

`SyncService` and the `balances` command speak to a bank only through
`BankProvider`. Enable Banking is one implementation
(`amonhen.adapters.enable_banking.EnableBankingProvider`); the tests use one in
memory. Nothing here knows about HTTP, JSON payloads or `requests`: a provider
translates its own data and its own errors into these before they leave it.

The consent flow (`/connect`, `/callback`, the wizard's *Banca* step) is not
here on purpose: it is the most provider-specific part of the integration, and a
port drawn from one provider's redirects and sessions would be a guess about the
next one. Those routes use the Enable Banking adapter directly.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable

from amonhen.config import ConfiguredAccount
from amonhen.models import IncomingTransaction

# -- errors ---------------------------------------------------------------------
#
# Three outcomes the sync reacts to differently, whatever the provider: a consent
# that has to be renewed by a person, a quota that waiting will not cure, and a
# bank that could not be reached or refused for any other reason. The message is
# the provider's own words, because the app shows it.


class BankError(Exception):
    """A call to the bank did not return what was asked."""


class ConsentExpired(BankError):
    """The consent behind the account is no longer valid: a person must renew it."""


class RateLimited(BankError):
    """The bank refuses this account for too many requests; asking again spends the quota."""


class BankUnavailable(BankError):
    """The bank could not be reached, or refused the request for another reason."""


# -- data -----------------------------------------------------------------------


@dataclass(frozen=True)
class BankAccount:
    """What a bank says about one of its accounts. Every field may be missing."""

    uid: str | None = None
    iban: str | None = None
    currency: str | None = None


@dataclass(frozen=True)
class DeclaredBalance:
    """One figure the bank declares for an account.

    `balance_type` is the bank's own label (`ITAV`, `CLBD`, ...), which the ledger
    maps to what it counts (`ledger.bank_balance_source`). `date` is None when the
    bank gives no reference date, and the caller decides which day that means.
    """

    date: dt.date | None
    amount: Decimal
    balance_type: str | None
    currency: str | None = None


@dataclass
class FetchedWindow:
    """One window of a period, and what the bank answered for it.

    `error` is None when the window was read to its end; otherwise its movements
    are not in `transactions` at all, because half a window is not a window the
    ledger can trust as covered. An empty window that succeeded is an answer too.
    """

    date_from: dt.date
    date_to: dt.date
    transactions: list[IncomingTransaction] = field(default_factory=list)
    error: str | None = None


# -- the port -------------------------------------------------------------------


@runtime_checkable
class BankProvider(Protocol):
    """The operations the application asks of a bank, and nothing else.

    `account` is the entry of `accounts.json` the call is about. Movements come
    back as `IncomingTransaction`, the shape every source produces (the CSV and
    OFX adapters too), so the caller passes the ledger ids they are written under.
    """

    def connected_accounts(self, account: ConfiguredAccount) -> list[BankAccount]:
        """Every account the same consent as `account` covers."""
        ...

    def account_details(self, account: ConfiguredAccount) -> BankAccount:
        """The account's own identification, which a listing may leave out."""
        ...

    def transactions(
        self,
        account: ConfiguredAccount,
        date_from: dt.date,
        date_to: dt.date,
        *,
        account_id: int,
        balancing_account_id: int,
    ) -> list[IncomingTransaction]:
        """Every movement in the range, or the first error: all or nothing."""
        ...

    def transaction_windows(
        self,
        account: ConfiguredAccount,
        date_from: dt.date,
        date_to: dt.date,
        *,
        account_id: int,
        balancing_account_id: int,
    ) -> list[FetchedWindow]:
        """The range window by window, each with its own outcome.

        A window's failure is reported in the window; only a dead consent raises,
        because every other window would fail the same way.
        """
        ...

    def balances(self, account: ConfiguredAccount) -> list[DeclaredBalance]:
        """The figures the bank declares for the account now."""
        ...
