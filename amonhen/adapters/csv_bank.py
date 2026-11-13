"""A second bank behind the same port: one CSV file per account, read as a feed.

A stub, written to measure what a second provider costs in this structure
(`docs/architettura.md`, the bank port experiment). It reads
`<directory>/<account_uid>.csv` with the columns `date,amount,description,id` and,
when present, `<directory>/<account_uid>.balances.csv` with `date,amount,type`.
The rows are parsed by the CSV import's own parser; what makes them a bank's and
not an import is only the source they are written under, `psd2`, because they
arrive through the sync like any bank's movements.
"""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from amonhen.adapters.csv_adapter import CsvProfile, parse_csv
from amonhen.config import ConfiguredAccount
from amonhen.models import IncomingTransaction
from amonhen.ports.bank import BankAccount, BankUnavailable, DeclaredBalance, FetchedWindow

FEED_PROFILE = CsvProfile(
    date_column="date",
    amount_column="amount",
    description_columns=("description",),
    external_id_column="id",
)


class CsvBankProvider:
    """`BankProvider` over a directory of CSV files, one per account uid."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def connected_accounts(self, account: ConfiguredAccount) -> list[BankAccount]:
        return [BankAccount(uid=account.account_uid)]

    def account_details(self, account: ConfiguredAccount) -> BankAccount:
        return BankAccount(uid=account.account_uid)

    def transactions(
        self,
        account: ConfiguredAccount,
        date_from: dt.date,
        date_to: dt.date,
        *,
        account_id: int,
        balancing_account_id: int,
    ) -> list[IncomingTransaction]:
        path = self.directory / f"{account.account_uid}.csv"
        try:
            rows = parse_csv(
                path,
                account_id=account_id,
                balancing_account_id=balancing_account_id,
                profile=FEED_PROFILE,
            )
        except (OSError, ValueError) as exc:
            raise BankUnavailable(f"cannot read {path.name}: {exc}") from exc
        return [
            replace(row, source="psd2", source_file=None)
            for row in rows
            if date_from <= row.date <= date_to
        ]

    def transaction_windows(
        self,
        account: ConfiguredAccount,
        date_from: dt.date,
        date_to: dt.date,
        *,
        account_id: int,
        balancing_account_id: int,
    ) -> list[FetchedWindow]:
        # A file has no range limit: the whole period is one window.
        try:
            rows = self.transactions(
                account, date_from, date_to,
                account_id=account_id, balancing_account_id=balancing_account_id,
            )
        except BankUnavailable as exc:
            return [FetchedWindow(date_from, date_to, error=str(exc))]
        return [FetchedWindow(date_from, date_to, rows)]

    def balances(self, account: ConfiguredAccount) -> list[DeclaredBalance]:
        path = self.directory / f"{account.account_uid}.balances.csv"
        if not path.exists():
            return []
        with path.open(encoding="utf-8", newline="") as handle:
            return [
                DeclaredBalance(
                    date=dt.date.fromisoformat(row["date"]),
                    amount=Decimal(row["amount"]),
                    balance_type=row.get("type") or None,
                )
                for row in csv.DictReader(handle)
            ]
