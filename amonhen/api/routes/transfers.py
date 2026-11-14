"""Giroconti: the review of a pair, the candidates, pairing, passthrough, unlinking."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from amonhen import queries
from amonhen.api.context import AppContext
from amonhen.api.payloads import _require_transaction, _transaction
from amonhen.api.schemas import (
    ReviewRequest,
    TransferPairRequest,
    TransferPassthroughRequest,
    TransferUnlinkRequest,
)
from amonhen.config import load_config
from amonhen.transfers import pair_candidates


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    config_path = ctx.config_path
    ledger_scope = ctx.ledger_scope

    @router.post("/api/transfers/{leg_a}/{leg_b}/review")
    def review_transfer(leg_a: int, leg_b: int, body: ReviewRequest) -> dict:
        with ledger_scope() as ledger:
            try:
                ledger.set_transfer_review(leg_a, leg_b, body.decision)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"ok": True, "decision": body.decision}

    @router.get("/api/transfers/labels")
    def transfer_labels() -> dict:
        """The names a leg can be recorded into.

        ``configured`` is what a sync matches against the description and
        ``recorded`` is what earlier marks created: both are offered, because a
        second spelling of the same account is what this list exists to prevent.
        ``accounts`` are the real accounts a transfer rule writes the other half
        of the movement on instead of a virtual destination: those added by hand,
        and the connected ones that do not report their top-ups.
        """
        with ledger_scope() as ledger:
            return {
                "configured": [d.destination for d in load_config(config_path).passthrough],
                "recorded": ledger.virtual_accounts(),
                "accounts": queries.mirror_destinations(ledger),
            }

    @router.get("/api/transfers/{transaction_id}/candidates")
    def transfer_candidates(transaction_id: int) -> list[dict]:
        """The legs this one could be paired with, best evidence first."""
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            return [
                _transaction(row, ledger) for row in pair_candidates(ledger, transaction_id)
            ]

    @router.post("/api/transfers/pair")
    def pair_transfer(body: TransferPairRequest) -> dict:
        with ledger_scope() as ledger:
            try:
                ledger.mark_transfer_pair(body.leg_a, body.leg_b)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return _transaction(_require_transaction(ledger, body.leg_a), ledger)

    @router.post("/api/transfers/passthrough")
    def passthrough_leg(body: TransferPassthroughRequest) -> dict:
        """Record a leg as money that is neither income nor spending."""
        with ledger_scope() as ledger:
            try:
                ledger.mark_passthrough(body.transaction_id, body.destination)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return _transaction(_require_transaction(ledger, body.transaction_id), ledger)

    @router.post("/api/transfers/unlink")
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

    return router
