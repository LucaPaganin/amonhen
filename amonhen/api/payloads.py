"""What the routers share: the payloads they answer with, the parsing of query values,
and the checks that turn a missing row into a 404.

The leading underscore marks these as the package's own, not the API's surface:
routers import them, nothing outside `amonhen.api` should."""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests
from fastapi import HTTPException

from amonhen import queries
from amonhen.adapters.enable_banking.client import (
    EnableBankingClient,
    refusal_code,
    refusal_detail,
)
from amonhen.api.schemas import BudgetItemRequest, RuleRequest
from amonhen.budgets import ItemFields, get_item, month_of, parse_month
from amonhen.config import Passthrough, load_config
from amonhen.ledger import BalanceCheck, Ledger
from amonhen.merchants import Rule, Stake, merchant_name
from amonhen.metrics import LedgerScope, SeriesStatistics
from amonhen.models import format_decimal, parse_decimal
from amonhen.sync import PeriodSyncResult, SyncResult, sync_limit


log = logging.getLogger("amonhen.api")

# A statement pasted into a JSON body. Far larger than any bank exports, and
# small enough that the copy the body already is and the file it becomes stay a
# request's worth of memory.
MAX_CSV_BYTES = 8_000_000

# Where an in-flight authorization waits between /connect and /callback.
PENDING_OAUTH = "pending_oauth"

# What the last authorization wrote, so the setup screen can report it even
# though the browser arrives back on a plain GET.
SETUP_LAST_CONNECT = "setup_last_connect"


def _shape(value: object) -> str:
    """How many entries a list held and of which types, for the log."""
    if not isinstance(value, list):
        return type(value).__name__
    kinds = sorted({type(item).__name__ for item in value})
    return f"{len(value)}x{'/'.join(kinds) or '-'}"


def _suggested_name(client: EnableBankingClient, account_uid: str | None, bank: str | None) -> str:
    """A name for a new connected account: the bank, then what tells its accounts apart.

    A session lists uids and nothing a person would call an account, so one consent
    covering a bank's three currencies and its card wrote four entries all called
    "FinecoBank". The details say whether it is a card and in which currency it
    runs; best-effort, because an account without details still has to be saved
    (`save_account` numbers what is still the same).
    """
    parts = [bank or "Conto"]
    try:
        details = client.fetch_account_details(account_uid) if account_uid else {}
    except Exception:  # naming is a convenience, the entry is what matters
        details = {}
    if str(details.get("cash_account_type") or "").upper() == "CARD":
        parts.append("carta")
    if details.get("currency"):
        parts.append(str(details["currency"]))
    return " ".join(parts)


def _refuse_oversized(content: str) -> None:
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "the file is larger than 8 MB: import it from the command line "
                "(uv run amonhen import <file> --account <name>)"
            ),
        )


def _import_account(ledger: Ledger, name: str) -> sqlite3.Row:
    """The account the rows belong to. A missing one is the caller's to add.

    An import never creates its account, for the same reason the CLI refuses:
    a typo that silently opens a second account is worse than a refusal.
    """
    account = ledger.find_account(name=name)
    if account is None:
        raise HTTPException(
            status_code=422,
            detail=f"no account named {name}: add it in Conti first, or import from the command line",
        )
    return account


def _passthrough(config_path: str | Path) -> tuple[Passthrough, ...]:
    """The configured passthrough labels, or none when the file cannot be read.

    The movements are already written when this runs, so a configuration that
    will not load must not fail an import that is otherwise done.
    """
    try:
        return load_config(config_path).passthrough
    except (OSError, KeyError, ValueError):
        return ()


