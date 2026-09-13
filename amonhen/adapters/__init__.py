"""Import adapters: turn manual bank exports into IncomingTransaction rows.

Both the PSD2 path and this import path produce IncomingTransaction, so the
ledger sees one shape regardless of where a transaction came from.
"""
from pathlib import Path

from amonhen.adapters.csv_adapter import ACTUAL, FINECO, REVOLUT, CsvProfile, parse_csv
from amonhen.adapters.ofx_adapter import parse_ofx
from amonhen.models import IncomingTransaction

__all__ = [
    "ACTUAL",
    "FINECO",
    "REVOLUT",
    "CsvProfile",
    "parse_csv",
    "parse_export",
    "parse_ofx",
]


def parse_export(
    path: str | Path,
    *,
    account_id: int,
    balancing_account_id: int,
    profile: CsvProfile | None = None,
    source_file: str | None = None,
) -> list[IncomingTransaction]:
    """Parse a manual export, choosing the parser from the file suffix."""
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        if profile is None:
            raise ValueError(f"{path}: a CsvProfile is required to parse a CSV export")
        return parse_csv(
            path,
            account_id=account_id,
            balancing_account_id=balancing_account_id,
            profile=profile,
            source_file=source_file,
        )
    if suffix in (".ofx", ".qfx"):
        return parse_ofx(
            path,
            account_id=account_id,
            balancing_account_id=balancing_account_id,
            source_file=source_file,
        )
    raise ValueError(f"{path}: unsupported export format {suffix or '<none>'}")
