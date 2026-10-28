"""PSD2 sync: fetch the configured accounts and write them into the ledger.

`SyncService.run` is the incremental pass over every account; `run_period` is
one account over a range a person chose, past included, window by window.
"""
import datetime as dt
import logging
import threading
from dataclasses import dataclass, field, replace
from decimal import Decimal

import requests

from amonhen.config import ConfiguredAccount, MonitorConfig
from amonhen.ledger import Ledger
from amonhen.merchants import RuleBook, categorize
from amonhen.models import Account, IncomingTransaction, RecordAction, format_decimal, parse_decimal
from amonhen.providers.eb_normalize import iban_of, normalize_account, normalize_transaction
from amonhen.providers.enable_banking import ConsentExpiredError, EnableBankingClient
from amonhen.transfers import link_passthrough_legs, link_transfers

log = logging.getLogger("amonhen.sync")

# Re-fetch a short overlap so late bookings and pending transitions are seen again.
SYNC_OVERLAP_DAYS = 7
DEFAULT_BACKFILL_DAYS = 90

# One sync at a time in this process. The app's button and the scheduled loop of
# `serve` live there together, and two runs writing the same SQLite file is not a
# state worth having. The CLI and the daemon are separate processes, with their
# own copy of this lock, so the guard costs them nothing.
_SYNC_LOCK = threading.Lock()


class SyncBusy(RuntimeError):
    """A sync is already running in this process."""


class PeriodInvalid(ValueError):
    """A period sync that cannot be asked of the bank: the reason is the message."""


@dataclass
class AccountSyncResult:
    account: str
    fetched: int = 0
    balances: int = 0
    actions: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    balance_mismatch: str | None = None
    # The opening this run derived from the bank's first figure, if it did.
    anchored: Decimal | None = None


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


@dataclass
class WindowReport:
    """One window of a period sync: what the bank returned, or why it did not."""

    date_from: dt.date
    date_to: dt.date
    fetched: int = 0
    error: str | None = None


@dataclass
class PeriodMovement:
    """One movement of a period preview, with what writing it would do."""

    date: dt.date
    amount: str
    description: str
    status: str
    action: RecordAction
    # The row a probable duplicate resembles: its description and where it came from.
    twin_description: str | None = None
    twin_source: str | None = None


