"""PSD2 sync: fetch the configured accounts and write them into the ledger."""
import datetime as dt
import logging
from dataclasses import dataclass, field, replace

import requests

from amonhen.config import ConfiguredAccount, MonitorConfig
from amonhen.ledger import Ledger
from amonhen.merchants import RuleBook, categorize
from amonhen.models import Account, RecordAction, parse_decimal
from amonhen.providers.eb_normalize import iban_of, normalize_account, normalize_transaction
from amonhen.providers.enable_banking import ConsentExpiredError, EnableBankingClient
from amonhen.transfers import link_passthrough_legs, link_transfers

log = logging.getLogger("amonhen.sync")

# Re-fetch a short overlap so late bookings and pending transitions are seen again.
SYNC_OVERLAP_DAYS = 7
DEFAULT_BACKFILL_DAYS = 90


@dataclass
class AccountSyncResult:
    account: str
    fetched: int = 0
    balances: int = 0
    actions: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    balance_mismatch: str | None = None


@dataclass
class SyncResult:
    accounts: list[AccountSyncResult]
    transfers_linked: int
    rules_applied: int = 0
    passthrough_legs: int = 0

    @property
    def errors(self) -> list[str]:
        problems = []
        for account in self.accounts:
            for problem in (account.error, account.balance_mismatch):
                if problem:
                    problems.append(f"{account.account}: {problem}")
        return problems


