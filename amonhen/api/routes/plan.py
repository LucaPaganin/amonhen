"""The plan (desiderata 5.16): goals, profile, tax years and fund against PAC."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException

from amonhen.api.context import AppContext
from amonhen.api.schemas import ComparisonRequest, GoalRequest, ProfileFactRequest, TaxParameterRequest
from amonhen.services.planning import comparison, overview


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    clock = ctx.clock
    ledger_scope = ctx.ledger_scope

    @router.get("/api/plan")
    def plan() -> dict:
        with ledger_scope() as ledger:
            return overview(ledger, clock.today())

    @router.put("/api/plan/goals")
    def put_goal(body: GoalRequest) -> dict:
        """Write a goal, or a new version of one, from ``valid_from`` on; answers with the plan."""
        with ledger_scope() as ledger:
            try:
                ledger.save_goal(
                    body.series, body.name, body.amount, dt.date.fromisoformat(body.target_date),
                    body.liquidity, dt.date.fromisoformat(body.valid_from),
                )
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return overview(ledger, clock.today())

    @router.delete("/api/plan/goals/{series}")
    def delete_goal(series: int) -> dict:
        """The goal stops holding today; a plan reopened on a day before still shows it."""
        with ledger_scope() as ledger:
            try:
                ledger.end_goal(series, clock.today())
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return overview(ledger, clock.today())

    @router.put("/api/plan/profile/{key}")
    def put_profile_fact(key: str, body: ProfileFactRequest) -> dict:
        with ledger_scope() as ledger:
            ledger.set_profile_fact(key, body.value, dt.date.fromisoformat(body.valid_from))
            return overview(ledger, clock.today())

    @router.put("/api/plan/tax/{year}/{key}")
    def put_tax_parameter(year: int, key: str, body: TaxParameterRequest) -> dict:
        with ledger_scope() as ledger:
            ledger.set_tax_parameter(year, key, body.value, body.source)
            return overview(ledger, clock.today())

    @router.delete("/api/plan/tax/{year}/{key}")
    def delete_tax_parameter(year: int, key: str) -> dict:
        with ledger_scope() as ledger:
            ledger.delete_tax_parameter(year, key)
            return overview(ledger, clock.today())

    @router.post("/api/plan/compare")
    def compare(body: ComparisonRequest) -> dict:
        with ledger_scope() as ledger:
            try:
                return comparison(
                    ledger, clock.today(), body.series, body.return_rate,
                    [(item.fund, item.pac) for item in body.allocations],
                )
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