@dataclass
class PeriodSyncResult:
    account: str
    date_from: dt.date
    date_to: dt.date
    preview: bool
    windows: list[WindowReport] = field(default_factory=list)
    actions: dict[str, int] = field(default_factory=dict)
    movements: list[PeriodMovement] = field(default_factory=list)
    held: int = 0
    transfers_linked: int = 0
    passthrough_legs: int = 0
    rules_applied: int = 0
    error: str | None = None
    balance_mismatch: str | None = None

    @property
    def errors(self) -> list[str]:
        problems = [
            f"{window.date_from}..{window.date_to}: {window.error}"
            for window in self.windows
            if window.error
        ]
        problems += [problem for problem in (self.error, self.balance_mismatch) if problem]
        return [f"{self.account}: {problem}" for problem in problems]


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
        """One full pass, or `SyncBusy` when another one is already running."""
        if not _SYNC_LOCK.acquire(blocking=False):
            raise SyncBusy("a sync is already running in this process")
        try:
            return self._run()
        finally:
            _SYNC_LOCK.release()

    def run_period(
        self, account: str, date_from: dt.date, date_to: dt.date, *, preview: bool = False
    ) -> PeriodSyncResult:
        """One account over a chosen range, or `PeriodInvalid` / `SyncBusy`.

        The period is checked before the lock and before the bank is asked. The
        incremental cursor is untouched: it is the newest movement of the
        account, and a past period adds nothing newer; `start_sync_date` is
        neither read nor written, because a person asking for a range is the
        one thing it does not limit.
        """
        entry = self._period_entry(account, date_from, date_to)
        if not _SYNC_LOCK.acquire(blocking=False):
            raise SyncBusy("a sync is already running in this process")
        try:
            return self._run_period(entry, date_from, date_to, preview)
        finally:
            _SYNC_LOCK.release()

    def _period_entry(
        self, account: str, date_from: dt.date, date_to: dt.date
    ) -> ConfiguredAccount:
        if date_from > date_to:
            raise PeriodInvalid(f"the period starts on {date_from}, after it ends on {date_to}")
        if date_to > self.today:
            raise PeriodInvalid(f"the period ends on {date_to}, after today ({self.today})")
        for entry in self.config.accounts:
            if entry.name == account:
                if not entry.account_uid:
                    raise PeriodInvalid(f"{account} is not connected to Enable Banking")
                return entry
        raise PeriodInvalid(
            f"no account named {account} is connected to Enable Banking: "
            "only a connected account can be synced"
        )

    def _run_period(
        self, entry: ConfiguredAccount, date_from: dt.date, date_to: dt.date, preview: bool
    ) -> PeriodSyncResult:
        result = PeriodSyncResult(entry.name, date_from, date_to, preview)
        account_id = self.ledger.ensure_account(self._account_record(entry))
        try:
            windows = self.client.fetch_transaction_windows(
                entry.account_uid, date_from, date_to, entry.max_window_days
            )
        except ConsentExpiredError as exc:
            result.error = f"consent expired: {exc}"
            log.warning("account %s: %s", entry.name, result.error)
            return result
        for window in windows:
            result.windows.append(
                WindowReport(window.date_from, window.date_to, len(window.transactions), window.error)
            )
        batches = [
            self._normalized(entry, account_id, window.transactions)
            for window in windows
            if window.error is None
        ]
        if preview:
            for batch in batches:
                for txn, action, twin in self.ledger.preview_batch(batch):
                    result.actions[action] = result.actions.get(action, 0) + 1
                    result.movements.append(
                        PeriodMovement(
                            txn.date, format_decimal(txn.amount), txn.description, txn.status,
                            action,
                            twin["description"] if twin is not None else None,
                            twin["source"] if twin is not None else None,
                        )
                    )
            result.held = len(self.ledger.held_transactions(account_id))
            return result
        # One batch per window: a window the bank answered is written whatever
        # happened to the others, and whole-day windows keep the numbering of
        # identical movements the same as the incremental sync gives them.
        for batch in batches:
            for action, count in self.ledger.record_batch(batch, hold_probable=True).items():
                result.actions[action] = result.actions.get(action, 0) + count
        result.held = len(self.ledger.held_transactions(account_id))
        # The same steps as the incremental pass, from the start of the period:
        # a leg older than any `start_sync_date` must still find its pair.
        result.transfers_linked = link_transfers(self.ledger, since=date_from)
        result.passthrough_legs = link_passthrough_legs(self.ledger, self.config.passthrough)
        self.ledger.validate()
        result.rules_applied = categorize(self.ledger, RuleBook(self.ledger.conn))
        result.balance_mismatch = self._declared_balance_mismatch(entry)
        log.info("account %s %s..%s: %s", entry.name, date_from, date_to, result.actions)
        return result

    def _normalized(
        self, entry: ConfiguredAccount, account_id: int, transactions: list[dict]
    ) -> list[IncomingTransaction]:
        balancing = self.ledger.uncategorized()
        return [
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

    def _run(self) -> SyncResult:
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
        explained = [check for check in failed if check.explained]
        for check in explained:
            # Not a mismatch and not silence either: the ledger disagrees with
            # the bank by exactly what somebody deleted here.
            log.info(
                "account %s: the %s figure is short by %s across %d deleted movement(s)",
                entry.name,
                check.kind,
                check.suppressed,
                check.suppressed_count,
            )
        failed = [check for check in failed if not check.explained]
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
            transactions = self.client.fetch_transactions(
                entry.account_uid, date_from, self.today, entry.max_window_days
            )
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
        result.actions = self.ledger.record_batch(
            self._normalized(entry, account_id, transactions)
        )
        result.balances = self._record_balances(entry, account_id)
        result.anchored = self._anchor_first_opening(entry, account_id)
        log.info("account %s: %s, %d balance(s)", entry.name, result.actions, result.balances)
        return result

    def _anchor_first_opening(self, entry: ConfiguredAccount, account_id: int) -> Decimal | None:
        """Desiderata 5.4: a connected account starts from the bank's own figure.

        Only once, while the account has no opening at all: from then on the
        opening is the fixed point the assertion measures from, and re-deriving
        it would fold whatever the ledger is missing into it. The booked figure
        wins over the available one, because a card authorization the bank
        subtracts without exposing it as pending is inside the available figure
        and nowhere in the ledger — anchored there, it is counted again the day
        it settles.
        """
        if self.ledger.account(account_id)["opening_date"] is not None:
            return None
        checks = {
            check.kind: check
            for check in self.ledger.declared_checks(account_id)
            if check.source.startswith("eb:")
        }
        check = checks.get("booked") or checks.get("available")
        if check is None:
            return None
        opening, opening_date = self.ledger.anchor_opening(
            account_id, check.as_of, check.declared, check.kind
        )
        log.info(
            "account %s: opening %s before %s from the bank's %s figure",
            entry.name, format_decimal(opening), opening_date, check.kind,
        )
        return opening

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