class SyncService:
    def __init__(
        self,
        ledger: Ledger,
        client: EnableBankingClient,
        config: MonitorConfig,
        today: dt.date | None = None,
    ) -> None:
        self.ledger = ledger
        self.client = client
        self.config = config
        self.today = today or dt.date.today()
        self._sessions: dict[str, dict[str, dict]] = {}
        self._details: dict[str, dict] = {}

    def run(self) -> SyncResult:
        results = [self._sync_account(entry) for entry in self.config.accounts]
        linked = link_transfers(self.ledger, since=self._earliest_start())
        # Declared own accounts come after the pairing, so a real pair between
        # two tracked accounts always wins over a label match.
        legs = link_passthrough_legs(self.ledger, self.config.passthrough)
        self.ledger.validate()
        # The deterministic rules belong to ingest: every sync path, including
        # the one inside the server, must leave categorized rows behind.
        applied = categorize(self.ledger, RuleBook(self.ledger.conn))
        for entry, result in zip(self.config.accounts, results):
            result.balance_mismatch = self._declared_balance_mismatch(entry)
        return SyncResult(results, linked, rules_applied=applied, passthrough_legs=legs)

    def _declared_balance_mismatch(self, entry: ConfiguredAccount) -> str | None:
        """Desiderata 5.4: the ledger must agree with the bank's own balance.

        This is an assertion in the sync process, not a dashboard metric: a
        mismatch means duplicates or gaps, and every number downstream is
        unreliable.
        """
        account = self.ledger.find_account(name=entry.name)
        if account is None:
            return None
        failed = [check for check in self.ledger.declared_checks(account["id"]) if not check.ok]
        if not failed:
            return None
        message = "; ".join(
            f"{check.kind} ({check.source}) disagrees with the declared balance"
            f" on {check.as_of} by {check.difference}"
            for check in failed
        )
        log.error("account %s %s", entry.name, message)
        return message

    def _sync_account(self, entry: ConfiguredAccount) -> AccountSyncResult:
        result = AccountSyncResult(account=entry.name)
        account_id = self.ledger.ensure_account(self._account_record(entry))
        date_from = self._start_date(entry, account_id)
        try:
            transactions = self.client.fetch_transactions(entry.account_uid, date_from, self.today)
        except ConsentExpiredError as exc:
            result.error = f"consent expired: {exc}"
            log.warning("account %s: %s", entry.name, result.error)
            return result
        except requests.RequestException as exc:
            # One unreachable bank must not abort the rest of the run.
            result.error = f"fetch failed: {exc}"
            log.warning("account %s: %s", entry.name, result.error)
            return result

        result.fetched = len(transactions)
        balancing = self.ledger.uncategorized()
        normalized = [
            normalize_transaction(
                raw,
                account_id=account_id,
                balancing_account_id=balancing,
                own_names=self.config.own_names,
                bank_name=entry.institution,
                source="psd2",
            )
            for raw in transactions
        ]
        result.actions = self.ledger.record_batch(normalized)
        result.balances = self._record_balances(entry, account_id)
        log.info("account %s: %s, %d balance(s)", entry.name, result.actions, result.balances)
        return result

    def _record_balances(self, entry: ConfiguredAccount, account_id: int) -> int:
        """Store the balance the bank reports, so net worth has observations.

        Best-effort on purpose: a failing balance call must not discard the
        transactions that just arrived. The recorded balance is also what the
        5.4 assertion below compares the ledger against.
        """
        try:
            payload = self.client.fetch_balances(entry.account_uid)
        except (ConsentExpiredError, requests.RequestException) as exc:
            log.warning("account %s: balance unavailable: %s", entry.name, exc)
            return 0
        recorded = 0
        for balance in payload.get("balances", []):
            amount = balance.get("balance_amount") or {}
            if not amount.get("amount"):
                continue
            reference = (balance.get("reference_date") or self.today.isoformat())[:10]
            self.ledger.record_declared_balance(
                account_id,
                dt.date.fromisoformat(reference),
                parse_decimal(amount["amount"]),
                f"eb:{balance.get('balance_type', 'unknown')}",
            )
            recorded += 1
        return recorded

    def _account_record(self, entry: ConfiguredAccount) -> Account:
        raw = self._session_accounts(entry).get(entry.account_uid)
        if not raw:
            raw = self._account_details(entry)
        record = normalize_account(
            raw, institution=entry.institution, name=entry.name,
            currency=raw.get("currency") or "EUR",
        )
        if record.iban is None:
            # A session names an account but does not identify it: its own IBAN
            # only comes from the details endpoint, and the transfer matcher
            # compares it with the counterparty each bank printed on a leg.
            record = replace(record, iban=iban_of(self._account_details(entry).get("account_id")))
        if record.external_uid is None:
            return replace(record, external_uid=entry.account_uid)
        return record

    def _account_details(self, entry: ConfiguredAccount) -> dict:
        """The account details payload, fetched once per run. Best-effort.

        An unreachable bank must not stop the sync: it only leaves the transfer
        matcher without the evidence to corroborate a pair.
        """
        if entry.account_uid not in self._details:
            try:
                payload = self.client.fetch_account_details(entry.account_uid)
            except Exception as exc:  # session metadata is optional enrichment
                log.warning(
                    "could not read account details for %s: %s", entry.name, type(exc).__name__
                )
                payload = {}
            self._details[entry.account_uid] = payload
        return self._details[entry.account_uid]

    def _session_accounts(self, entry: ConfiguredAccount) -> dict[str, dict]:
        if entry.session_id not in self._sessions:
            try:
                accounts = self.client.list_accounts(entry.session_id)
            except Exception as exc:  # session metadata is optional enrichment
                log.warning("could not read session metadata for %s: %s", entry.name, type(exc).__name__)
                accounts = []
            self._sessions[entry.session_id] = {
                account["uid"]: account for account in accounts if account.get("uid")
            }
        return self._sessions[entry.session_id]

    def _start_date(self, entry: ConfiguredAccount, account_id: int) -> dt.date:
        row = self.ledger.conn.execute(
            "SELECT MAX(date) AS last FROM transactions WHERE account_id = ?", (account_id,)
        ).fetchone()
        if row["last"] is None:
            return entry.start_sync_date or (self.today - dt.timedelta(days=DEFAULT_BACKFILL_DAYS))
        start = dt.date.fromisoformat(row["last"]) - dt.timedelta(days=SYNC_OVERLAP_DAYS)
        return max(start, entry.start_sync_date) if entry.start_sync_date else start

    def _earliest_start(self) -> dt.date | None:
        starts = [entry.start_sync_date for entry in self.config.accounts if entry.start_sync_date]
        return min(starts) if starts else None
