"""The sync: the button, one account over a period, the held probable duplicates."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException

from amonhen.api.context import AppContext
from amonhen.api.payloads import _day, _held_payload, _passthrough, _period_payload, _sync_payload
from amonhen.api.schemas import PeriodSyncRequest
from amonhen.composition import BankFactory, bank_factory
from amonhen.config import load_config
from amonhen.services.ingest import settle_after_ingest
from amonhen.sync import PeriodInvalid, SyncBusy, SyncService


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    config_path = ctx.config_path
    ledger_scope = ctx.ledger_scope

    @router.post("/api/sync")
    def run_sync(make_bank: BankFactory = Depends(bank_factory)) -> dict:
        """Fetch every configured account now, and answer with what it wrote.

        Synchronous on purpose: the caller asked for this run, and the answer is
        the run. The guard is the sync's own, so the button and the scheduled
        loop of `serve` can never write at the same time. A configuration that
        cannot be read is the caller's to see, in the same words the CLI prints.
        """
        try:
            config = load_config(config_path)
            bank = make_bank(config)
        except (OSError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"cannot sync: {exc}")
        with ledger_scope() as ledger:
            try:
                result = SyncService(ledger, bank, config).run()
            except SyncBusy as exc:
                raise HTTPException(status_code=409, detail=str(exc))
            return _sync_payload(ledger, result)
    @router.post("/api/sync/period")
    def run_period_sync(
        body: PeriodSyncRequest, make_bank: BankFactory = Depends(bank_factory)
    ) -> dict:
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
                bank = make_bank(config)
            except (OSError, KeyError, ValueError) as exc:
                raise HTTPException(status_code=503, detail=f"cannot sync: {exc}")
            service = SyncService(ledger, bank, config)
            try:
                result = service.run_period(
                    account["name"], date_from, date_to, preview=body.preview
                )
            except PeriodInvalid as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except SyncBusy as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return _period_payload(ledger, account["id"], result)
    @router.get("/api/sync/held")
    def held_movements(account_id: int | None = None) -> list[dict]:
        """The probable duplicates a period sync did not write, still undecided."""
        with ledger_scope() as ledger:
            return [_held_payload(row) for row in ledger.held_transactions(account_id)]
    @router.post("/api/sync/held/{held_id}/{decision}")
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
                settle_after_ingest(
                    ledger, _passthrough(config_path), since=dt.date.fromisoformat(row["date"])
                )
            return {
                "transaction_id": transaction_id or None,
                "action": action,
                "held": [_held_payload(item) for item in ledger.held_transactions(row["account_id"])],
            }

    return router
