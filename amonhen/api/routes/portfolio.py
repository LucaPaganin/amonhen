"""The portfolio (desiderata 5.16): what is held, the fund in transit, the reconciliations.

Read only but for one write: a month's unit value of the fund, when its page did not give it."""
from __future__ import annotations

from fastapi import APIRouter

from amonhen.api.context import AppContext
from amonhen.api.schemas import NavRequest
from amonhen.budgets import parse_month
from amonhen.models import parse_decimal
from amonhen.services.portfolio import overview, set_nav


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/portfolio")
    def portfolio() -> dict:
        """Nothing here writes: data enters through the use cases, from the sources."""
        with ctx.ledger_scope() as ledger:
            return overview(ledger, ctx.clock.today())

    @router.post("/api/portfolio/nav")
    def write_nav(body: NavRequest) -> dict:
        """The one figure a person writes here: a month's unit value the public page did not give."""
        with ctx.ledger_scope() as ledger:
            try:
                value = parse_decimal(body.value.strip())
            except ArithmeticError:
                raise ValueError(f"{body.value!r} non è un numero") from None
            set_nav(ledger, parse_month(body.month), value)
            return overview(ledger, ctx.clock.today())

    return router