def _sync_payload(ledger: Ledger, result: SyncResult) -> dict:
    """What a sync did, per account, with the 5.4 verdict the panel shows.

    The accounts are answered in the order the configuration lists them, and one
    that could not be reached carries its reason: a sync that reports what it
    failed to do is worth more than one that reports only its successes.
    """
    accounts = []
    for entry in result.accounts:
        row = ledger.find_account(name=entry.account)
        accounts.append(
            {
                "account": entry.account,
                "fetched": entry.fetched,
                "balances": entry.balances,
                "actions": entry.actions,
                "error": entry.error,
                "rate_limited": entry.rate_limited,
                "last_read": (sync_limit(ledger, row["id"]) or {}).get("last_read") if row else None,
                "balance_mismatch": entry.balance_mismatch,
                # Set on the run that gave a new account its opening.
                "anchored": format_decimal(entry.anchored) if entry.anchored is not None else None,
                "verification": _verification(ledger, row["id"]) if row else None,
            }
        )
    return {
        "accounts": accounts,
        "transfers_linked": result.transfers_linked,
        "rules_applied": result.rules_applied,
        "passthrough_legs": result.passthrough_legs,
        "errors": result.errors,
    }


def _period_payload(ledger: Ledger, account_id: int, result: PeriodSyncResult) -> dict:
    """A period sync as the account's panel shows it.

    `verification` is the account's 5.4 state after the run: a mismatch that
    appears after a past period is the sign of a duplicate the hash missed.
    """
    return {
        "account": result.account,
        "from": result.date_from.isoformat(),
        "to": result.date_to.isoformat(),
        "preview": result.preview,
        "windows": [
            {
                "from": window.date_from.isoformat(),
                "to": window.date_to.isoformat(),
                "fetched": window.fetched,
                "error": window.error,
            }
            for window in result.windows
        ],
        "actions": result.actions,
        "movements": [
            {
                "date": movement.date.isoformat(),
                "amount": movement.amount,
                "description": movement.description,
                "status": movement.status,
                "action": movement.action,
                "twin_description": movement.twin_description,
                "twin_source": movement.twin_source,
            }
            for movement in result.movements
        ],
        "held": result.held,
        "transfers_linked": result.transfers_linked,
        "passthrough_legs": result.passthrough_legs,
        "rules_applied": result.rules_applied,
        "error": result.error,
        "balance_mismatch": result.balance_mismatch,
        "errors": result.errors,
        "verification": _verification(ledger, account_id),
    }


def _held_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "account": row["account_name"],
        "date": row["date"],
        "amount": row["amount"],
        "description": row["description"],
        "twin_id": row["twin_id"],
        "twin_description": row["twin_description"],
        "twin_source": row["twin_source"],
        "twin_source_file": row["twin_source_file"],
    }


def _verification(ledger: Ledger, account_id: int) -> dict:
    """The 5.4 invariant as the app shows it: what was declared, and whether we agree.

    One check per kind, because the bank's available figure includes the pending
    movements and its booked figure does not: a failure then says whether to
    look at the pending rows or at duplicates and gaps. An account nobody ever
    declared a balance for is `unverified`, never `verified`: silence is not
    agreement, and the ledger cannot check itself.
    """
    checks = ledger.declared_checks(account_id)
    if not checks:
        return {"state": "unverified", "date": None, "checks": []}
    return {
        "state": _verification_state(checks),
        "date": max(check.as_of for check in checks).isoformat(),
        "checks": [
            {
                "kind": check.kind,
                "source": check.source,
                "date": check.as_of.isoformat(),
                "declared": format_decimal(check.declared),
                "computed": format_decimal(check.computed),
                "difference": format_decimal(check.difference),
                "ok": check.ok,
                # A difference a person made by deleting a movement is not a
                # defect, and the panel says which one it is.
                "explained": check.explained,
                "suppressed": format_decimal(check.suppressed),
                "suppressed_count": check.suppressed_count,
            }
            for check in checks
        ],
    }


def _forecast(ledger: Ledger, account_id: int, today: dt.date) -> dict | None:
    row = ledger.overdraft_forecast(account_id, today)
    return None if row is None else {"date": row["date"], "balance": row["balance"]}


def _unrecognized_balances(ledger: Ledger, account_id: int) -> list[dict]:
    return [
        {
            "type": row["source"].removeprefix("eb:"),
            "date": row["date"],
            "balance": row["balance"],
        }
        for row in ledger.unrecognized_balances(account_id)
    ]


def _verification_state(checks: list[BalanceCheck]) -> str:
    """Which of the four outcomes the account is in.

    `suppressed` is its own state and not a quiet `verified`: the ledger does
    disagree with the bank by exactly what somebody deleted, and the panel has
    to be able to say that in one phrase.
    """
    if all(check.ok for check in checks):
        return "verified"
    if all(check.ok or check.explained for check in checks):
        return "suppressed"
    return "mismatch"


