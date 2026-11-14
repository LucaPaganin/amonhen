"""The budget of a month (desiderata 5.12)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from amonhen.api.context import AppContext
from amonhen.api.payloads import (
    _budget_amount,
    _budget_month,
    _item_fields,
    _require_budget_item,
    _require_category,
)
from amonhen.api.schemas import BudgetCopyRequest, BudgetItemRequest, BudgetRequest
from amonhen.budgets import (
    add_item,
    budget_month,
    copy_items,
    delete_item,
    set_default,
    set_month_override,
    update_item,
)


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    ledger_scope = ctx.ledger_scope

    @router.get("/api/budgets")
    def budgets(month: str | None = None, months: int = Query(6, ge=3, le=24)) -> dict:
        """One month of budgets, read against the ``months`` complete months before it."""
        with ledger_scope() as ledger:
            return budget_month(ledger, _budget_month(month), window_months=months)
    @router.put("/api/budgets/{category_id}")
    def put_budget(
        category_id: int,
        body: BudgetRequest,
        month: str | None = None,
        months: int = Query(6, ge=3, le=24),
    ) -> dict:
        """Set or clear a category's default budget from ``month`` on.

        The months before it keep the budget they had, which is what makes a
        past month readable as it was. The answer is that whole month again.
        """
        month = _budget_month(month)
        with ledger_scope() as ledger:
            _require_category(ledger, category_id)
            set_default(ledger, category_id, month, _budget_amount(body.amount))
            return budget_month(ledger, month, window_months=months)
    @router.put("/api/budgets/{category_id}/override")
    def put_budget_override(
        category_id: int,
        body: BudgetRequest,
        month: str | None = None,
        months: int = Query(6, ge=3, le=24),
    ) -> dict:
        """Give one month its own budget for a category; an empty amount hands it back."""
        month = _budget_month(month)
        with ledger_scope() as ledger:
            _require_category(ledger, category_id)
            set_month_override(ledger, category_id, month, _budget_amount(body.amount))
            return budget_month(ledger, month, window_months=months)
    @router.post("/api/budgets/{category_id}/copy")
    def copy_budget_items(
        category_id: int, body: BudgetCopyRequest, months: int = Query(6, ge=3, le=24)
    ) -> dict:
        """Copy a category's planned expenses from one month into another."""
        with ledger_scope() as ledger:
            _require_category(ledger, category_id)
            copied = copy_items(ledger, category_id, body.from_month, body.to_month)
            return {
                "copied": copied,
                "budgets": budget_month(ledger, body.to_month, window_months=months),
            }
    @router.post("/api/budget-items", status_code=201)
    def create_budget_item(
        body: BudgetItemRequest, months: int = Query(6, ge=3, le=24)
    ) -> dict:
        """Plan an expense, with or without its category; answers with its month."""
        with ledger_scope() as ledger:
            if body.category_id is not None:
                _require_category(ledger, body.category_id)
            add_item(ledger, _item_fields(body))
            return budget_month(ledger, body.month, window_months=months)
    @router.put("/api/budget-items/{item_id}")
    def update_budget_item(
        item_id: int,
        body: BudgetItemRequest,
        month: str | None = None,
        months: int = Query(6, ge=3, le=24),
    ) -> dict:
        """Rewrite a planned expense, answering for ``month`` (by default the one it moved to)."""
        with ledger_scope() as ledger:
            _require_budget_item(ledger, item_id)
            if body.category_id is not None:
                _require_category(ledger, body.category_id)
            update_item(ledger, item_id, _item_fields(body))
            return budget_month(ledger, _budget_month(month or body.month), window_months=months)
    @router.delete("/api/budget-items/{item_id}")
    def delete_budget_item(item_id: int, months: int = Query(6, ge=3, le=24)) -> dict:
        """Drop a planned expense, answering with the month it was in."""
        with ledger_scope() as ledger:
            month = _require_budget_item(ledger, item_id)["month"]
            delete_item(ledger, item_id)
            return budget_month(ledger, month, window_months=months)

    return router
