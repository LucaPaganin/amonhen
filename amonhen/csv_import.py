"""Turn a column mapping chosen in the browser into a CsvProfile and a preview.

The import screen sends the whole statement as text, plus the columns a person
picked on it. This is the half of that job with no HTTP and no ledger in it: the
mapping becomes a CsvProfile, an incomplete mapping becomes a sentence to show,
and a statement on disk becomes the rows the preview panel lists before anything
is written.
"""
import csv
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from amonhen.adapters.csv_adapter import CsvProfile, RowError, read_csv
from amonhen.models import IncomingTransaction, format_decimal


def profile_from_mapping(mapping: dict) -> CsvProfile:
    """The declarative profile the mapping describes.

    An empty column is an unmapped column. The caller refuses a mapping with no
    description column before this runs, so a blank entry here is a name to drop.
    """
    return CsvProfile(
        delimiter=mapping["delimiter"],
        skip_rows=mapping["skip_rows"],
        date_column=mapping["date_column"],
        date_format=mapping["date_format"],
        amount_column=mapping["amount_column"] or None,
        debit_column=mapping["debit_column"] or None,
        credit_column=mapping["credit_column"] or None,
        decimal_separator=mapping["decimal_separator"],
        description_columns=tuple(name for name in mapping["description_columns"] if name.strip()),
        external_id_column=mapping["external_id_column"] or None,
        invert_sign=mapping["invert_sign"],
    )


def missing_from_mapping(mapping: dict) -> str | None:
    """What the mapping still lacks, as a sentence the import screen prints."""
    if not mapping["date_column"]:
        return "choose the date column"
    if not any(name.strip() for name in mapping["description_columns"]):
        return "choose the description column"
    if not mapping["amount_column"] and not (mapping["debit_column"] and mapping["credit_column"]):
        return "choose the amount column, or both the debit and the credit column"
    return None


@contextmanager
def csv_file(content: str) -> Iterator[Path]:
    """The pasted statement as a file `read_csv` can open.

    The file is closed before it is yielded: Windows refuses to reopen a named
    temporary file that is still open for writing, and `delete=False` with the
    unlink in the `finally` is what keeps the temporary from outliving the call.
    """
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", encoding="utf-8", newline="", delete=False
    )
    try:
        handle.write(content)
        handle.close()
        yield Path(handle.name)
    finally:
        handle.close()
        os.unlink(handle.name)


def read_mapped(
    path: Path,
    *,
    profile: CsvProfile,
    account_id: int,
    balancing_account_id: int,
    source_file: str | None = None,
) -> tuple[list[IncomingTransaction], list[RowError]]:
    """`read_csv` with the temporary path kept out of what it refuses.

    A statement missing a mapped column is the caller's mistake to read about,
    and the file it was read from is named after a temporary nobody chose: the
    sentence that follows that name is the whole answer.
    """
    try:
        return read_csv(
            path,
            account_id=account_id,
            balancing_account_id=balancing_account_id,
            profile=profile,
            source_file=source_file,
        )
    except ValueError as exc:
        raise ValueError(str(exc).removeprefix(f"{path}: ")) from exc


def preview_csv(
    path: Path,
    *,
    mapping: dict,
    account_id: int,
    balancing_account_id: int,
    limit: int = 10,
) -> dict:
    """The rows the import screen shows before anything is written.

    The header is read here rather than by `read_csv`, because the screen offers
    those names in order to choose one — that is the state in which the mapping
    is still incomplete, and the state in which a preview is all there is.
    """
    profile = profile_from_mapping(mapping)
    columns, lines = _scan(path, profile)
    if missing_from_mapping(mapping) is not None:
        return {"columns": columns, "rows": [], "parsed": 0, "rejected": []}
    transactions, errors = read_mapped(
        path,
        profile=profile,
        account_id=account_id,
        balancing_account_id=balancing_account_id,
    )
    # A rejected row has its line in `lines` too: what pairs with a parsed row is
    # the lines left once the rejected ones are taken out.
    rejected_lines = {error.line for error in errors}
    kept_lines = [line for line in lines if line not in rejected_lines]
    rows = [
        {
            "line": line,
            "date": txn.date.isoformat(),
            "amount": format_decimal(txn.amount),
            "description": txn.description,
        }
        for line, txn in zip(kept_lines[:limit], transactions[:limit])
    ]
    return {
        "columns": columns,
        "rows": rows,
        "parsed": len(transactions),
        "rejected": [{"line": error.line, "reason": error.reason} for error in errors[:5]],
    }


def _scan(path: Path, profile: CsvProfile) -> tuple[list[str], list[int]]:
    """The header, and the line each data row of the file ends on.

    The lines follow the convention `RowError.line` uses, so a row in the
    preview and a rejected row are counted the same way.
    """
    with path.open("r", encoding=profile.encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=profile.delimiter)
        for _ in range(profile.skip_rows):
            next(reader, None)
        header = next(reader, None)
        columns = [name.strip() for name in header] if header else []
        lines = [reader.line_num for row in reader if row]
    return columns, lines