def _names(raw: str | None) -> tuple[str, ...]:
    """A comma-separated list of names, trimmed, in order and without repeats."""
    found: dict[str, None] = {}
    for part in (raw or "").split(","):
        name = part.strip()
        if name:
            found[name] = None
    return tuple(found)


def _scope(
    accounts: str | None, categories: str | None, tags: str | None = None
) -> LedgerScope:
    return LedgerScope(
        accounts=_names(accounts), categories=_names(categories), tags=_names(tags)
    )


def _day(value: str) -> dt.date:
    """An ISO date a person typed, refused with a message instead of a traceback."""
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{value!r} is not an ISO date") from None


def _amount(value: str | None) -> Decimal | None:
    """An amount a person typed, refused the same way."""
    if value is None or not value.strip():
        return None
    try:
        return parse_decimal(value.strip())
    except InvalidOperation:
        raise HTTPException(status_code=422, detail=f"{value!r} is not an amount") from None


def _size(value: str | None) -> str | None:
    """An amount to compare a movement with, as the ledger stores one, sign left out."""
    if value is None or not value.strip():
        return None
    try:
        return format_decimal(abs(parse_decimal(value.strip())))
    except InvalidOperation:
        raise HTTPException(status_code=422, detail=f"{value!r} is not an amount") from None


def _period(from_date: str | None, to_date: str | None, today: dt.date) -> tuple[dt.date, dt.date]:
    """The period a chart covers: the last twelve months unless asked otherwise.

    The end defaults to today, the start to the first day of the month eleven
    months earlier, which is the year the flows chart has always shown. A period
    that ends before it starts is a caller's mistake, not an empty chart.
    """
    end = _day(to_date) if to_date else today
    if from_date:
        start = _day(from_date)
    else:
        year, month = end.year, end.month - 11
        while month < 1:
            month += 12
            year -= 1
        start = dt.date(year, month, 1)
    if start > end:
        raise HTTPException(status_code=422, detail="`from` is after `to`")
    return start, end


def _applied(scope: LedgerScope, period: tuple[dt.date, dt.date] | None = None) -> dict:
    """What the server actually applied, so the client never has to guess."""
    applied: dict = {
        "accounts": list(scope.accounts),
        "categories": list(scope.categories),
        "tags": list(scope.tags),
    }
    if period is not None:
        applied["from"], applied["to"] = period[0].isoformat(), period[1].isoformat()
    return applied


def _require_real_account(ledger: Ledger, account_id: int) -> sqlite3.Row:
    row = queries.account(ledger, account_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"account {account_id} not found")
    if row["type"] != "real":
        raise HTTPException(status_code=422, detail=f"account {account_id} is not a real account")
    return row


def _deleted_payload(row: sqlite3.Row) -> dict:
    """A deleted movement as the trash list reads it.

    No payload and no provider id: what the list shows is the movement a person
    recognises — when it was, what it was, what it was worth, the note they wrote
    on it and when it went — and the rest stays in the ledger, where the sync
    reads it from.
    """
    return {
        "id": row["id"],
        "account": {"id": row["account_id"], "name": row["account_name"]},
        "date": row["date"],
        "amount": row["amount"],
        "description": row["description"],
        "merchant": merchant_name(row["description"]),
        "status": row["status"],
        "notes": row["notes"],
        "deleted_at": row["deleted_at"],
    }


