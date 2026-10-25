"""HTTP API and the host for the mobile PWA.

The surface is deliberately small: the two screens of phase 2 need a
filterable transaction list, the review queue, category changes and the
confirm/reject decision on a transfer link. No authentication: the app is
served behind Tailscale, and the ledger never leaves the machine.
"""
import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator, Literal

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from amonhen import assistant, db
from amonhen.anomalies import detect_anomalies
from amonhen.budgets import (
    ItemFields,
    add_item,
    budget_status,
    copy_items,
    delete_item,
    get_item,
    month_of,
    parse_month,
    set_default,
    set_month_override,
    update_item,
)
from amonhen.classifier import apply_proposals, propose_categories
from amonhen.config import (
    MonitorConfig,
    Passthrough,
    UnknownConfiguredAccount,
    load_config,
    remove_account,
    rename_account,
    save_account,
    save_credentials,
    setup_state,
)
from amonhen.csv_import import (
    csv_file,
    missing_from_mapping,
    preview_csv,
    profile_from_mapping,
    read_mapped,
)
from amonhen.ledger import UNCATEGORIZED_WHERE, BalanceCheck, Ledger
from amonhen.llm import LlmOff, llm_config
from amonhen.merchants import (
    Rule,
    RuleBook,
    Stake,
    accept_merchant,
    categorize,
    deleting_rule,
    merchant_name,
    preview,
    rule_usage,
    uncovered_spending,
)
from amonhen.metrics import (
    LedgerScope,
    compute_metrics,
    latest_balances,
    monthly_flows,
    net_worth_series,
    spend_by_category,
)
from amonhen.models import Account, format_decimal, parse_decimal
from amonhen.providers.enable_banking import (
    ConsentExpiredError,
    EnableBankingClient,
    refusal_code,
    refusal_detail,
)
from amonhen.settings import CONFIG_FILE, DB_PATH, UNCATEGORIZED
from amonhen.suggestions import propose_for_unseen
from amonhen.sync import PeriodInvalid, PeriodSyncResult, SyncBusy, SyncResult, SyncService
from amonhen.transfers import link_passthrough_legs, link_transfers, pair_candidates

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

# Bump when a response shape changes: the PWA compares this with the version it
# was built for and, when the server is older, says so instead of crashing on a
# key that is not there. The bundle is read from disk on every request while the
# Python process keeps running its old code, so the two can drift. Version 20 is
# the queue's decision: the request carries the text of a rule to write and the
# answer says what the decision did, and an older server would take the text as
# absent — writing a rule named after the merchant, which is the behaviour this
# version removed. 21 is the budget planned by month (desiderata 5.12): a budget
# row carries its default, its month override and its items, and every budget
# write answers with the whole month instead of one row. 22 is the general rule
# (desiderata 5.5): a rule has an id, an action, a target and conditions, and the
# writes around it are new, with the account deletion and the movements' batch
# writes beside them. 23 is the sync of one account over a chosen period:
# `/api/sync/period` and the probable duplicates it holds (`/api/sync/held`),
# and an account row says whether it is `connected`.
API_VERSION = 23

# A statement pasted into a JSON body. Far larger than any bank exports, and
# small enough that the copy the body already is and the file it becomes stay a
# request's worth of memory.
MAX_CSV_BYTES = 8_000_000

# Where an in-flight authorization waits between /connect and /callback.
PENDING_OAUTH = "pending_oauth"

# What the last authorization wrote, so the setup screen can report it even
# though the browser arrives back on a plain GET.
SETUP_LAST_CONNECT = "setup_last_connect"


def _client(config) -> EnableBankingClient:
    return EnableBankingClient(
        application_id=config.application_id,
        pem_path=config.pem_path,
        redirect_url=config.redirect_url,
    )


class CategoryRequest(BaseModel):
    category: str


class NotesRequest(BaseModel):
    """The local note of a movement: the only field the app may write on it."""

    notes: str | None = None


class ReviewRequest(BaseModel):
    decision: Literal["confirm", "reject"]


class TransferPassthroughRequest(BaseModel):
    transaction_id: int
    destination: str


class AssistantAskRequest(BaseModel):
    """A question, and optionally the thing the question is about."""

    question: str = ""
    context: dict | None = None


class BudgetProposalDecisionRequest(BaseModel):
    category: str
    decision: str


class TransferPairRequest(BaseModel):
    leg_a: int
    leg_b: int


class TransferUnlinkRequest(BaseModel):
    transaction_id: int


class RuleRequest(BaseModel):
    """A rule to write. `category` is the old form of `target` for a category rule.

    `id` changes that rule; without it, a rule with the same text and conditions
    is the one changed. The amounts are sizes, as text, so "12,50" reads too.
    """

    pattern: str
    action: str = "category"
    target: str | None = None
    category: str | None = None
    account_id: int | None = None
    amount_min: str | None = None
    amount_max: str | None = None
    id: int | None = None


class RuleRemoveRequest(BaseModel):
    """The rule to drop: by id, or by the text of a rule without conditions."""

    pattern: str | None = None
    id: int | None = None


class TransactionIdsRequest(BaseModel):
    ids: list[int]


class BatchCategoryRequest(BaseModel):
    ids: list[int]
    category: str


class CategoryNameRequest(BaseModel):
    name: str


class CategoryFlagsRequest(BaseModel):
    episodic: bool | None = None
    essential: bool | None = None


class AccountFlagsRequest(BaseModel):
    investment: bool | None = None
    reimport_deleted: bool | None = None


class SplitItem(BaseModel):
    category: str
    amount: str


class SplitsRequest(BaseModel):
    splits: list[SplitItem]


class AccountRequest(BaseModel):
    name: str
    institution: str | None = None
    currency: str | None = None
    opening_balance: str | None = None
    opening_date: str | None = None


class DeclarationRequest(BaseModel):
    """A balance read off the bank, and which of its two figures it is."""

    date: str
    balance: str
    kind: Literal["available", "booked"] = "available"


class BudgetRequest(BaseModel):
    amount: str | None = None


class BudgetItemRequest(BaseModel):
    """A planned expense, whole: an edit may move it to another month or category."""

    category_id: int
    month: str
    description: str
    amount: str
    date: str | None = None
    priority: Literal["essential", "important", "deferrable"] = "important"
    note: str | None = None


class BudgetCopyRequest(BaseModel):
    from_month: str
    to_month: str


class SuggestionDecisionRequest(BaseModel):
    merchant: str
    decision: Literal["accept", "dismiss"]
    # The category a person chose instead of the proposed one. Absent (or empty)
    # means the proposal was right; on a dismissal it is not read at all.
    category: str | None = None
    # The text of a rule to write for this merchant, when one was asked for.
    # Absent means the decision is about the movements alone: `rules` is not
    # touched, and the next movements of that merchant come back to the queue.
    rule: str | None = None


class SetupCredentialsRequest(BaseModel):
    """The Enable Banking credentials the first-setup screen collected.

    `private_key` is the pasted PEM, present only when the key is being written.
    Where it goes is not the caller's to choose: it is `pem_path` on the file, or
    `./private.pem` beside it, which is also what the Enable Banking client and
    the container's `/config` mount expect.
    """

    application_id: str
    redirect_url: str
    account_holder_name: str | None = None
    private_key: str | None = None


class SetupConnectRequest(BaseModel):
    bank: str
    country: str = "IT"


