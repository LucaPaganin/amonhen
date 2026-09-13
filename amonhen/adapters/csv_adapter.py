"""Parse bank CSV exports into IncomingTransaction rows.

One CsvProfile describes one bank's export layout. The profiles below are the
known banks; another export is a new constant, not new code. Amounts are always
converted to the account holder's perspective: negative means money left the
account.
"""
import csv
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from amonhen.models import IncomingTransaction


@dataclass(frozen=True)
class CsvProfile:
    delimiter: str = ","
    encoding: str = "utf-8"
    skip_rows: int = 0
    date_column: str = "Date"
    date_format: str = "%Y-%m-%d"
    amount_column: str | None = None
    debit_column: str | None = None
    credit_column: str | None = None
    decimal_separator: str = "."
    description_columns: tuple[str, ...] = ("Description",)
    external_id_column: str | None = None
    invert_sign: bool = False


# Revolut account-statement CSV. Amount is already signed.
REVOLUT = CsvProfile(
    date_column="Completed Date",
    date_format="%Y-%m-%d %H:%M:%S",
    amount_column="Amount",
    description_columns=("Description",),
)

# Fineco movements export: semicolon-separated, Italian dates and decimals,
# money out in Dare and money in in Avere.
FINECO = CsvProfile(
    delimiter=";",
    date_column="Data",
    date_format="%d/%m/%Y",
    debit_column="Dare",
    credit_column="Avere",
    decimal_separator=",",
    description_columns=("Descrizione",),
)

# Actual Budget CSV export. Payee and Notes are the raw text the bank supplied,
# so together they are the description.
ACTUAL = CsvProfile(
    date_column="Date",
    amount_column="Amount",
    description_columns=("Payee", "Notes"),
)


def parse_csv(
    path: str | Path,
    *,
    account_id: int,
    balancing_account_id: int,
    profile: CsvProfile,
    source_file: str | None = None,
) -> list[IncomingTransaction]:
    path = Path(path)
    with path.open("r", encoding=profile.encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=profile.delimiter)
        for _ in range(profile.skip_rows):
            next(reader, None)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"{path}: no header row") from None

        columns = [name.strip() for name in header]
        _require_columns(path, columns, profile)
        return [
            _parse_row(path, reader.line_num, columns, row, profile, account_id, balancing_account_id, source_file)
            for row in reader
            if row
        ]


def _require_columns(path: Path, columns: list[str], profile: CsvProfile) -> None:
    if profile.amount_column is None and (profile.debit_column is None or profile.credit_column is None):
        raise ValueError(f"{path}: profile needs amount_column or both debit_column and credit_column")
    if profile.amount_column is not None:
        required = (profile.date_column, profile.amount_column, *profile.description_columns)
    else:
        required = (
            profile.date_column, profile.debit_column, profile.credit_column, *profile.description_columns,
        )
    missing = [name for name in required if name not in columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")


def _parse_row(
    path: Path,
    line_number: int,
    columns: list[str],
    row: list[str],
    profile: CsvProfile,
    account_id: int,
    balancing_account_id: int,
    source_file: str | None,
) -> IncomingTransaction:
    if len(row) != len(columns):
        raise ValueError(
            f"{path}: line {line_number}: expected {len(columns)} fields, got {len(row)}"
        )
    record = dict(zip(columns, row))
    try:
        date = _parse_date(record, profile)
        amount = _parse_amount(record, profile)
    except ValueError as exc:
        raise ValueError(f"{path}: line {line_number}: {exc}") from exc

    external_id = None
    if profile.external_id_column is not None:
        external_id = _cell(record.get(profile.external_id_column)) or None
    return IncomingTransaction(
        account_id=account_id,
        date=date,
        amount=amount,
        description=_description(record, profile),
        status="BOOK",
        source="import",
        balancing_account_id=balancing_account_id,
        external_id=external_id,
        source_file=source_file,
        raw=record,
    )


def _parse_date(record: dict[str, str], profile: CsvProfile) -> dt.date:
    raw = _cell(record.get(profile.date_column))
    try:
        return dt.datetime.strptime(raw, profile.date_format).date()
    except ValueError as exc:
        raise ValueError(f"unparseable date {raw!r} for format {profile.date_format!r}") from exc


def _parse_amount(record: dict[str, str], profile: CsvProfile) -> Decimal:
    if profile.amount_column is not None:
        amount = _decimal(record.get(profile.amount_column), profile.decimal_separator)
    else:
        # Dare is money out, Avere is money in; empty cells count as zero.
        debit = abs(_decimal(record.get(profile.debit_column), profile.decimal_separator))
        credit = abs(_decimal(record.get(profile.credit_column), profile.decimal_separator))
        amount = credit - debit
    return -amount if profile.invert_sign else amount


def _decimal(value: Any, decimal_separator: str) -> Decimal:
    text = _cell(value)
    if not text:
        return Decimal("0")
    if decimal_separator == ",":
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"unparseable amount {text!r}") from exc


def _description(record: dict[str, str], profile: CsvProfile) -> str:
    parts = [_cell(record.get(column)) for column in profile.description_columns]
    return " | ".join(part for part in parts if part)


def _cell(value: Any) -> str:
    return "" if value is None else str(value).strip()
