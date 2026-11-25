"""The tracked services (desiderata 5.17): their balances, sessions and payments."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query

from amonhen.api.context import AppContext
from amonhen.api.schemas import PaymentLinkRequest, ServiceRequest, SessionAmountRequest
from amonhen.composition import calendar_source
from amonhen.services import tracking

# One page of movements a person may link by hand: the search narrows the list,
# the page keeps it readable.
CANDIDATE_PAGE = 15
CANDIDATE_PAGE_MAX = 50


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    ledger_scope = ctx.ledger_scope

    @router.get("/api/services")
    def services() -> dict:
        with ledger_scope() as ledger:
            return {
                "services": tracking.overview(ledger, ctx.clock.today()),
                "calendar_configured": calendar_source_configured(),
                "calendar_window": _window_payload(ctx.clock.now()),
            }

    @router.post("/api/services")
    def create_service(body: ServiceRequest) -> dict:
        with ledger_scope() as ledger:
            service_id = ledger.save_service(None, **body.model_dump())
            ledger.link_payments_by_iban()
            return tracking.detail(ledger, service_id, ctx.clock.today())

    @router.get("/api/services/{service_id}")
    def service(service_id: int) -> dict:
        with ledger_scope() as ledger:
            return _detail_or_404(ledger, service_id, ctx.clock.today())

    @router.put("/api/services/{service_id}")
    def update_service(service_id: int, body: ServiceRequest) -> dict:
        with ledger_scope() as ledger:
            _detail_or_404(ledger, service_id, ctx.clock.today())
            ledger.save_service(service_id, **body.model_dump())
            ledger.link_payments_by_iban()
            return tracking.detail(ledger, service_id, ctx.clock.today())

    @router.get("/api/services/{service_id}/candidates")
    def candidates(
        service_id: int,
        q: str = "",
        limit: int = Query(CANDIDATE_PAGE, ge=1, le=CANDIDATE_PAGE_MAX),
        offset: int = Query(0, ge=0),
    ) -> dict:
        """One page of the movements that could pay this service, and how many there are."""
        with ledger_scope() as ledger:
            _detail_or_404(ledger, service_id, ctx.clock.today())
            return {
                "items": [dict(row) for row in ledger.payment_candidates(service_id, q, limit, offset)],
                "total": ledger.count_payment_candidates(service_id, q),
            }

    @router.put("/api/services/sessions/{event_id}/amount")
    def session_amount(event_id: str, body: SessionAmountRequest) -> dict:
        with ledger_scope() as ledger:
            session = ledger.session(event_id)
            if session is None:
                raise HTTPException(status_code=404, detail=f"session {event_id} not found")
            ledger.set_session_amount(event_id, body.amount)
            return tracking.detail(ledger, session["service_id"], ctx.clock.today())

    @router.put("/api/services/payments/{transaction_id}")
    def link_payment(transaction_id: int, body: PaymentLinkRequest) -> dict:
        """Link a movement to a service, or take it out; answers with the service it left or joined."""
        with ledger_scope() as ledger:
            if ledger.conn.execute("SELECT 1 FROM transactions WHERE id = ?", (transaction_id,)).fetchone() is None:
                raise HTTPException(status_code=404, detail=f"movement {transaction_id} not found")
            before = ledger.payment_service(transaction_id)
            ledger.link_payment(transaction_id, body.service_id)
            shown = body.service_id if body.service_id is not None else before
            if shown is None:
                return {}
            return tracking.detail(ledger, shown, ctx.clock.today())

    @router.post("/api/services/sync")
    def sync_calendars() -> dict:
        """Read the calendars now: the same pass the sync button runs after the banks."""
        try:
            source = calendar_source()
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=f"cannot read the calendars: {exc}") from exc
        if source is None:
            raise HTTPException(status_code=503, detail="no Google service account configured")
        window = tracking.calendar_window(ctx.clock.now())
        with ledger_scope() as ledger:
            result = tracking.sync_calendars(ledger, source, ctx.clock.now(), window)
            return {
                "calendars": calendars_payload(result),
                "window": _window_payload(ctx.clock.now()),
                "services": tracking.overview(ledger, ctx.clock.today()),
            }

    return router


def calendar_pass(ledger, now: dt.datetime) -> list[dict]:
    """The calendars after the banks, for the sync button: never a reason for it to fail.

    No account configured is an empty list; a key that does not load is one line
    with its error, the way an unreachable calendar is.
    """
    try:
        source = calendar_source()
    except ValueError as exc:
        return [{"calendar_id": "", "written": 0, "cancelled": 0, "error": str(exc)}]
    if source is None or not ledger.services(active_only=True):
        return []
    return calendars_payload(tracking.sync_calendars(ledger, source, now, tracking.calendar_window(now)))


def calendar_source_configured() -> bool:
    from amonhen import settings

    return bool(settings.GOOGLE_SERVICE_ACCOUNT_FILE)


def calendars_payload(result: tracking.CalendarSyncResult) -> list[dict]:
    return [
        {"calendar_id": c.calendar_id, "events": c.events, "written": c.written,
         "cancelled": c.cancelled, "error": c.error}
        for c in result.calendars
    ]


def _window_payload(now: dt.datetime) -> dict:
    """The days a read covers, so the screen can say which range it asked for."""
    from amonhen import settings

    window = tracking.calendar_window(now)
    return {
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "lookback_days": settings.CALENDAR_LOOKBACK_DAYS,
        "ahead_days": settings.CALENDAR_AHEAD_DAYS,
    }


def _detail_or_404(ledger, service_id: int, today: dt.date) -> dict:
    found = tracking.detail(ledger, service_id, today)
    if found is None:
        raise HTTPException(status_code=404, detail=f"service {service_id} not found")
    return found
