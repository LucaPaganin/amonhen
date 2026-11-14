"""The figures: health, the month, the metrics, the statistics, the dashboard series, the anomalies."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Query

from amonhen.anomalies import MIN_AMOUNT, detect_anomalies
from amonhen.api.context import AppContext
from amonhen.api.payloads import (
    _applied,
    _metrics_payload,
    _money,
    _period,
    _scope,
    _statistics_payload,
)
from amonhen.api.version import API_VERSION
from amonhen.metrics import (
    compute_metrics,
    latest_balances,
    month_reading,
    monthly_flows,
    net_worth_series,
    spend_by_category,
    spending_statistics,
)
from amonhen.models import format_decimal
from amonhen.settings import UNCATEGORIZED, VERSION


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    ledger_scope = ctx.ledger_scope

    # -- reads -------------------------------------------------------------

    @router.get("/api/health")
    def health() -> dict:
        # `version` is the release the server runs, which the app shows beside its
        # own: the bundle is read from disk, so the two can differ.
        return {
            "status": "ok",
            "api_version": API_VERSION,
            "version": VERSION,
            "uncategorized": UNCATEGORIZED,
        }

    @router.get("/api/month")
    def month(
        accounts: str | None = None, categories: str | None = None, tags: str | None = None
    ) -> dict:
        """The month in progress against the same point of the months before it."""
        scope = _scope(accounts, categories, tags)
        with ledger_scope() as ledger:
            reading = month_reading(ledger, dt.date.today(), scope)
            return {
                "currency": "EUR",
                "applied": _applied(scope),
                "month": reading.month,
                "day": reading.day,
                "spent": _money(reading.spent),
                "usual": _money(reading.usual),
                "rare": _money(reading.rare),
                "contributions": _money(reading.contributions),
                "net": _money(reading.net),
                "months_compared": reading.months_compared,
                "categories": [
                    {
                        "category": item.category,
                        "spent": _money(item.spent),
                        "usual": _money(item.usual),
                    }
                    for item in reading.categories
                ],
            }

    @router.get("/api/metrics")
    def metrics(
        accounts: str | None = None, categories: str | None = None, tags: str | None = None
    ) -> dict:
        """The 5.6 metrics for the selected accounts and categories.

        The period is not a parameter: these windows are the definition of the
        metrics, and the cards say which window each one used.
        """
        scope = _scope(accounts, categories, tags)
        with ledger_scope() as ledger:
            return _metrics_payload(compute_metrics(ledger, dt.date.today(), scope=scope), scope)

    @router.get("/api/statistics")
    def statistics(months: int = Query(12, ge=1, le=60)) -> dict:
        """Each category's last complete months: the median, the mean, the range."""
        with ledger_scope() as ledger:
            reading = spending_statistics(ledger, dt.date.today(), months)
            return {
                "currency": "EUR",
                "applied": {"months": months, "available": len(reading.months)},
                "months": list(reading.months),
                "total": None if reading.total is None else _statistics_payload(reading.total),
                "categories": [
                    {"category": item.category, **_statistics_payload(item.statistics)}
                    for item in reading.categories
                ],
            }

    @router.get("/api/spending")
    def spending(
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
        accounts: str | None = None,
        categories: str | None = None,
        tags: str | None = None,
    ) -> dict:
        """What each category took in the period: the slices of the pie."""
        scope = _scope(accounts, categories, tags)
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

    @router.get("/api/flows")
    def flows(
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
        accounts: str | None = None,
        categories: str | None = None,
        tags: str | None = None,
    ) -> dict:
        """Money in and out per month in the period, empty months included."""
        scope = _scope(accounts, categories, tags)
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

    @router.get("/api/networth")
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

    @router.get("/api/anomalies")
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
                for anomaly in detect_anomalies(
                    ledger, today, recent_days=days, min_amount=MIN_AMOUNT
                )
            ]

    return router
