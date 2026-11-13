"""Enable Banking behind the `BankProvider` port.

The client (`client.py`) speaks Enable Banking: JWTs, pages, windows, the 429
backoff, JSON. The normalizer (`normalize.py`) reads that JSON. This class is the
adapter in the strict sense: it implements the port the application wrote, and
it is the one place where Enable Banking's data and errors become the
application's. Nothing above it sees a payload or a `requests` exception.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import TypeVar

import requests

from amonhen.adapters.enable_banking.client import (
    ConsentExpiredError,
    EnableBankingClient,
    RateLimitedError,
)
from amonhen.adapters.enable_banking.normalize import (
    bank_account,
    declared_balances,
    normalize_transaction,
)
from amonhen.config import ConfiguredAccount
from amonhen.models import IncomingTransaction
from amonhen.ports.bank import (
    BankAccount,
    BankUnavailable,
    ConsentExpired,
    DeclaredBalance,
    FetchedWindow,
    RateLimited,
)

T = TypeVar("T")


def translated(call: Callable[[], T]) -> T:
    """Run one call to the client, with its errors in the port's words.

    The order matters: a rate limit is also a `requests.HTTPError`, so it is
    recognized before the general case. The message is kept as the client wrote
    it, because the app and the logs show it to a person.
    """
    try:
        return call()
    except ConsentExpiredError as exc:
        raise ConsentExpired(str(exc)) from exc
    except RateLimitedError as exc:
        raise RateLimited(str(exc)) from exc
    except requests.RequestException as exc:
        raise BankUnavailable(str(exc)) from exc


class EnableBankingProvider:
    """`BankProvider` over an Enable Banking client.

    `own_names` are the holder's names, which the normalizer uses to tell a
    transfer between one's own accounts from a payment to someone else.
    """

    def __init__(self, client: EnableBankingClient, own_names: frozenset[str] = frozenset()) -> None:
        self.client = client
        self.own_names = own_names

    def connected_accounts(self, account: ConfiguredAccount) -> list[BankAccount]:
        listed = translated(lambda: self.client.list_accounts(account.session_id))
        return [bank_account(raw) for raw in listed]

    def account_details(self, account: ConfiguredAccount) -> BankAccount:
        return bank_account(translated(lambda: self.client.fetch_account_details(account.account_uid)))

    def transactions(
        self,
        account: ConfiguredAccount,
        date_from: dt.date,
        date_to: dt.date,
        *,
        account_id: int,
        balancing_account_id: int,
    ) -> list[IncomingTransaction]:
        raw = translated(
            lambda: self.client.fetch_transactions(
                account.account_uid, date_from, date_to, account.max_window_days
            )
        )
        return self._normalized(account, raw, account_id, balancing_account_id)

    def transaction_windows(
        self,
        account: ConfiguredAccount,
        date_from: dt.date,
        date_to: dt.date,
        *,
        account_id: int,
        balancing_account_id: int,
    ) -> list[FetchedWindow]:
        windows = translated(
            lambda: self.client.fetch_transaction_windows(
                account.account_uid, date_from, date_to, account.max_window_days
            )
        )
        return [
            FetchedWindow(
                window.date_from,
                window.date_to,
                self._normalized(account, window.transactions, account_id, balancing_account_id),
                window.error,
            )
            for window in windows
        ]

    def balances(self, account: ConfiguredAccount) -> list[DeclaredBalance]:
        return declared_balances(translated(lambda: self.client.fetch_balances(account.account_uid)))

    def _normalized(
        self,
        account: ConfiguredAccount,
        transactions: list[dict],
        account_id: int,
        balancing_account_id: int,
    ) -> list[IncomingTransaction]:
        return [
            normalize_transaction(
                raw,
                account_id=account_id,
                balancing_account_id=balancing_account_id,
                own_names=self.own_names,
                bank_name=account.institution,
                source="psd2",
            )
            for raw in transactions
        ]
