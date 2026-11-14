"""A bank in memory that implements `BankProvider` directly.

Unlike `test_sync_service.FakeClient`, which imitates Enable Banking's HTTP client
and its JSON, this speaks the port's own types: a test written against it says
what the sync does with movements, balances and failures, and nothing about any
provider. It lives in the tests on purpose: production code does not ship its
test doubles.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from amonhen.config import ConfiguredAccount
from amonhen.models import IncomingTransaction
from amonhen.ports.bank import (
    BankAccount,
    BankError,
    ConsentExpired,
    DeclaredBalance,
    FetchedWindow,
)


@dataclass(frozen=True)
class Movement:
    """A movement as a test writes it: the day, the signed amount, the words."""

    date: dt.date
    amount: str
    description: str
    external_id: str | None = None
    status: str = "BOOK"


@dataclass
class MemoryBank:
    """Movements, balances and failures per account uid, and a log of what was asked."""

    movements: dict[str, list[Movement]] = field(default_factory=dict)
    balances_by_uid: dict[str, list[DeclaredBalance]] = field(default_factory=dict)
    accounts: dict[str, BankAccount] = field(default_factory=dict)
    # A failure raised by every call about that account.
    failures: dict[str, BankError] = field(default_factory=dict)
    # Windows refused by their first day, as the period sync would see them.
    refused_windows: dict[dt.date, str] = field(default_factory=dict)
    window_days: int = 30
    calls: list[tuple[str, str]] = field(default_factory=list)

    def connected_accounts(self, account: ConfiguredAccount) -> list[BankAccount]:
        self._ask("connected_accounts", account)
        return list(self.accounts.values())

    def account_details(self, account: ConfiguredAccount) -> BankAccount:
        self._ask("account_details", account)
        return self.accounts.get(account.account_uid, BankAccount())

    def transactions(self, account, date_from, date_to, *, account_id, balancing_account_id):
        self._ask("transactions", account)
        return [
            self._incoming(movement, account_id, balancing_account_id)
            for movement in self.movements.get(account.account_uid, [])
            if date_from <= movement.date <= date_to
        ]

    def transaction_windows(self, account, date_from, date_to, *, account_id, balancing_account_id):
        self._ask("transaction_windows", account)
        windows = []
        start = date_from
        while start <= date_to:
            end = min(start + dt.timedelta(days=self.window_days - 1), date_to)
            if start in self.refused_windows:
                windows.append(FetchedWindow(start, end, error=self.refused_windows[start]))
            else:
                windows.append(
                    FetchedWindow(
                        start,
                        end,
                        self.transactions(
                            account, start, end,
                            account_id=account_id, balancing_account_id=balancing_account_id,
                        ),
                    )
                )
            start = end + dt.timedelta(days=1)
        return windows

    def balances(self, account: ConfiguredAccount) -> list[DeclaredBalance]:
        self._ask("balances", account)
        return list(self.balances_by_uid.get(account.account_uid, []))

    def _ask(self, operation: str, account: ConfiguredAccount) -> None:
        self.calls.append((operation, account.account_uid))
        failure = self.failures.get(account.account_uid)
        # A dead consent fails the windows too; the other failures are the
        # windows' own, and `refused_windows` is how a test asks for those.
        if failure is not None and (
            operation != "transaction_windows" or isinstance(failure, ConsentExpired)
        ):
            raise failure

    @staticmethod
    def _incoming(movement: Movement, account_id: int, balancing_account_id: int) -> IncomingTransaction:
        return IncomingTransaction(
            account_id=account_id,
            date=movement.date,
            amount=Decimal(movement.amount),
            description=movement.description,
            status=movement.status,
            source="psd2",
            balancing_account_id=balancing_account_id,
            external_id=movement.external_id,
            raw={"memory": movement.description},
        )
