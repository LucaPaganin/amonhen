"""Idempotency keys for transactions coming from different sources.

`external_id` is the provider's identifier when it exists. The fallback hash is
the only discriminator in the overlap zone between PSD2 sync and file import,
so it normalises what the two paths spell differently: whitespace and case in
the description.
"""
import datetime as dt
import hashlib
import re
from decimal import Decimal

_WHITESPACE = re.compile(r"\s+")


def normalize_description(description: str) -> str:
    return _WHITESPACE.sub(" ", description).strip().casefold()


def content_hash(account_id: int, date: dt.date, amount: Decimal, description: str) -> str:
    payload = "|".join(
        (str(account_id), date.isoformat(), f"{amount:.2f}", normalize_description(description))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
