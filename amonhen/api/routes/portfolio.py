"""The portfolio (desiderata 5.16), read only: what is held, the fund in transit, the reconciliations."""
from __future__ import annotations

from fastapi import APIRouter

from amonhen.api.context import AppContext
from amonhen.services.portfolio import overview


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/portfolio")
    def portfolio() -> dict:
        """Nothing here writes: data enters through the use cases, from the sources."""
        with ctx.ledger_scope() as ledger:
            return overview(ledger, ctx.clock.today())

    return router
