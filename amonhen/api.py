"""HTTP API and the host for the mobile PWA.

The surface is deliberately small: the two screens of phase 2 need a
filterable transaction list, the review queue, category changes and the
confirm/reject decision on a transfer link. No authentication: the app is
served behind Tailscale, and the ledger never leaves the machine.
"""
import calendar
import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator, Literal

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from amonhen import assistant, db
from amonhen.anomalies import detect_anomalies
from amonhen.classifier import apply_proposals, propose_categories
from amonhen.config import load_config, save_account
from amonhen.ledger import UNCATEGORIZED_WHERE, Ledger
from amonhen.llm import LlmOff, llm_config
from amonhen.merchants import (
    RuleBook,
    Stake,
    categorize,
    merchant_name,
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
from amonhen.providers.enable_banking import EnableBankingClient
from amonhen.settings import CONFIG_FILE, DB_PATH, UNCATEGORIZED
from amonhen.suggestions import propose_for_unseen
from amonhen.transfers import pair_candidates

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

# Bump when a response shape changes: the PWA compares this with the version it
# was built for and, when the server is older, says so instead of crashing on a
# key that is not there. The bundle is read from disk on every request while the
# Python process keeps running its old code, so the two can drift.
API_VERSION = 11

# Where an in-flight authorization waits between /connect and /callback.
PENDING_OAUTH = "pending_oauth"


def _client(config) -> EnableBankingClient:
    return EnableBankingClient(
        application_id=config.application_id,
        pem_path=config.pem_path,
        redirect_url=config.redirect_url,
    )


class CategoryRequest(BaseModel):
    category: str


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
    pattern: str
    category: str


class RuleRemoveRequest(BaseModel):
    pattern: str


class CategoryNameRequest(BaseModel):
    name: str


class CategoryFlagsRequest(BaseModel):
    episodic: bool | None = None
    essential: bool | None = None


class AccountFlagsRequest(BaseModel):
    investment: bool | None = None


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


class SuggestionDecisionRequest(BaseModel):
    merchant: str
    decision: Literal["accept", "dismiss"]
    # The category a person chose instead of the proposed one. Absent (or empty)
    # means the proposal was right; on a dismissal it is not read at all.
    category: str | None = None


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

    @app.get("/connect")
    def connect(bank: str, country: str, psu_type: str = "personal") -> RedirectResponse:
        config = load_config(config_path)
        client = _client(config)
        try:
            state, valid_until, url = client.start_auth(bank, country, psu_type)
        except requests.HTTPError as exc:
            # The bank rejects an ASPSP name it does not know: say so, rather
            # than turning it into a server error.
            raise HTTPException(
                status_code=502, detail=f"Enable Banking refused the request: {_upstream_detail(exc)}"
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
        return RedirectResponse(url, status_code=302)

    @app.get("/callback")
    def callback(code: str, state: str) -> dict:
        with ledger_scope() as ledger:
            pending = ledger.setting(PENDING_OAUTH)
            if not pending:
                raise HTTPException(status_code=400, detail="no authorization was started")
            request = json.loads(pending)
            if request.get("state") != state:
                raise HTTPException(status_code=400, detail="the authorization state does not match")
            config = load_config(config_path)
            try:
                session = _client(config).complete_auth(code, state)
            except requests.HTTPError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Enable Banking refused the session: {_upstream_detail(exc)}",
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
            return {
                "session_id": session_id,
                "accounts": [account.get("uid") for account in connected],
                # Which entries were refreshed and which were added: a bank that
                # returns several accounts writes several, and the person keeps
                # the ones they want before the sync imports them all.
                "written": written,
                "next": (
                    "run `uv run amonhen sync` to import this session"
                    if len(connected) == 1
                    else "edit accounts.json to keep the accounts you want, "
                    "then run `uv run amonhen sync`"
                ),
            }

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
            start, end = _month_bounds(month)
            return ledger.budget_status(start, end)

    @app.put("/api/budgets/{category_id}")
    def put_budget(category_id: int, body: BudgetRequest, month: str | None = None) -> dict:
        """Set or clear one category's monthly budget, answering for a month.

        The amount is one per category and applies to every month; ``month``
        decides which month's spend the answer reports, so a client looking at
        August is never handed July's figures.
        """
        with ledger_scope() as ledger:
            row = ledger.conn.execute(
                "SELECT type, name FROM accounts WHERE id = ?", (category_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"account {category_id} not found")
            if row["type"] != "category" or row["name"] == UNCATEGORIZED:
                raise HTTPException(
                    status_code=422,
                    detail=f"account {category_id} is not a category with a budget",
                )
            if body.amount is None:
                ledger.set_budget(category_id, None)
            else:
                ledger.set_budget(category_id, parse_decimal(body.amount))
            start, end = _month_bounds(month)
            return next(
                status for status in ledger.budget_status(start, end) if status["id"] == category_id
            )

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
                    # A proposal is a starting point: the rule carries the category
                    # that was chosen, and the ledger refuses one that is not a
                    # category of its own.
                    chosen = (body.category or suggestion["category"]).strip()
                    RuleBook(ledger.conn).set_rule(merchant, chosen, ledger)
                ledger.decide_suggestion(merchant, "accepted" if body.decision == "accept" else "dismissed")
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"merchant": merchant, "decision": body.decision}

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
            book = RuleBook(ledger.conn)
            usage = rule_usage(ledger, book.rules())
            return [
                {
                    "pattern": rule.pattern,
                    "category": rule.category,
                    "count": usage.get(rule.key, 0),
                }
                for rule in book.rules()
            ]

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

    @app.patch("/api/accounts/{account_id}")
    def patch_account(account_id: int, body: AccountFlagsRequest) -> dict:
        if body.investment is None:
            raise HTTPException(status_code=422, detail="set investment")
        with ledger_scope() as ledger:
            try:
                ledger.set_investment(account_id, body.investment)
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=404 if isinstance(exc, KeyError) else 422,
                                    detail=str(exc)) from exc
            row = ledger.account(account_id)
            return {
                "id": row["id"],
                "name": row["name"],
                "investment": bool(row["investment"]),
                "balance": format_decimal(ledger.balance(account_id, dt.date.today())),
                "opening_date": row["opening_date"],
            }

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
        pattern = body.pattern.strip()
        if not pattern:
            raise HTTPException(status_code=422, detail="a rule needs a text to look for")
        with ledger_scope() as ledger:
            count = RuleBook(ledger.conn).set_rule(pattern, body.category, ledger)
            return {"pattern": pattern, "category": body.category, "count": count}

    @app.post("/api/rules/remove")
    def remove_rule(body: RuleRemoveRequest) -> dict:
        pattern = body.pattern.strip()
        with ledger_scope() as ledger:
            held = RuleBook(ledger.conn).remove_rule(pattern, ledger)
        if held is None:
            raise HTTPException(status_code=404, detail=f"no rule for {pattern!r}")
        return {"pattern": pattern, "held": held}

    @app.post("/api/categorize")
    def run_categorize() -> dict:
        with ledger_scope() as ledger:
            return {"applied": categorize(ledger, RuleBook(ledger.conn))}

    _mount_pwa(app, web_dist if web_dist is not None else WEB_DIST)
    return app


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
        "state": "verified" if all(check.ok for check in checks) else "mismatch",
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
            }
            for check in checks
        ],
    }


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
        clauses.append("(t.description LIKE ? OR t.counterparty LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
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


def _month_bounds(month: str | None) -> tuple[dt.date, dt.date]:
    """First and last day of a YYYY-MM month; the current one by default."""
    if month:
        year, number = (int(part) for part in month.split("-"))
    else:
        today = dt.date.today()
        year, number = today.year, today.month
    last_day = calendar.monthrange(year, number)[1]
    return dt.date(year, number, 1), dt.date(year, number, last_day)


def _upstream_detail(exc: requests.HTTPError) -> str:
    """The bank's own explanation, which is what the operator needs to see."""
    response = exc.response
    if response is None:
        return str(exc)
    try:
        body = response.json()
    except ValueError:
        return f"{response.status_code} {response.text[:200]}"
    if isinstance(body, dict):
        for key in ("message", "detail", "error", "error_description"):
            if isinstance(body.get(key), str):
                return f"{response.status_code} {body[key]}"
    return f"{response.status_code} {response.text[:200]}"


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
