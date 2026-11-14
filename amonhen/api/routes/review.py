"""The review queue and the proposals."""
from __future__ import annotations

from typing import Literal

import requests
from fastapi import APIRouter, HTTPException, Query

from amonhen.api.context import AppContext
from amonhen.api.payloads import (
    _require_transaction,
    _review_page,
    _review_transaction,
    _stake,
    _transaction,
)
from amonhen.api.schemas import SuggestionDecisionRequest
from amonhen.classifier import apply_proposals, propose_categories
from amonhen.ledger import CREDITS_WHERE, UNCATEGORIZED_WHERE
from amonhen.llm import llm_config
from amonhen.merchants import accept_merchant, merchant_name, uncovered_spending
from amonhen.settings import CREDITS_REVIEW_FROM, UNCATEGORIZED
from amonhen.suggestions import propose_for_unseen


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    ledger_scope = ctx.ledger_scope

    @router.get("/api/suggestions")
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
    @router.post("/api/suggestions/decision")
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
    @router.post("/api/propose")
    def propose() -> dict:
        with ledger_scope() as ledger:
            proposals = propose_categories(ledger)
            return {"considered": len(proposals), "recorded": apply_proposals(ledger, proposals)}
    @router.post("/api/llm-suggest")
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
    @router.get("/api/review")
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

        `credits` is the block beside it, money in from `CREDITS_REVIEW_FROM` on.
        The filters are the list's: they leave it alone.
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
            waiting = (CREDITS_REVIEW_FROM, UNCATEGORIZED)
            credits_total = ledger.conn.execute(
                f"SELECT COUNT(*) AS c FROM transactions t {CREDITS_WHERE}", waiting
            ).fetchone()["c"]
            credits = ledger.conn.execute(
                f"""SELECT t.* FROM transactions t {CREDITS_WHERE}
                    ORDER BY t.date DESC, t.id DESC LIMIT ?""",
                (*waiting, limit),
            ).fetchall()
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
                "credits": [_transaction(row, ledger) for row in credits],
                "credits_total": credits_total,
                "applied": {"state": state, "account_id": account_id, "search": search},
            }

    return router
