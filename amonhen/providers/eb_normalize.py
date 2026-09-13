"""Pure translation of raw Enable Banking payloads into ledger types.

No I/O: the HTTP client hands over decoded JSON and this module decides what it
means. Given the same payload it always produces the same description and
counterparty, so the fallback dedup hash is stable across syncs.
"""
import datetime as dt
import decimal
import re
from typing import Any

from amonhen.models import Account, IncomingTransaction, SourceKind

# Fineco encodes an incoming SEPA transfer as
# "Ord: <sender> Ben: <beneficiary> Dt-ord: ...".
_FINECO_ORDER = re.compile(r"Ord:\s*(.+?)\s+Ben:", re.IGNORECASE)


def normalize_transaction(
    raw: dict[str, Any],
    *,
    account_id: int,
    balancing_account_id: int,
    own_names: frozenset[str] = frozenset(),
    bank_name: str = "",
    source: SourceKind = "psd2",
    source_file: str | None = None,
) -> IncomingTransaction:
    """Translate one raw Enable Banking transaction into an `IncomingTransaction`."""
    counterparty = _counterparty(raw, own_names, bank_name)
    return IncomingTransaction(
        account_id=account_id,
        date=_date(raw),
        amount=_amount(raw),
        description=_description(raw, counterparty),
        status=raw.get("status") or "BOOK",
        source=source,
        balancing_account_id=balancing_account_id,
        external_id=raw.get("entry_reference") or raw.get("transaction_id") or None,
        counterparty=counterparty,
        counterparty_account=_counterparty_account(raw),
        currency=_currency(raw),
        raw=raw,
        source_file=source_file,
    )


def normalize_account(
    raw: dict[str, Any], *, institution: str, name: str, currency: str = "EUR"
) -> Account:
    """Translate one raw Enable Banking session account into an `Account`."""
    return Account(
        name=name,
        type="real",
        institution=institution,
        iban=iban_of(raw.get("account_id")),
        external_uid=_text(raw.get("uid")) or None,
        currency=_text(raw.get("currency")) or currency,
    )


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _party_name(value: Any) -> str:
    return _text(value.get("name")) if isinstance(value, dict) else ""


def iban_of(value: Any) -> str | None:
    """The IBAN inside an Enable Banking account reference, when it has one.

    The payload names an account either as a plain IBAN or as an object with an
    ``iban`` key, and both shapes turn up on the same statement.
    """
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return _text(value.get("iban")) or None
    return None


def _indicator(raw: dict[str, Any]) -> str:
    return _text(raw.get("credit_debit_indicator")).upper()


def _amount(raw: dict[str, Any]) -> decimal.Decimal:
    amount = raw.get("transaction_amount")
    value = amount.get("amount") if isinstance(amount, dict) else None
    parsed = decimal.Decimal(str(value)) if value not in (None, "") else decimal.Decimal("0")
    # EB reports an unsigned magnitude plus a direction indicator.
    return -abs(parsed) if _indicator(raw) == "DBIT" else abs(parsed)


def _currency(raw: dict[str, Any]) -> str:
    amount = raw.get("transaction_amount")
    if isinstance(amount, dict):
        return _text(amount.get("currency")) or "EUR"
    return "EUR"


def _date(raw: dict[str, Any]) -> dt.date:
    value = raw.get("booking_date") or raw.get("value_date") or raw.get("transaction_date")
    if not isinstance(value, str) or not value:
        raise ValueError("Enable Banking transaction has no date")
    return dt.date.fromisoformat(value[:10])


def _remittance(raw: dict[str, Any]) -> str:
    """Raw remittance text, taken from the least-rendered field available."""
    structured = raw.get("remittance_information")
    if isinstance(structured, list):
        joined = " | ".join(
            part.strip() for part in structured if isinstance(part, str) and part.strip()
        )
        if joined:
            return joined
    elif isinstance(structured, str) and structured.strip():
        return structured.strip()
    return _text(raw.get("remittance_information_unstructured"))


def _bank_code(raw: dict[str, Any]) -> str:
    code = raw.get("bank_transaction_code")
    if isinstance(code, dict):
        return _text(code.get("description")) or _text(code.get("code"))
    return ""


def _description(raw: dict[str, Any], counterparty: str) -> str:
    """First non-empty source text, never the rendered counterparty label."""
    return (
        _remittance(raw)
        or _text(raw.get("note"))
        or _bank_code(raw)
        or counterparty
        or "Unknown"
    )


# ---------------------------------------------------------------------------
# Counterparty
# ---------------------------------------------------------------------------

def _is_fineco(bank_name: str) -> bool:
    return bank_name.strip().casefold().startswith("fineco")


def _fineco_counterparty(remittance: str, indicator: str) -> str | None:
    """Unwrap Fineco remittance conventions to the actual counterparty name."""
    if "Carta N." in remittance:
        return remittance.split("Carta N.")[0].strip() or None
    if "Addebito SDD" in remittance:
        return remittance.split("Addebito SDD")[0].strip() or None
    if indicator == "CRDT":
        match = _FINECO_ORDER.search(remittance)
        if match:
            return match.group(1).strip() or None
    return None


def _counterparty(raw: dict[str, Any], own_names: frozenset[str], bank_name: str) -> str:
    remittance = _remittance(raw)
    indicator = _indicator(raw)
    if _is_fineco(bank_name):
        specific = _fineco_counterparty(remittance, indicator)
        if specific:
            return specific

    # Money leaving is paid to the creditor; money arriving comes from the debtor.
    if indicator == "DBIT":
        name = _party_name(raw.get("creditor"))
    else:
        name = _party_name(raw.get("debtor"))
    # A transfer to/from one of the holder's own accounts has no useful payee,
    # so relabel it with the remittance text instead of the holder's own name.
    if not name or name.lower() in own_names:
        name = remittance
    return name or "Unknown"


def _counterparty_account(raw: dict[str, Any]) -> str | None:
    if _indicator(raw) == "DBIT":
        return iban_of(raw.get("creditor_account"))
    return iban_of(raw.get("debtor_account"))
