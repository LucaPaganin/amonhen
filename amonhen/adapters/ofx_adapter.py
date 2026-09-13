"""Parse OFX/QFX bank exports into IncomingTransaction rows.

OFX 1.x is SGML with unclosed leaf tags; OFX 2.x is XML. A tag regex over each
<STMTTRN> block reads both, and only transaction blocks are visited, so
LEDGERBAL never becomes a transaction.
"""
import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from amonhen.models import IncomingTransaction

_TRANSACTION = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.IGNORECASE | re.DOTALL)
_TAGS = ("TRNTYPE", "DTPOSTED", "TRNAMT", "FITID", "NAME", "MEMO")


def parse_ofx(
    path: str | Path,
    *,
    account_id: int,
    balancing_account_id: int,
    source_file: str | None = None,
) -> list[IncomingTransaction]:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = _TRANSACTION.findall(text)
    if not blocks:
        raise ValueError(f"{path}: no <STMTTRN> entries found")

    transactions = []
    for index, block in enumerate(blocks, start=1):
        tags = {name: _tag(block, name) for name in _TAGS}
        transactions.append(
            IncomingTransaction(
                account_id=account_id,
                date=_parse_date(tags["DTPOSTED"], path, index),
                amount=_parse_amount(tags["TRNAMT"], path, index),
                description=" | ".join(part for part in (tags["NAME"], tags["MEMO"]) if part),
                status="BOOK",
                source="import",
                balancing_account_id=balancing_account_id,
                external_id=tags["FITID"] or None,
                source_file=source_file,
                raw=tags,
            )
        )
    return transactions


def _tag(block: str, name: str) -> str:
    match = re.search(rf"<{name}>\s*([^<]*)", block, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_date(raw: str, path: Path, index: int) -> dt.date:
    try:
        return dt.datetime.strptime(raw[:8], "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(f"{path}: transaction {index}: unparseable DTPOSTED {raw!r}") from exc


def _parse_amount(raw: str, path: Path, index: int) -> Decimal:
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{path}: transaction {index}: unparseable TRNAMT {raw!r}") from exc