class SetupAccountRequest(BaseModel):
    name: str
    start_sync_date: str | None = None


class CsvMapping(BaseModel):
    """The column map the import screen built, one field per choice it offered.

    An empty column means "not chosen": a statement carries either one signed
    amount column or a debit and a credit pair, and the half left blank is what
    the preview reports back as a problem.
    """

    delimiter: str = Field(",", min_length=1, max_length=1)
    skip_rows: int = Field(0, ge=0)
    date_column: str = ""
    date_format: str = "%Y-%m-%d"
    amount_column: str = ""
    debit_column: str = ""
    credit_column: str = ""
    decimal_separator: Literal[".", ","] = "."
    description_columns: list[str] = []
    external_id_column: str = ""
    invert_sign: bool = False


class PeriodSyncRequest(BaseModel):
    """One connected account over a period a person chose, both days included."""

    model_config = ConfigDict(populate_by_name=True)

    account_id: int
    date_from: str = Field(alias="from")
    date_to: str = Field(alias="to")
    preview: bool = False


class CsvImportRequest(BaseModel):
    """A statement pasted as text, the account it belongs to, and its map."""

    filename: str = ""
    content: str
    account: str
    mapping: CsvMapping


def create_app(
    db_path: str | Path = DB_PATH,
    web_dist: Path | None = None,
    config_path: str | Path = CONFIG_FILE,
) -> FastAPI:
    startup = db.connect(db_path)
    db.initialize(startup)
    startup.close()
    app = FastAPI(title="finance-monitor", docs_url=None, redoc_url=None)

    @app.exception_handler(ValueError)
    async def invalid_value(_request, exc: ValueError) -> JSONResponse:
        # The ledger validates names and amounts; a bad value is the caller's
        # problem, not a server error. ArithmeticError covers a malformed
        # decimal string from parse_decimal.
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ArithmeticError)
    async def invalid_number(_request, exc: ArithmeticError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": f"invalid number: {exc}"})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, exc: RequestValidationError) -> JSONResponse:
        """A malformed request, described without repeating what it carried.

        Pydantic's own answer echoes the whole body under `input`, and one of
        these bodies is a pasted private key: describing the offending field is
        what the client shows anyway, and it is all it needs.
        """
        problems = [
            f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422, content={"detail": "invalid request: " + "; ".join(problems)}
        )

    @contextmanager
    def ledger_scope() -> Iterator[Ledger]:
        """One connection per request, opened and closed on the same thread.

        A `yield` dependency would not do: FastAPI runs the setup and the
        teardown in the thread pool, and sqlite3 refuses a connection used from
        a different thread than the one that created it.
        """
        conn = db.connect(db_path)
        try:
            yield Ledger(conn)
        finally:
            conn.close()

    # -- consent flow (desiderata 7: the routes live in the application) ----

    def credentials_or_409() -> MonitorConfig:
        """The configuration a bank call needs, or the reason it cannot be made.

        What a bank call needs is the application ID and a private key that
        loads — not an account list, because the first setup authorizes its
        first bank before any account is configured. Without this a fresh
        install answers 500 for a state the screen is about to collect.
        """
        state = setup_state(config_path)
        missing = [name for name in state["missing"] if name != "accounts"]
        if missing:
            raise HTTPException(
                status_code=409,
                detail=(
                    "no Enable Banking credentials yet: finish the first setup "
                    f"({', '.join(missing)} missing)"
                ),
            )
        try:
            return load_config(config_path)
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=409, detail=f"the configuration is not usable yet: {exc}"
            ) from exc

    def start_authorization(bank: str, country: str, psu_type: str) -> str:
        """Ask Enable Banking for an authorization URL and remember the state.

        The two callers differ only in what the browser does with the answer:
        `/connect` redirects to it, and the setup screen navigates to it in the
        same tab, because the return has to land inside the app.
        """
        config = credentials_or_409()
        client = _client(config)
        try:
            state, valid_until, url = client.start_auth(bank, country, psu_type)
        except requests.HTTPError as exc:
            # The bank rejects an ASPSP name it does not know: say so, rather
            # than turning it into a server error.
            raise HTTPException(
                status_code=502,
                detail=_auth_refusal(exc, config.redirect_url),
            ) from exc
        with ledger_scope() as ledger:
            ledger.set_setting(
                PENDING_OAUTH,
                json.dumps(
                    {
                        "state": state,
                        "bank": bank,
                        "country": country,
                        "valid_until": valid_until,
                        "created_at": dt.datetime.now(dt.UTC).isoformat(),
                    }
                ),
            )
        return url

    @app.get("/connect")
    def connect(bank: str, country: str, psu_type: str = "personal") -> RedirectResponse:
        return RedirectResponse(start_authorization(bank, country, psu_type), status_code=302)

    @app.get("/callback")
    def callback(code: str, state: str) -> RedirectResponse:
        with ledger_scope() as ledger:
            pending = ledger.setting(PENDING_OAUTH)
            if not pending:
                raise HTTPException(status_code=400, detail="no authorization was started")
            request = json.loads(pending)
            if request.get("state") != state:
                raise HTTPException(status_code=400, detail="the authorization state does not match")
            config = credentials_or_409()
            try:
                session = _client(config).complete_auth(code, state)
            except requests.HTTPError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Enable Banking refused the session: {_upstream_refusal(exc)}",
                ) from exc
            session_id = session.get("session_id")
            raw_accounts = session.get("accounts_data") or session.get("accounts") or []
            connected = [account for account in raw_accounts if isinstance(account, dict)]
            written = []
            for account in connected:
                entry = {
                    "session_id": session_id,
                    "account_uid": account.get("uid"),
                    "bank_name": request.get("bank"),
                    "country": request.get("country"),
                    "notes": account.get("name") or request.get("bank"),
                    "start_sync_date": dt.date.today().isoformat(),
                    # Enable Banking reports when this consent stops working, and
                    # the file is where a person looks before re-authorizing.
                    "session_expiry": request.get("valid_until"),
                }
                action, name = save_account(config_path, entry)
                written.append({"account": name, "action": action})
            ledger.set_setting(PENDING_OAUTH, "")
            # Which entries were refreshed and which were added: a bank that
            # returns several accounts writes several, and the setup screen
            # keeps the ones wanted before the sync imports them all. It is read
            # back from `/api/setup`, because what the browser gets here is a
            # redirect into the app rather than a JSON document nobody sees.
            ledger.set_setting(
                SETUP_LAST_CONNECT,
                json.dumps(
                    {
                        "when": dt.datetime.now(dt.UTC).isoformat(),
                        "written": written,
                    }
                ),
            )
        return RedirectResponse("/?setup=1", status_code=303)

    # -- first setup (desiderata 5.10) --------------------------------------

    def setup_payload() -> dict:
        with ledger_scope() as ledger:
            payload = setup_state(config_path)
            payload["last_connect"] = _last_connect(ledger)
        return payload

    @app.get("/api/setup")
    def setup() -> dict:
        return setup_payload()

    @app.put("/api/setup/credentials")
    def write_credentials(request: SetupCredentialsRequest) -> dict:
        try:
            save_credentials(
                config_path,
                application_id=request.application_id,
                redirect_url=request.redirect_url,
                account_holder_name=request.account_holder_name,
                private_key=request.private_key,
            )
        except OSError as exc:
            # A folder the container's user cannot write in is the first setup's
            # likeliest failure, and it deserves its own words rather than a 500.
            raise HTTPException(
                status_code=503, detail=f"the configuration could not be written: {exc}"
            ) from exc
        return setup_payload()

    @app.get("/api/setup/banks")
    def setup_banks(country: str = "IT") -> dict:
        """The banks Enable Banking knows in one country, by exact name.

        `/connect` takes the ASPSP name character for character, and a screen
        that asks a person to remember it is asking them to get it wrong.
        """
        config = credentials_or_409()
        try:
            banks = _client(config).list_banks()
        except (requests.HTTPError, ConsentExpiredError) as exc:
            # The client reports a refused credential two ways — an HTTPError
            # from a status code, a ConsentExpiredError from 401/403 — and both
            # are the bank's answer, not a server error.
            raise HTTPException(
                status_code=502,
                detail=f"Enable Banking refused the request: {_upstream_refusal(exc)}",
            ) from exc
        wanted = country.strip().upper()
        return {
            "country": wanted,
            "banks": sorted(
                (
                    {"name": bank["name"], "country": bank.get("country") or ""}
                    for bank in banks
                    if (bank.get("country") or "").upper() == wanted
                ),
                key=lambda bank: bank["name"],
            ),
        }

    @app.post("/api/setup/connect")
    def setup_connect(request: SetupConnectRequest) -> dict:
        return {"url": start_authorization(request.bank, request.country, "personal")}

    @app.patch("/api/setup/accounts/{account_uid}")
    def rename_configured_account(account_uid: str, request: SetupAccountRequest) -> dict:
        try:
            rename_account(
                config_path,
                account_uid,
                name=request.name,
                start_sync_date=request.start_sync_date,
            )
        except UnknownConfiguredAccount as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return setup_payload()

    @app.delete("/api/setup/accounts/{account_uid}")
    def remove_configured_account(account_uid: str) -> dict:
        try:
            remove_account(config_path, account_uid)
        except UnknownConfiguredAccount as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return setup_payload()

    # -- reads -------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "api_version": API_VERSION, "uncategorized": UNCATEGORIZED}

    @app.get("/api/accounts")
    def accounts() -> list[dict]:
        with ledger_scope() as ledger:
            return [_account_payload(ledger, row["id"]) for row in _real_accounts(ledger)]

    @app.get("/api/categories")
    def categories() -> list[dict]:
        with ledger_scope() as ledger:
            rows = ledger.conn.execute(
                "SELECT id, name, episodic, essential FROM accounts WHERE type = 'category' ORDER BY name"
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "episodic": bool(row["episodic"]),
                    "essential": bool(row["essential"]),
                }
                for row in rows
            ]

    @app.get("/api/metrics")
    def metrics(accounts: str | None = None, categories: str | None = None) -> dict:
        """The 5.6 metrics for the selected accounts and categories.

        The period is not a parameter: these windows are the definition of the
        metrics, and the cards say which window each one used.
        """
        scope = _scope(accounts, categories)
        with ledger_scope() as ledger:
            return _metrics_payload(compute_metrics(ledger, dt.date.today(), scope=scope), scope)

    @app.get("/api/spending")
    def spending(
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
        accounts: str | None = None,
        categories: str | None = None,
    ) -> dict:
        """What each category took in the period: the slices of the pie."""
        scope = _scope(accounts, categories)
        period = _period(from_date, to_date)
        with ledger_scope() as ledger:
            slices = spend_by_category(ledger, period[0], period[1], scope)
            return {
                "currency": "EUR",
                "period": {"start": period[0].isoformat(), "end": period[1].isoformat()},
                "applied": _applied(scope, period),
                "total": _money(sum((item.amount for item in slices), Decimal(0))),
                "categories": [
                    {"category": item.category, "amount": _money(item.amount)} for item in slices
                ],
            }

    @app.get("/api/flows")
    def flows(
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
        accounts: str | None = None,
        categories: str | None = None,
    ) -> dict:
        """Money in and out per month in the period, empty months included."""
        scope = _scope(accounts, categories)
        period = _period(from_date, to_date)
        with ledger_scope() as ledger:
            return {
                "currency": "EUR",
                "applied": _applied(scope, period),
                "months": [
                    {
                        "month": flow.month,
                        "income": _money(flow.income),
                        "expenses": _money(flow.expenses),
                        "partial": flow.partial,
                    }
                    for flow in monthly_flows(ledger, period[0], period[1], scope)
                ],
            }

    @app.get("/api/networth")
    def networth(
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
        accounts: str | None = None,
    ) -> dict:
        """Observed balances over time, plus each account's latest one.

        The period cuts the points it shows, not the running total: an
        observation before the period still decides what the first point inside
        it is worth. The legend under the chart is a state, not a series, so it
        is always the latest balance each account reported.
        """
        scope = _scope(accounts, None)
        period = _period(from_date, to_date)
        with ledger_scope() as ledger:
            return {
                "currency": "EUR",
                "applied": _applied(scope, period),
                "points": [
                    {"date": point.date.isoformat(), "total": _money(point.total)}
                    for point in net_worth_series(ledger, period[0], period[1], scope)
                ],
                "accounts": [
                    {
                        "account": balance.account,
                        "date": balance.date.isoformat(),
                        "balance": _money(balance.balance),
                    }
                    for balance in latest_balances(ledger, scope)
                ],
            }

    @app.get("/api/budgets")
    def budgets(month: str | None = None) -> list[dict]:
        with ledger_scope() as ledger:
            return budget_status(ledger, _budget_month(month))

    @app.put("/api/budgets/{category_id}")
    def put_budget(category_id: int, body: BudgetRequest, month: str | None = None) -> list[dict]:
        """Set or clear a category's default budget from ``month`` on.

        The months before it keep the budget they had, which is what makes a
        past month readable as it was. The answer is that whole month again.
        """
        month = _budget_month(month)
        with ledger_scope() as ledger:
            _require_category(ledger, category_id)
            set_default(ledger, category_id, month, _budget_amount(body.amount))
            return budget_status(ledger, month)

    @app.put("/api/budgets/{category_id}/override")
    def put_budget_override(
        category_id: int, body: BudgetRequest, month: str | None = None
    ) -> list[dict]:
        """Give one month its own budget for a category; an empty amount hands it back."""
        month = _budget_month(month)
        with ledger_scope() as ledger:
            _require_category(ledger, category_id)
            set_month_override(ledger, category_id, month, _budget_amount(body.amount))
            return budget_status(ledger, month)

    @app.post("/api/budgets/{category_id}/copy")
    def copy_budget_items(category_id: int, body: BudgetCopyRequest) -> dict:
        """Copy a category's planned expenses from one month into another."""
        with ledger_scope() as ledger:
            _require_category(ledger, category_id)
            copied = copy_items(ledger, category_id, body.from_month, body.to_month)
            return {"copied": copied, "budgets": budget_status(ledger, body.to_month)}

    @app.post("/api/budget-items", status_code=201)
    def create_budget_item(body: BudgetItemRequest) -> list[dict]:
        """Plan an expense inside a category's budget; answers with its month."""
        with ledger_scope() as ledger:
            _require_category(ledger, body.category_id)
            add_item(ledger, _item_fields(body))
            return budget_status(ledger, body.month)

    @app.put("/api/budget-items/{item_id}")
    def update_budget_item(item_id: int, body: BudgetItemRequest, month: str | None = None) -> list[dict]:
        """Rewrite a planned expense, answering for ``month`` (by default the one it moved to)."""
        with ledger_scope() as ledger:
            _require_budget_item(ledger, item_id)
            _require_category(ledger, body.category_id)
            update_item(ledger, item_id, _item_fields(body))
            return budget_status(ledger, _budget_month(month or body.month))

    @app.delete("/api/budget-items/{item_id}")
    def delete_budget_item(item_id: int) -> list[dict]:
        """Drop a planned expense, answering with the month it was in."""
        with ledger_scope() as ledger:
            month = _require_budget_item(ledger, item_id)["month"]
            delete_item(ledger, item_id)
            return budget_status(ledger, month)

    @app.post("/api/accounts", status_code=201)
    def create_account(body: AccountRequest) -> dict:
        """Add a real account by hand: the broker, or a bank that is not connected.

        A name already in the ledger is refused instead of reused — `ensure_account`
        would quietly hand back the existing account and the caller would believe
        it had created one.
        """
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="an account needs a name")
        opening = _amount(body.opening_balance)
        opening_date = _day(body.opening_date) if body.opening_date else None
        if opening is not None and opening_date is None:
            raise HTTPException(
                status_code=422, detail="an opening balance needs the date it refers to"
            )
        with ledger_scope() as ledger:
            if ledger.find_account(name=name) is not None:
                raise HTTPException(status_code=422, detail=f"{name!r} already exists")
            account_id = ledger.ensure_account(
                Account(
                    name=name,
                    type="real",
                    institution=body.institution,
                    currency=body.currency or "EUR",
                    opening_balance=opening,
                    opening_date=opening_date,
                )
            )
            return _account_payload(ledger, account_id)

    @app.delete("/api/accounts/{account_id}")
    def delete_account(account_id: int) -> dict:
        """Delete a real account with its movements, and stop syncing it.

        A connected account is also taken out of `accounts.json`, or the next sync
        would create it again and import its history from the bank. Nothing is
        kept to restore: the snapshot is the way back.
        """
        with ledger_scope() as ledger:
            try:
                name = ledger.account(account_id)["name"]
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
            movements = ledger.delete_account(account_id)
        disconnected = False
        try:
            configured = load_config(config_path).accounts
        except (FileNotFoundError, ValueError, KeyError):
            configured = []
        for entry in configured:
            if entry.name == name:
                remove_account(config_path, entry.account_uid)
                disconnected = True
        return {"name": name, "movements": movements, "disconnected": disconnected}

    @app.put("/api/accounts/{account_id}/declaration")
    def declare_balance(account_id: int, body: DeclarationRequest) -> dict:
        """Record a balance a person read off the bank, and answer with the check.

        The source carries which of the bank's two figures it is
        (`manual:available`), exactly like a hand-typed declaration on the
        command line, so the assertion is made against the computed balance that
        means the same thing.
        """
        declared = _amount(body.balance)
        if declared is None:
            raise HTTPException(status_code=422, detail="a declaration needs an amount")
        with ledger_scope() as ledger:
            _require_real_account(ledger, account_id)
            ledger.record_declared_balance(
                account_id, _day(body.date), declared, f"manual:{body.kind}"
            )
            return _account_payload(ledger, account_id)

    @app.put("/api/accounts/{account_id}/opening")
    def set_opening(account_id: int, body: DeclarationRequest) -> dict:
        """Derive the opening balance from a declared figure: the `anchor` path.

        The declaration is recorded as well, tagged `anchor:<kind>`, so the
        check the derivation produces stays visible instead of vanishing with
        the request.
        """
        declared = _amount(body.balance)
        if declared is None:
            raise HTTPException(status_code=422, detail="an opening needs an amount")
        with ledger_scope() as ledger:
            _require_real_account(ledger, account_id)
            as_of = _day(body.date)
            ledger.anchor_opening(account_id, as_of, declared, body.kind)
            ledger.record_declared_balance(account_id, as_of, declared, f"anchor:{body.kind}")
            return _account_payload(ledger, account_id)

    @app.get("/api/anomalies")
    def anomalies(days: int = Query(31, ge=1, le=366)) -> list[dict]:
        with ledger_scope() as ledger:
            today = dt.date.today()
            return [
                {
                    "transaction_id": anomaly.transaction_id,
                    "date": anomaly.date.isoformat(),
                    "merchant": anomaly.merchant,
                    "category": anomaly.category,
                    "amount": format_decimal(anomaly.amount),
                    "median": format_decimal(anomaly.median),
                    "mad": format_decimal(anomaly.mad),
                    "score": f"{anomaly.score:.2f}",
                    "method": anomaly.method,
                    "sentence": anomaly.sentence,
                }
                for anomaly in detect_anomalies(ledger, today, recent_days=days)
            ]

    @app.get("/api/suggestions")
    def suggestions() -> list[dict]:
        with ledger_scope() as ledger:
            stakes = uncovered_spending(ledger)
            return [
                {
                    "merchant": row["merchant"],
                    "category": row["category"],
                    "source": row["source"],
                    "created_at": row["created_at"],
                    # What the decision is about. A proposal covers a merchant,
                    # not one movement, so the queue answers with how much is
                    # waiting, how many movements, and the span they cover.
                    "stake": _stake(stakes.get(row["merchant"])),
                }
                for row in ledger.suggestions()
            ]

    @app.post("/api/suggestions/decision")
    def decide_suggestion(body: SuggestionDecisionRequest) -> dict:
        # The merchant travels in the body: names routinely contain a slash
        # ("AMAZON/IT 123"), and a path segment would never reach the route.
        merchant = body.merchant
        with ledger_scope() as ledger:
            try:
                if body.decision == "accept":
                    suggestion = ledger.conn.execute(
                        "SELECT category FROM merchant_suggestions WHERE merchant = ?", (merchant,)
                    ).fetchone()
                    if suggestion is None:
                        raise KeyError(f"no suggestion for {merchant!r}")
                    # A proposal is a starting point: the decision carries the
                    # category that was chosen, and the ledger refuses one that is
                    # not a category of its own. The rule is written only when its
                    # text came with the request, and that text is the rule.
                    chosen = (body.category or suggestion["category"]).strip()
                    outcome = accept_merchant(ledger, merchant, chosen, rule=body.rule or None)
                    ledger.decide_suggestion(merchant, "accepted")
                else:
                    outcome = {"category": None, "rule": None, "movements": 0}
                    ledger.decide_suggestion(merchant, "dismissed")
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"merchant": merchant, "decision": body.decision, **outcome}

    @app.post("/api/propose")
    def propose() -> dict:
        with ledger_scope() as ledger:
            proposals = propose_categories(ledger)
            return {"considered": len(proposals), "recorded": apply_proposals(ledger, proposals)}

    @app.post("/api/llm-suggest")
    def llm_suggest() -> dict:
        with ledger_scope() as ledger:
            try:
                return {"recorded": propose_for_unseen(ledger, llm_config())}
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except requests.RequestException as exc:
                raise HTTPException(status_code=502, detail=f"the model call failed: {exc}") from exc
            except (ValueError, KeyError) as exc:
                # A malformed reply is an upstream failure, not a bad request.
                raise HTTPException(
                    status_code=502, detail=f"the model answered unusably: {exc}"
                ) from exc

    @app.get("/api/assistant")
    def assistant_state() -> dict:
        """Whether the assistant is on, what it has spent today, what it proposed."""
        with ledger_scope() as ledger:
            return assistant.state(ledger, llm_config())

    @app.get("/api/assistant/readings")
    def assistant_readings() -> list[dict]:
        """The readings kept: what was asked, what came back, on which numbers."""
        with ledger_scope() as ledger:
            return assistant.readings(ledger)

    @app.post("/api/assistant/ask")
    def assistant_ask(body: AssistantAskRequest) -> dict:
        """Read the numbers this ledger has already computed.

        Nothing here is a query language: the packet is built from the same
        functions the screens read, and the model is handed the figures.
        """
        with ledger_scope() as ledger:
            try:
                reading = assistant.ask(ledger, llm_config(), body.question, context=body.context)
            except LlmOff as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except RuntimeError as exc:
                # The day's ceiling: the answer is a message, not a failure.
                raise HTTPException(status_code=429, detail=str(exc)) from exc
            except requests.RequestException as exc:
                raise HTTPException(
                    status_code=502, detail=f"la chiamata al modello non è riuscita: {exc}"
                ) from exc
            except ValueError as exc:
                raise HTTPException(
                    status_code=502, detail=f"la lettura non è utilizzabile: {exc}"
                ) from exc
            return {
                "question": reading.question,
                "answer": reading.answer,
                "model": reading.model,
                "fingerprint": reading.fingerprint,
                "created_at": reading.created_at,
                "cached": reading.cached,
                "proposals": list(reading.proposals),
            }

    @app.post("/api/assistant/budgets/decision")
    def assistant_budget_decision(body: BudgetProposalDecisionRequest) -> dict:
        """Accept or drop a budget the assistant proposed, and only that."""
        with ledger_scope() as ledger:
            try:
                return assistant.decide_budget_proposal(ledger, body.category, body.decision)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/transactions")
    def transactions(
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
        account_id: int | None = None,
        category: str | None = None,
        status: str | None = None,
        search: str | None = None,
        transfer: bool | None = None,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict:
        where, params = _transaction_filters(
            from_date, to_date, account_id, category, status, search, transfer
        )
        with ledger_scope() as ledger:
            total = ledger.conn.execute(
                f"SELECT COUNT(*) AS c FROM transactions t JOIN accounts a ON a.id = t.account_id {where}",
                params,
            ).fetchone()["c"]
            rows = ledger.conn.execute(
                f"""SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id
                    {where} ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?""",
                params + [limit, offset],
            ).fetchall()
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": [_transaction(row, ledger) for row in rows],
            }

    @app.get("/api/transactions/{transaction_id}")
    def transaction(transaction_id: int) -> dict:
        with ledger_scope() as ledger:
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @app.get("/api/review")
    def review(
        limit: int = Query(50, ge=1, le=200),
        state: Literal["all", "proposed", "unhandled"] = "all",
        account_id: int | None = None,
        search: str | None = None,
    ) -> dict:
        """The queue, with what each row already survived spelled out.

        A row that appears here already escaped the transfer matcher: linking a
        pair moves a leg's posting to the clearing account, so anything still on
        ``Uncategorized`` is spending no pairing claimed. What is left to know is
        the classifier: a merchant with a pending proposal is waiting for a
        decision, one without it fell through every automatic pass and is manual
        work — that is the state the UI flags.
        """
        with ledger_scope() as ledger:
            pending = {
                row["merchant"]: row["category"] for row in ledger.suggestions("pending")
            }
            # Three columns only: a long uncategorized history must not drag
            # every raw payload into memory just to be counted.
            backlog = ledger.conn.execute(
                f"SELECT t.id, t.description, t.account_id FROM transactions t {UNCATEGORIZED_WHERE}"
                " ORDER BY t.date DESC, t.id DESC",
                (UNCATEGORIZED,),
            ).fetchall()
            by_id = {row["id"]: row for row in backlog}
            proposed = [row["id"] for row in backlog if pending.get(merchant_name(row["description"]))]
            unhandled = [row["id"] for row in backlog if not pending.get(merchant_name(row["description"]))]

            selected = {"all": [row["id"] for row in backlog], "proposed": proposed, "unhandled": unhandled}[state]
            if account_id is not None:
                selected = [row_id for row_id in selected if by_id[row_id]["account_id"] == account_id]
            if search:
                needle = search.casefold()
                selected = [
                    row_id
                    for row_id in selected
                    if needle in (by_id[row_id]["description"] or "").casefold()
                ]

            uncategorized = _review_page(ledger, selected[:limit], UNCATEGORIZED_WHERE)
            transfers_total = ledger.conn.execute(
                "SELECT COUNT(*) AS c FROM transfer_links WHERE confirmed_by_human = 0"
            ).fetchone()["c"]
            links = ledger.conn.execute(
                """SELECT * FROM transfer_links WHERE confirmed_by_human = 0
                   ORDER BY leg_a DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            transfers = []
            for link in links:
                leg_a = _require_transaction(ledger, link["leg_a"])
                leg_b = _require_transaction(ledger, link["leg_b"])
                transfers.append(
                    {
                        "confidence": link["confidence"],
                        "method": link["method"],
                        "leg_a": _transaction(leg_a, ledger),
                        "leg_b": _transaction(leg_b, ledger),
                    }
                )
            # The accounts that actually have rows in the backlog, so the filter
            # offers only choices that can return something.
            accounts = [
                {"id": row["id"], "name": row["name"]}
                for row in ledger.conn.execute(
                    f"""SELECT DISTINCT a.id, a.name FROM transactions t
                        JOIN accounts a ON a.id = t.account_id {UNCATEGORIZED_WHERE}
                        ORDER BY a.name""",
                    (UNCATEGORIZED,),
                )
            ]
            return {
                "uncategorized": [_review_transaction(row, ledger, pending) for row in uncategorized],
                # The counts are the real backlog, never the length of the page
                # and never a function of the filter: the chips must not lie
                # about how much work is behind them.
                "accounts": accounts,
                "uncategorized_total": len(backlog),
                "proposed_total": len(proposed),
                "unhandled_total": len(unhandled),
                "transfers": transfers,
                "transfers_total": transfers_total,
                "proposals_total": len(pending),
                "applied": {"state": state, "account_id": account_id, "search": search},
            }

    @app.get("/api/rules")
    def rules() -> list[dict]:
        with ledger_scope() as ledger:
            rules = RuleBook(ledger.conn).rules()
            usage = rule_usage(ledger, rules)
            return [_rule_payload(ledger, rule, usage.get(rule.id or 0, 0)) for rule in rules]

    # -- writes ------------------------------------------------------------

    @app.post("/api/categories", status_code=201)
    def add_category(body: CategoryNameRequest) -> dict:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="a category needs a name")
        with ledger_scope() as ledger:
            account_id = ledger.category(name)
            return {"id": account_id, "name": name}

    @app.patch("/api/categories/{account_id}")
    def patch_category(account_id: int, body: CategoryFlagsRequest) -> dict:
        if body.episodic is None and body.essential is None:
            raise HTTPException(status_code=422, detail="set episodic and/or essential")
        with ledger_scope() as ledger:
            try:
                if body.episodic is not None:
                    ledger.set_category_flag(account_id, "episodic", body.episodic)
                if body.essential is not None:
                    ledger.set_category_flag(account_id, "essential", body.essential)
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=404 if isinstance(exc, KeyError) else 422,
                                    detail=str(exc)) from exc
            row = ledger.account(account_id)
            return {
                "id": row["id"],
                "name": row["name"],
                "episodic": bool(row["episodic"]),
                "essential": bool(row["essential"]),
            }

    @app.get("/api/deleted")
    def deleted() -> list[dict]:
        """The movements a person deleted and has not brought back.

        Answered whole rather than per account: the Conti section asks once and
        groups them under the account each one belonged to, which is where the
        flag that would bring them all back also lives.
        """
        with ledger_scope() as ledger:
            return [_deleted_payload(row) for row in ledger.deleted_transactions()]

    @app.post("/api/deleted/{deleted_id}/restore")
    def restore_deleted(deleted_id: int) -> dict:
        """Put one deleted movement back, with the note it had when it went.

        Refused while a rule that deletes still matches it: the movement would be
        back in the trash at the next sync, and a restore that undoes itself is
        not one. The rule is named, so the person knows what to change.
        """
        with ledger_scope() as ledger:
            row = ledger.conn.execute(
                "SELECT * FROM deleted_transactions WHERE id = ?", (deleted_id,)
            ).fetchone()
            if row is not None:
                rule = deleting_rule(
                    ledger, row["description"], row["account_id"], parse_decimal(row["amount"])
                )
                if rule is not None:
                    raise HTTPException(
                        status_code=409,
                        detail=f"la regola «{rule.pattern}» lo cancellerebbe di nuovo: "
                        "togli o cambia la regola prima di ripristinarlo",
                    )
            try:
                transaction_id = ledger.restore_deleted(deleted_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @app.patch("/api/accounts/{account_id}")
    def patch_account(account_id: int, body: AccountFlagsRequest) -> dict:
        """Flip an account's own flags, and answer with the account.

        `investment` marks the account whose inflows are savings rather than
        spending; `reimport_deleted` decides whether a movement deleted here may
        come back at the next sync. Both are decisions about the account, so
        they are written here rather than on a movement, and the answer is the
        account as every other endpoint reads it.
        """
        if body.investment is None and body.reimport_deleted is None:
            raise HTTPException(status_code=422, detail="nothing to set")
        with ledger_scope() as ledger:
            try:
                if body.investment is not None:
                    ledger.set_investment(account_id, body.investment)
                if body.reimport_deleted is not None:
                    ledger.set_reimport_deleted(account_id, body.reimport_deleted)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return _account_payload(ledger, account_id)

    @app.put("/api/transactions/{transaction_id}/splits")
    def put_splits(transaction_id: int, body: SplitsRequest) -> dict:
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            if ledger.is_transfer(transaction_id):
                raise HTTPException(
                    status_code=409,
                    detail="the transaction is a leg of a transfer: review the link first",
                )
            try:
                ledger.set_splits(
                    transaction_id,
                    [(ledger.category(item.category), parse_decimal(item.amount)) for item in body.splits],
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @app.delete("/api/transactions/{transaction_id}")
    def delete_transaction(transaction_id: int) -> dict:
        """Take a movement out of the ledger, remembered as a tombstone.

        The row goes: this is not a flag on a movement that stays visible. What
        it carried — the bank's payload, the note, the identity the ledger
        dedupes by — is copied aside, so the next sync does not write it back
        and a person can still see and undo the deletion.
        """
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            deletion = ledger.delete_transaction(transaction_id)
            return {"id": deletion.transaction_id, "unlinked_pair": deletion.unlinked_pair}

    @app.post("/api/transactions/delete")
    def delete_transactions(body: TransactionIdsRequest) -> dict:
        """Delete several movements at once — a page selected in Movimenti.

        Each one as the single delete does it, tombstone and all, in one
        transaction; an id the ledger does not hold refuses the whole batch.
        """
        if not body.ids:
            raise HTTPException(status_code=422, detail="no movement to delete")
        with ledger_scope() as ledger:
            try:
                deletions = ledger.delete_transactions(body.ids)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
            return {
                "deleted": len(deletions),
                "unlinked_pairs": sum(deletion.unlinked_pair for deletion in deletions),
            }

    @app.post("/api/transactions/category")
    def categorize_transactions(body: BatchCategoryRequest) -> dict:
        """Give several movements one category, as a person's own decision.

        A transfer leg and a split are skipped and counted: one category would
        hide the transfer or throw the split away, and each is decided by opening
        it.
        """
        if not body.ids:
            raise HTTPException(status_code=422, detail="no movement to categorize")
        with ledger_scope() as ledger:
            for transaction_id in body.ids:
                _require_transaction(ledger, transaction_id)
            account = ledger.category(body.category)
            categorized = 0
            with db.deferred_commits(ledger.conn):
                for transaction_id in dict.fromkeys(body.ids):
                    if ledger.is_transfer(transaction_id) or len(ledger.splits(transaction_id)) > 1:
                        continue
                    ledger.set_category(transaction_id, account)
                    categorized += 1
            return {"categorized": categorized, "skipped": len(set(body.ids)) - categorized}

    @app.put("/api/transactions/{transaction_id}/notes")
    def put_notes(transaction_id: int, body: NotesRequest) -> dict:
        """Write the local note of a movement, or clear it.

        The only field of a movement a person may rewrite: everything else is
        what the bank said, and the 5.4 assertion compares that statement with
        the ledger, so a hand-edited amount or date would break the one check
        that says whether the numbers can be trusted.
        """
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            ledger.set_notes(transaction_id, body.notes)
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @app.post("/api/transactions/{transaction_id}/category")
    def set_category(transaction_id: int, body: CategoryRequest) -> dict:
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            if ledger.is_transfer(transaction_id):
                raise HTTPException(
                    status_code=409,
                    detail="the transaction is a leg of a transfer: review the link first",
                )
            ledger.set_category(transaction_id, ledger.category(body.category))
            return _transaction(ledger.conn.execute(
                "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
            ).fetchone(), ledger)

    @app.post("/api/transfers/{leg_a}/{leg_b}/review")
    def review_transfer(leg_a: int, leg_b: int, body: ReviewRequest) -> dict:
        with ledger_scope() as ledger:
            try:
                ledger.set_transfer_review(leg_a, leg_b, body.decision)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"ok": True, "decision": body.decision}

    @app.get("/api/transfers/labels")
    def transfer_labels() -> dict:
        """The names a leg can be recorded into.

        ``configured`` is what a sync matches against the description and
        ``recorded`` is what earlier marks created: both are offered, because a
        second spelling of the same account is what this list exists to prevent.
        """
        with ledger_scope() as ledger:
            return {
                "configured": [d.destination for d in load_config(config_path).passthrough],
                "recorded": ledger.virtual_accounts(),
            }

    @app.get("/api/transfers/{transaction_id}/candidates")
    def transfer_candidates(transaction_id: int) -> list[dict]:
        """The legs this one could be paired with, best evidence first."""
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            return [
                _transaction(row, ledger) for row in pair_candidates(ledger, transaction_id)
            ]

    @app.post("/api/transfers/pair")
    def pair_transfer(body: TransferPairRequest) -> dict:
        with ledger_scope() as ledger:
            try:
                ledger.mark_transfer_pair(body.leg_a, body.leg_b)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return _transaction(_require_transaction(ledger, body.leg_a), ledger)

    @app.post("/api/transfers/passthrough")
    def passthrough_leg(body: TransferPassthroughRequest) -> dict:
        """Record a leg as money that is neither income nor spending."""
        with ledger_scope() as ledger:
            try:
                ledger.mark_passthrough(body.transaction_id, body.destination)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return _transaction(_require_transaction(ledger, body.transaction_id), ledger)

    @app.post("/api/transfers/unlink")
    def unlink_transfer(body: TransferUnlinkRequest) -> dict:
        """Undo a transfer.

        ``configured`` says the released name is one the configuration
        re-applies: the next sync puts the leg back, and the answer is to change
        ``passthrough`` in the configuration instead of unlinking it again.
        """
        with ledger_scope() as ledger:
            try:
                released = ledger.unlink_transfer(body.transaction_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            declarations = load_config(config_path).passthrough
            return {
                "released": released,
                "configured": released is not None
                and any(
                    released.casefold() == declared.destination.casefold()
                    for declared in declarations
                ),
                "transaction": _transaction(
                    _require_transaction(ledger, body.transaction_id), ledger
                ),
            }

    @app.post("/api/rules", status_code=201)
    def save_rule(body: RuleRequest) -> dict:
        """Write a rule and apply it now — a deleting one moves its movements to
        the trash, which is why the app asks `/api/rules/preview` first."""
        pattern = body.pattern.strip()
        if not pattern:
            raise HTTPException(status_code=422, detail="a rule needs a text to look for")
        with ledger_scope() as ledger:
            book = RuleBook(ledger.conn)
            try:
                count = book.set_rule(pattern, _rule_target(body), ledger, **_rule_fields(body))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
            saved = book.checked(pattern, _rule_target(body), ledger, **_rule_fields(body))
            stored = next(
                rule
                for rule in book.rules()
                if (rule.key, rule.account_id, rule.amount_min, rule.amount_max)
                == (saved.key, saved.account_id, saved.amount_min, saved.amount_max)
            )
            return _rule_payload(ledger, stored, count)

    @app.post("/api/rules/preview")
    def preview_rule(body: RuleRequest) -> dict:
        """What a rule would take if it were written now, writing nothing."""
        pattern = body.pattern.strip()
        if not pattern:
            raise HTTPException(status_code=422, detail="a rule needs a text to look for")
        with ledger_scope() as ledger:
            fields = _rule_fields(body)
            # A category named here is not created by a preview: only the text
            # and the conditions decide which movements a rule would take.
            rule = RuleBook(ledger.conn).checked(
                pattern, None, ledger, **{**fields, "action": "delete"}
            )
            found = preview(ledger, rule)
            return {
                "count": found["count"],
                "items": [
                    {
                        "id": row["id"],
                        "date": row["date"],
                        "amount": row["amount"],
                        "description": row["description"],
                        "account": row["account"],
                    }
                    for row in found["items"]
                ],
            }

    @app.post("/api/rules/remove")
    def remove_rule(body: RuleRemoveRequest) -> dict:
        with ledger_scope() as ledger:
            book = RuleBook(ledger.conn)
            if body.id is not None:
                try:
                    rule = book.rule(body.id)
                except KeyError as exc:
                    raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
                held = book.remove(body.id, ledger)
                return {"id": body.id, "pattern": rule.pattern, "held": held}
            pattern = (body.pattern or "").strip()
            held = book.remove_rule(pattern, ledger)
        if held is None:
            raise HTTPException(status_code=404, detail=f"no rule for {pattern!r}")
        return {"id": None, "pattern": pattern, "held": held}

    @app.post("/api/categorize")
    def run_categorize() -> dict:
        with ledger_scope() as ledger:
            return {"applied": categorize(ledger, RuleBook(ledger.conn))}

    @app.post("/api/sync")
    def run_sync() -> dict:
        """Fetch every configured account now, and answer with what it wrote.

        Synchronous on purpose: the caller asked for this run, and the answer is
        the run. The guard is the sync's own, so the button and the scheduled
        loop of `serve` can never write at the same time. A configuration that
        cannot be read is the caller's to see, in the same words the CLI prints.
        """
        try:
            config = load_config(config_path)
            client = _client(config)
        except (OSError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"cannot sync: {exc}")
        with ledger_scope() as ledger:
            try:
                result = SyncService(ledger, client, config).run()
            except SyncBusy as exc:
                raise HTTPException(status_code=409, detail=str(exc))
            return _sync_payload(ledger, result)

    @app.post("/api/sync/period")
    def run_period_sync(body: PeriodSyncRequest) -> dict:
        """One account over the period asked, window by window, or its preview.

        The period is refused with 422 before the bank is asked, and a run
        already going answers 409 like the full sync, whose lock this is. What
        comes back says, per window, what the bank returned — an empty window is
        an answer, not a period covered — and how many probable duplicates of an
        imported movement are waiting for a person.
        """
        date_from, date_to = _day(body.date_from), _day(body.date_to)
        with ledger_scope() as ledger:
            account = ledger.conn.execute(
                "SELECT * FROM accounts WHERE id = ? AND type = 'real'", (body.account_id,)
            ).fetchone()
            if account is None:
                raise HTTPException(
                    status_code=422, detail=f"account {body.account_id} is not a real account"
                )
            try:
                config = load_config(config_path)
                client = _client(config)
            except (OSError, KeyError, ValueError) as exc:
                raise HTTPException(status_code=503, detail=f"cannot sync: {exc}")
            service = SyncService(ledger, client, config)
            try:
                result = service.run_period(
                    account["name"], date_from, date_to, preview=body.preview
                )
            except PeriodInvalid as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except SyncBusy as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return _period_payload(ledger, account["id"], result)

    @app.get("/api/sync/held")
    def held_movements(account_id: int | None = None) -> list[dict]:
        """The probable duplicates a period sync did not write, still undecided."""
        with ledger_scope() as ledger:
            return [_held_payload(row) for row in ledger.held_transactions(account_id)]

    @app.post("/api/sync/held/{held_id}/{decision}")
    def decide_held(held_id: int, decision: str) -> dict:
        """Write one held movement or keep it out, and answer with what is left.

        A written movement is linked and categorized as a sync would have done,
        so it does not wait for the next one to leave the queue it belongs out
        of. The decision is final: a second one answers 409.
        """
        if decision not in ("write", "discard"):
            raise HTTPException(status_code=404, detail=f"no decision {decision!r}")
        with ledger_scope() as ledger:
            row = ledger.conn.execute(
                "SELECT account_id, date FROM held_transactions WHERE id = ?", (held_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"held movement {held_id} not found")
            try:
                transaction_id, action = ledger.decide_held(held_id, decision)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if transaction_id:
                link_transfers(ledger, since=dt.date.fromisoformat(row["date"]))
                link_passthrough_legs(ledger, _passthrough(config_path))
                categorize(ledger, RuleBook(ledger.conn))
            return {
                "transaction_id": transaction_id or None,
                "action": action,
                "held": [_held_payload(item) for item in ledger.held_transactions(row["account_id"])],
            }

    @app.post("/api/import/csv/preview")
    def csv_import_preview(body: CsvImportRequest) -> dict:
        """What the statement would become, before anything is written.

        The column names come back even when the mapping is not finished: they
        are what the screen needs in order to finish choosing.
        """
        _refuse_oversized(body.content)
        mapping = body.mapping.model_dump()
        problem = missing_from_mapping(mapping)
        with ledger_scope() as ledger:
            account = _import_account(ledger, body.account)
            with csv_file(body.content) as path:
                payload = preview_csv(
                    path,
                    mapping=mapping,
                    account_id=account["id"],
                    balancing_account_id=ledger.uncategorized(),
                )
        return {"ready": problem is None, "problem": problem, **payload}

    @app.post("/api/import/csv")
    def csv_import(body: CsvImportRequest) -> dict:
        """Write the mapped rows, then link and categorize them as `import` does.

        The pipeline is the CLI's, in the same order: the rows land, the matcher
        pairs what it can, the configured passthrough labels take their legs out
        of spending and income, and the rules classify what is left.
        """
        _refuse_oversized(body.content)
        mapping = body.mapping.model_dump()
        problem = missing_from_mapping(mapping)
        if problem is not None:
            raise HTTPException(status_code=422, detail=problem)
        profile = profile_from_mapping(mapping)
        with ledger_scope() as ledger:
            account = _import_account(ledger, body.account)
            with csv_file(body.content) as path:
                transactions, errors = read_mapped(
                    path,
                    profile=profile,
                    account_id=account["id"],
                    balancing_account_id=ledger.uncategorized(),
                    source_file=body.filename or None,
                )
            counts = ledger.record_batch(transactions)
            links = link_transfers(ledger)
            legs = link_passthrough_legs(ledger, _passthrough(config_path))
            ledger.validate()
            applied = categorize(ledger, RuleBook(ledger.conn))
            return {
                "account": account["name"],
                "filename": body.filename,
                "parsed": len(transactions),
                "actions": counts,
                "rejected": [{"line": error.line, "reason": error.reason} for error in errors],
                "links": links,
                "passthrough": legs,
                "rules": applied,
            }

    _mount_pwa(app, web_dist if web_dist is not None else WEB_DIST)
    return app


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
                "balance_mismatch": entry.balance_mismatch,
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


def _scope(accounts: str | None, categories: str | None) -> LedgerScope:
    return LedgerScope(accounts=_names(accounts), categories=_names(categories))


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


def _period(from_date: str | None, to_date: str | None) -> tuple[dt.date, dt.date]:
    """The period a chart covers: the last twelve months unless asked otherwise.

    The end defaults to today, the start to the first day of the month eleven
    months earlier, which is the year the flows chart has always shown. A period
    that ends before it starts is a caller's mistake, not an empty chart.
    """
    end = _day(to_date) if to_date else dt.date.today()
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
    applied: dict = {"accounts": list(scope.accounts), "categories": list(scope.categories)}
    if period is not None:
        applied["from"], applied["to"] = period[0].isoformat(), period[1].isoformat()
    return applied


def _real_accounts(ledger: Ledger) -> list[sqlite3.Row]:
    return ledger.conn.execute("SELECT id FROM accounts WHERE type = 'real' ORDER BY name").fetchall()


def _require_real_account(ledger: Ledger, account_id: int) -> sqlite3.Row:
    row = ledger.conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
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


def _account_payload(ledger: Ledger, account_id: int) -> dict:
    """One account as every account endpoint answers it."""
    row = ledger.account(account_id)
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "institution": row["institution"],
        "balance": format_decimal(ledger.balance(row["id"], dt.date.today())),
        "opening_date": row["opening_date"],
        "opening_balance": row["opening_balance"],
        "investment": bool(row["investment"]),
        # Off means a movement deleted here stays deleted; on means the next
        # sync writes it back from the tombstone, note included.
        "reimport_deleted": bool(row["reimport_deleted"]),
        # Seen by a sync, so Enable Banking knows it: what the panel's period
        # sync needs. An account added by hand has no uid and nothing to ask.
        "connected": row["external_uid"] is not None,
        "verification": _verification(ledger, row["id"]),
    }


def _transaction_filters(
    from_date: str | None,
    to_date: str | None,
    account_id: int | None,
    category: str | None,
    status: str | None,
    search: str | None,
    transfer: bool | None,
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if from_date:
        clauses.append("t.date >= ?")
        params.append(from_date)
    if to_date:
        clauses.append("t.date <= ?")
        params.append(to_date)
    if account_id is not None:
        clauses.append("t.account_id = ?")
        params.append(account_id)
    if status:
        clauses.append("t.status = ?")
        params.append(status)
    if category:
        clauses.append(
            """EXISTS (SELECT 1 FROM postings p JOIN accounts c ON c.id = p.account_id
                       WHERE p.transaction_id = t.id AND c.type = 'category' AND c.name = ?)"""
        )
        params.append(category)
    if search:
        # A note is the one word a person wrote on a movement, so a search that
        # could not find it would make marking a movement pointless.
        clauses.append("(t.description LIKE ? OR t.counterparty LIKE ? OR t.notes LIKE ?)")
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if transfer is not None:
        # A leg's balancing side sits on a virtual account, so this is the same
        # test `Ledger.is_transfer` makes.
        leg = """EXISTS (SELECT 1 FROM postings p JOIN accounts v ON v.id = p.account_id
                         WHERE p.transaction_id = t.id AND v.type = 'virtual')"""
        clauses.append(leg if transfer else f"NOT {leg}")
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def _require_transaction(ledger: Ledger, transaction_id: int) -> sqlite3.Row:
    row = ledger.conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"transaction {transaction_id} not found")
    return row


def _budget_month(month: str | None) -> str:
    """The month a budget answer is for; the current one by default."""
    return parse_month(month) if month else month_of(dt.date.today())


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


def _money(value) -> str | None:
    return format_decimal(value) if value is not None else None


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
        "savings_flow": _money(metrics.savings_flow),
    }


def _review_page(ledger: Ledger, ids: list[int], uncategorized_where: str) -> list[sqlite3.Row]:
    """The full rows for the selected ids, most recent first.

    The ids were already ordered, so this is one bounded query rather than a
    scan of the whole backlog with every raw payload attached.
    """
    if not ids:
        return []
    placeholders = ", ".join("?" * len(ids))
    return list(
        ledger.conn.execute(
            f"""SELECT t.* FROM transactions t {uncategorized_where}
                AND t.id IN ({placeholders})
                ORDER BY t.date DESC, t.id DESC""",
            (UNCATEGORIZED, *ids),
        )
    )


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
        return {"movements": 0, "total": "0.00", "first_date": None, "last_date": None}
    return {
        "movements": stake.movements,
        "total": format_decimal(stake.total),
        "first_date": stake.first_date,
        "last_date": stake.last_date,
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
    }


def _mount_pwa(app: FastAPI, web_dist: Path) -> None:
    if not web_dist.exists():
        return
    assets = web_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (web_dist / path).resolve()
        # The shell names the assets, and a deploy replaces them with new names:
        # a document served from a cache points at files that no longer exist and
        # the app comes up blank. `no-cache` is "ask before using", so the
        # revalidation still answers 304 when nothing changed.
        headers = {"Cache-Control": "no-cache"}
        if path and candidate.is_file() and web_dist.resolve() in candidate.parents:
            return FileResponse(candidate, headers=headers)
        return FileResponse(web_dist / "index.html", headers=headers)