def _account_payload(ledger: Ledger, account_id: int, today: dt.date) -> dict:
    """One account as every account endpoint answers it."""
    row = ledger.account(account_id)
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "institution": row["institution"],
        "balance": format_decimal(ledger.balance(row["id"], today)),
        "opening_date": row["opening_date"],
        "opening_balance": row["opening_balance"],
        "investment": bool(row["investment"]),
        # Off means a movement deleted here stays deleted; on means the next
        # sync writes it back from the tombstone, note included.
        "reimport_deleted": bool(row["reimport_deleted"]),
        # The net worth reads this account's balance from its postings rather
        # than from what a bank declared.
        "computed_balance": bool(row["computed_balance"]),
        # A connected wallet whose top-ups a transfer rule writes, because the
        # wallet reports only what they paid for.
        "unreported_funding": bool(row["unreported_funding"]),
        # Seen by a sync, so Enable Banking knows it: what the panel's period
        # sync needs. An account added by hand has no uid and nothing to ask.
        "connected": row["external_uid"] is not None,
        "verification": _verification(ledger, row["id"]),
        "forecast": _forecast(ledger, row["id"], today),
        "unrecognized_balances": _unrecognized_balances(ledger, row["id"]),
        "sync_limit": sync_limit(ledger, row["id"]),
    }


def _require_transaction(ledger: Ledger, transaction_id: int) -> sqlite3.Row:
    row = queries.transaction(ledger, transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"transaction {transaction_id} not found")
    return row


def _budget_month(month: str | None, today: dt.date) -> str:
    """The month a budget answer is for; the current one by default."""
    return parse_month(month) if month else month_of(today)


def _rule_target(body: RuleRequest) -> str | None:
    """The target the request names: `category` is how the old form said it."""
    if body.target is not None:
        return body.target
    return body.category if body.action == "category" else None


def _rule_fields(body: RuleRequest) -> dict:
    """The keyword arguments `RuleBook.set_rule` and `checked` take from a request."""

    def amount(value: str | None) -> Decimal | None:
        text = (value or "").strip()
        return None if text == "" else parse_decimal(text)

    return {
        "action": body.action,
        "account_id": body.account_id,
        "amount_min": amount(body.amount_min),
        "amount_max": amount(body.amount_max),
        "rule_id": body.id,
    }


def _rule_payload(ledger: Ledger, rule: Rule, count: int) -> dict:
    """A rule as the app reads it. `category` stays for the category rules."""
    account = None
    if rule.account_id is not None:
        account = ledger.account(rule.account_id)["name"]
    return {
        "id": rule.id,
        "pattern": rule.pattern,
        "action": rule.action,
        "target": rule.target,
        "category": rule.target if rule.action == "category" else None,
        "account_id": rule.account_id,
        "account": account,
        "amount_min": None if rule.amount_min is None else format_decimal(rule.amount_min),
        "amount_max": None if rule.amount_max is None else format_decimal(rule.amount_max),
        "count": count,
    }


def _budget_amount(value: str | None) -> Decimal | None:
    """None clears; anything else must read as an amount (an empty string does not)."""
    return None if value is None else parse_decimal(value)


