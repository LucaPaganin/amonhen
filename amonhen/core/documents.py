"""Desiderata 5.16-bis, pure: when a movement may pay a document.

A document states its own date; the money may move before it (a receipt issued
after the payment, a year of sessions paid in advance) or after (a bill, its
direct debit some days later). The rule says how far to look on each side, in
days, and this module turns those two numbers into the sentence a person reads
and into the test the ledger runs.
"""
from __future__ import annotations

import datetime as dt


def window_text(before_days: int, after_days: int) -> str:
    """The window as someone would say it, not as two signed numbers."""
    if before_days <= 0 and after_days <= 0:
        return "lo stesso giorno del documento"
    if before_days <= 0:
        return f"entro {after_days} giorni dal documento"
    if after_days <= 0:
        return f"fino a {before_days} giorni prima del documento"
    return f"da {before_days} giorni prima a {after_days} giorni dopo il documento"


def in_window(document: dt.date, movement: dt.date, before_days: int, after_days: int) -> bool:
    """Is the movement inside the rule's window, counted from the document?"""
    days = (movement - document).days
    return -max(before_days, 0) <= days <= max(after_days, 0)
