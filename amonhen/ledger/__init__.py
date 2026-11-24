"""The ledger: the single write path for accounts, transactions and postings.

Every transaction has postings that sum to zero. A spend is a posting on a real
account balanced by one on a category account; an internal transfer leg is
balanced by the transfer clearing account, which is why transfers never show up
as spending without needing a rule.

The class is split by sub-domain, one module each (`accounts`, `ingest`,
`deletions`, `categorization`, `transfer_legs`, `balances`, `planning`, `portfolio`, `tracking`); `Ledger` composes
them, so every caller keeps one object and one import. The module-level
definitions are in `definitions` and are re-exported here."""
from __future__ import annotations

import sqlite3

from amonhen.ledger.accounts import AccountsMixin
from amonhen.ledger.balances import BalancesMixin
from amonhen.ledger.categorization import CategorizationMixin
from amonhen.ledger.definitions import (  # noqa: F401 — re-exported
    BALANCE_KINDS,
    BALANCE_TYPES,
    BALANCE_TYPE_ORDER,
    BANK_BALANCE_TYPES,
    BalanceCheck,
    CONTRIBUTION_SQL,
    COUNTED_SOURCES_SQL,
    CREDITS_WHERE,
    DECIDABLE_BY_ONE_CATEGORY,
    DeletedTotal,
    Deletion,
    ESSENTIAL_SQL,
    FORECAST_SOURCES_SQL,
    INVESTMENTS_ACCOUNT,
    PENDING_WINDOW_DAYS,
    RARE_SQL,
    SPENDING_SQL,
    TRANSFER_CLEARING,
    UNCATEGORIZED_WHERE,
    UNRECOGNIZED_SOURCES_SQL,
    VALUATION_PREFIX,
    _COUNTED_BANK_SOURCES,
    _COUNTED_BANK_SOURCES_SQL,
    _FLAGGED_SQL,
    _Plan,
    _TRANSACTION_COLUMNS,
    _WAITING_SQL,
    _balance_type,
    _declaration_order,
    _movement_from_json,
    _movement_json,
    _numbered,
    _source_priority,
    account_setting_keys,
    balance_kind,
    bank_balance_source,
    last_read_key,
    limited_key,
    log,
)
from amonhen.ledger.deletions import DeletionsMixin
from amonhen.ledger.ingest import IngestMixin
from amonhen.ledger.planning import PlanningMixin
from amonhen.ledger.portfolio import PortfolioMixin
from amonhen.ledger.tracking import TrackingMixin
from amonhen.ledger.transfer_legs import TransferLegsMixin


class Ledger(
    AccountsMixin,
    IngestMixin,
    DeletionsMixin,
    CategorizationMixin,
    TransferLegsMixin,
    BalancesMixin,
    PlanningMixin,
    PortfolioMixin,
    TrackingMixin,
):
    """The one object every caller holds: each part keeps its sub-domain, and they
    share the connection and call each other through `self`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