def _require_category(ledger: Ledger, category_id: int) -> None:
    """404 for an account that does not exist; the budget module refuses the rest."""
    try:
        ledger.account(category_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from None


def _require_budget_item(ledger: Ledger, item_id: int) -> dict:
    try:
        return get_item(ledger, item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from None


def _item_fields(body: BudgetItemRequest) -> ItemFields:
    return ItemFields(
        category_id=body.category_id,
        month=body.month,
        description=body.description,
        amount=parse_decimal(body.amount),
        date=None if not body.date else _day(body.date),
        priority=body.priority,
        note=body.note,
    )


def _upstream_refusal(exc: Exception) -> str:
    """The bank's own reason, whichever way its client reports it."""
    if not isinstance(exc, requests.HTTPError) or exc.response is None:
        return str(exc)
    return f"{exc.response.status_code} {refusal_detail(exc.response)}"


def _auth_refusal(exc: Exception, redirect_url: str) -> str:
    """Why `/auth` was refused, naming the redirect URL when that is the reason.

    Enable Banking compares the redirect URL against the application's
    registered list, which lives in its control panel and not in this file. That
    is the one refusal a person can repair, and only if they are told which
    value was sent — the two have to match character for character.
    """
    words = f"Enable Banking refused the request: {_upstream_refusal(exc)}"
    response = exc.response if isinstance(exc, requests.HTTPError) else None
    if response is None or refusal_code(response) != "REDIRECT_URI_NOT_ALLOWED":
        return words
    return (
        f"{words} — the redirect URL sent was {redirect_url}, from accounts.json "
        "(step 1 of Configurazione); Enable Banking accepts only the URLs registered "
        "for the application, character for character"
    )


def _last_connect(ledger: Ledger) -> dict | None:
    """What the last authorization wrote, for the screen the browser came back to."""
    raw = ledger.setting(SETUP_LAST_CONNECT)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _statistics_payload(statistics: SeriesStatistics) -> dict:
    return {
        "median": _money(statistics.median),
        "mean": _money(statistics.mean),
        "min": _money(statistics.minimum),
        "max": _money(statistics.maximum),
        "active_months": statistics.active_months,
        "series": [_money(value) for value in statistics.series],
    }


def _money(value) -> str | None:
    return format_decimal(value) if value is not None else None


def _category_payload(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "episodic": bool(row["episodic"]),
        "essential": bool(row["essential"]),
        "income": bool(row["income"]),
        "contribution": bool(row["contribution"]),
        "description": row["description"],
    }


def _metrics_payload(metrics, scope: LedgerScope) -> dict:
    return {
        "currency": "EUR",
        "applied": _applied(scope),
        "period": {
            "start": metrics.period_start.isoformat(),
            "end": metrics.period_end.isoformat(),
        },
        "months_of_history": metrics.months_of_history,
        "partial": metrics.partial,
        "episodic_partial": metrics.episodic_partial,
        "recurring_burn": _money(metrics.recurring_burn),
        "episodic_accrual": _money(metrics.episodic_accrual),
        "expected_burn": _money(metrics.expected_burn),
        "liquidity": _money(metrics.liquidity),
        "runway_months": f"{metrics.runway_months:.1f}" if metrics.runway_months is not None else None,
        "essential_monthly": _money(metrics.essential_monthly),
        "discretionary_monthly": _money(metrics.discretionary_monthly),
        "contributions_monthly": _money(metrics.contributions_monthly),
    }


def _review_transaction(row: sqlite3.Row, ledger: Ledger, pending: dict[str, str]) -> dict:
    """A queue row plus what the automatic passes already made of it."""
    payload = _transaction(row, ledger)
    proposed = pending.get(payload["merchant"])
    payload["proposed_category"] = proposed
    payload["review_state"] = "proposed" if proposed else "unhandled"
    return payload


def _stake(stake: Stake | None) -> dict:
    """A proposal's stake as the queue reads it. Nothing waiting is a zero."""
    if stake is None:
        return {
            "movements": 0, "total": "0.00", "first_date": None, "last_date": None, "items": [],
        }
    return {
        "movements": stake.movements,
        "total": format_decimal(stake.total),
        "first_date": stake.first_date,
        "last_date": stake.last_date,
        # The movements a yes decides, oldest first: a merchant's name is not
        # enough to recognise a charge, its day and amount are.
        "items": [
            {
                "id": item.id,
                "date": item.date,
                "amount": format_decimal(item.amount),
                "description": item.description,
                "account": item.account,
            }
            for item in stake.items
        ],
    }


def _transaction(row: sqlite3.Row, ledger: Ledger) -> dict:
    account = ledger.account(row["account_id"])
    return {
        "id": row["id"],
        "date": row["date"],
        "amount": row["amount"],
        "description": row["description"],
        "merchant": merchant_name(row["description"]),
        "status": row["status"],
        "account": {"id": account["id"], "name": account["name"]},
        "category": ledger.category_of(row["id"]),
        "splits": [
            {"category": split["name"], "amount": split["amount"]}
            for split in ledger.splits(row["id"])
        ],
        # A transfer leg says where its other half is, or which own account it
        # went to: without it a leg is a row with no category, indistinguishable
        # from one nobody has decided about yet.
        "transfer": ledger.transfer_of(row["id"]),
        "counterparty": row["counterparty"],
        "source": row["source"],
        # Local, and the only field a person may write: the sync never sets it,
        # so what is here was written by hand and stays.
        "notes": row["notes"],
        "tags": ledger.tags_of(row["id"]),
        # The paperwork behind the movement: what Paperless holds for it.
        "documents": [
            {"paperless_id": document["paperless_id"], "title": document["title"],
             "created": document["created"], "kind": document["kind"]}
            for document in ledger.documents_of(row["id"])
        ],
    }
