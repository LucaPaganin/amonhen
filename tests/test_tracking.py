"""The tracked services (desiderata 5.17): sessions from a calendar, payments by IBAN, FIFO coverage."""
import datetime as dt
from decimal import Decimal

import pytest

from amonhen.core.tracking import Session, coverage, title_matches
from amonhen.models import Account, IncomingTransaction
from amonhen.ports.calendar import (
    CalendarChanges,
    CalendarError,
    CalendarEvent,
    CalendarWindow,
    SyncTokenExpired,
)
from amonhen.services.ingest import settle_after_ingest
from amonhen.services.tracking import detail, overview, sync_calendars

NOW = dt.datetime(2026, 11, 24, 12, tzinfo=dt.UTC)
TODAY = NOW.date()
WINDOW = CalendarWindow(TODAY - dt.timedelta(days=90), TODAY + dt.timedelta(days=90))
IBAN = "IT60X0542811101000000123456"


class MemoryCalendar:
    """Answers with the events it holds inside the window; a token counts the reads.

    Like the real calendar, a full read lists only the events of the window it was
    asked for: an event outside it is out of sight, not deleted.
    """

    def __init__(self) -> None:
        self.events: dict[str, list[CalendarEvent]] = {}
        self.pending: dict[str, list[CalendarEvent]] = {}
        self.expire = False
        self.fail = False
        self.tokens: list[str | None] = []
        self.windows: list[CalendarWindow] = []

    def add(self, calendar_id, event_id, summary, start, cancelled=False):
        event = CalendarEvent(event_id, summary, start, cancelled)
        events = [e for e in self.events.get(calendar_id, []) if e.event_id != event_id]
        if not cancelled:
            events.append(event)
        self.events[calendar_id] = events
        self.pending.setdefault(calendar_id, []).append(event)

    def changes(self, calendar_id, sync_token, window):
        self.tokens.append(sync_token)
        self.windows.append(window)
        if self.fail:
            raise CalendarError("down")
        if sync_token and self.expire:
            self.expire = False
            raise SyncTokenExpired("old")
        if sync_token is None:
            listed = list(self.events.get(calendar_id, []))
        else:
            listed = self.pending.get(calendar_id, [])
        self.pending[calendar_id] = []
        in_window = [event for event in listed if _inside(event, window)]
        return CalendarChanges(in_window, f"token-{len(self.tokens)}")


def _inside(event: CalendarEvent, window: CalendarWindow) -> bool:
    day = event.start[:10]
    return day == "" or window.start.isoformat() <= day <= window.end.isoformat()


def lesson(ledger, **overrides):
    fields = dict(
        name="Ripetizioni Andrea", kind="lezione", direction="entrata", rate="25",
        calendar_id="andrea@cal", title_pattern="Lezione Andrea", counterparty_iban=IBAN,
    )
    fields.update(overrides)
    return ledger.save_service(None, **fields)


def credit(ledger, bank, day, amount, iban: str | None = IBAN, ext=None, description="Bonifico"):
    txn_id, _ = ledger.record(IncomingTransaction(
        account_id=bank, date=day, amount=Decimal(amount), description=description,
        status="BOOK", source="psd2", balancing_account_id=ledger.category("Ripetizioni"),
        external_id=ext or f"{day}-{amount}", counterparty_account=iban,
    ))
    return txn_id


# -- pure ------------------------------------------------------------------------

def test_a_title_matches_when_it_carries_the_pattern_or_an_expression():
    assert title_matches("Lezione Tennis", "  lezione   tennis ")
    assert title_matches("Lezione Tennis", "Lezione Tennis annullata")
    assert title_matches("Ripetizioni", "Ripetizioni Andrea")
    assert not title_matches("Ripetizioni", "Dentista")
    assert title_matches("/^seduta/", "Seduta dr Rossi")


def test_payments_cover_the_oldest_sessions_first():
    sessions = [
        Session("c", "2026-11-20T17:00:00+01:00", Decimal(25)),
        Session("a", "2026-11-06", Decimal(25)),
        Session("b", "2026-11-13", Decimal(25)),
        Session("d", "2026-12-01", Decimal(25)),
    ]
    result = coverage(sessions, Decimal(40), TODAY)
    assert result.due == Decimal(75)
    assert result.balance == Decimal(35)
    states = [(line.event_id, line.covered, line.state) for line in result.sessions]
    assert states == [
        ("a", Decimal(25), "pagata"),
        ("b", Decimal(15), "parziale"),
        ("c", Decimal(0), "da_pagare"),
        ("d", Decimal(0), "futura"),
    ]


def test_a_payment_ahead_leaves_a_negative_balance():
    result = coverage([Session("a", "2026-11-06", Decimal(25))], Decimal(100), TODAY)
    assert result.balance == Decimal(-75)
    assert result.sessions[0].state == "pagata"


# -- the calendar ------------------------------------------------------------------

def test_reading_twice_gives_the_same_sessions(ledger):
    service = lesson(ledger)
    calendar = MemoryCalendar()
    calendar.add("andrea@cal", "e1", "Lezione Andrea", "2026-11-06T17:00:00+01:00")
    calendar.add("andrea@cal", "e2", "Lezione Andrea", "2026-11-13T17:00:00+01:00")
    calendar.add("andrea@cal", "x", "Dentista", "2026-11-14T09:00:00+01:00")
    first = sync_calendars(ledger, calendar, NOW, WINDOW)
    second = sync_calendars(ledger, calendar, NOW, WINDOW)
    assert first.calendars[0].written == 2
    assert second.calendars[0].written == 0
    assert calendar.tokens == [None, "token-1"]
    assert [row["event_id"] for row in ledger.sessions_of(service)] == ["e1", "e2"]
    assert overview(ledger, TODAY)[0]["balance"] == "50.00"


def test_a_cancelled_event_leaves_the_balance_and_comes_back(ledger):
    service = lesson(ledger)
    calendar = MemoryCalendar()
    calendar.add("andrea@cal", "e1", "Lezione Andrea", "2026-11-06")
    sync_calendars(ledger, calendar, NOW, WINDOW)
    calendar.add("andrea@cal", "e1", "", "", cancelled=True)
    sync_calendars(ledger, calendar, NOW, WINDOW)
    view = detail(ledger, service, TODAY)
    assert view["balance"] == "0.00"
    assert [row["event_id"] for row in view["cancelled"]] == ["e1"]
    calendar.add("andrea@cal", "e1", "Lezione Andrea", "2026-11-06")
    sync_calendars(ledger, calendar, NOW, WINDOW)
    assert detail(ledger, service, TODAY)["balance"] == "25.00"


def test_an_amount_written_by_hand_survives_the_next_read(ledger):
    service = lesson(ledger)
    calendar = MemoryCalendar()
    calendar.add("andrea@cal", "e1", "Lezione Andrea", "2026-11-06")
    sync_calendars(ledger, calendar, NOW, WINDOW)
    ledger.set_session_amount("e1", "40")
    calendar.add("andrea@cal", "e1", "Lezione Andrea", "2026-11-07")
    sync_calendars(ledger, calendar, NOW, WINDOW)
    row = ledger.session("e1")
    assert (row["amount"], row["start"]) == ("40.00", "2026-11-07")
    assert ledger.service(service)["rate"] == "25.00"


def test_an_expired_token_reads_everything_and_cancels_what_is_gone(ledger):
    service = lesson(ledger)
    calendar = MemoryCalendar()
    calendar.add("andrea@cal", "e1", "Lezione Andrea", "2026-11-06")
    calendar.add("andrea@cal", "e2", "Lezione Andrea", "2026-11-13")
    sync_calendars(ledger, calendar, NOW, WINDOW)
    # Deleted while the token aged: the full read no longer lists it.
    calendar.events["andrea@cal"] = [e for e in calendar.events["andrea@cal"] if e.event_id != "e2"]
    calendar.pending["andrea@cal"] = []
    calendar.expire = True
    result = sync_calendars(ledger, calendar, NOW, WINDOW)
    assert result.calendars[0].cancelled == 1
    assert detail(ledger, service, TODAY)["balance"] == "25.00"


def test_a_calendar_that_does_not_answer_keeps_what_was_there(ledger):
    lesson(ledger)
    calendar = MemoryCalendar()
    calendar.add("andrea@cal", "e1", "Lezione Andrea", "2026-11-06")
    sync_calendars(ledger, calendar, NOW, WINDOW)
    calendar.fail = True
    result = sync_calendars(ledger, calendar, NOW, WINDOW)
    assert result.errors == ["andrea@cal: down"]
    assert overview(ledger, TODAY)[0]["balance"] == "25.00"


def test_the_read_asks_for_the_window_and_a_different_one_reads_everything(ledger):
    lesson(ledger)
    calendar = MemoryCalendar()
    calendar.add("andrea@cal", "e1", "Lezione Andrea", "2026-11-06")
    sync_calendars(ledger, calendar, NOW, WINDOW)
    sync_calendars(ledger, calendar, NOW, WINDOW)
    assert calendar.windows == [WINDOW, WINDOW]
    assert calendar.tokens == [None, "token-1"]
    sync_calendars(ledger, calendar, NOW, CalendarWindow(WINDOW.start, TODAY))
    assert calendar.tokens[-1] is None


def test_a_read_that_narrows_the_window_keeps_the_sessions_outside_it(ledger):
    service = lesson(ledger)
    calendar = MemoryCalendar()
    calendar.add("andrea@cal", "old", "Lezione Andrea", "2026-06-01")
    calendar.add("andrea@cal", "e1", "Lezione Andrea", "2026-11-06")
    sync_calendars(ledger, calendar, NOW, CalendarWindow(dt.date(2026, 5, 1), dt.date(2026, 12, 31)))
    assert len(ledger.sessions_of(service)) == 2
    result = sync_calendars(ledger, calendar, NOW, WINDOW)
    assert result.calendars[0].cancelled == 0
    assert [row["status"] for row in ledger.sessions_of(service)] == ["valida", "valida"]


# -- the payments ------------------------------------------------------------------

def test_candidates_are_searched_paged_and_the_likeliest_come_first(ledger):
    service = lesson(ledger)
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    paid = credit(ledger, bank, dt.date(2026, 11, 1), "25", iban="IT00KNOWN", ext="paid")
    ledger.link_payment(paid, service)
    same_payer = credit(ledger, bank, dt.date(2026, 11, 2), "40", iban="IT00KNOWN", ext="same")
    multiple = credit(ledger, bank, dt.date(2026, 11, 3), "75", iban=None, ext="multiple")
    debit = credit(ledger, bank, dt.date(2026, 11, 4), "-25", iban=None, ext="debit")
    old = credit(ledger, bank, dt.date(2019, 3, 7), "25", iban=None, ext="old")

    # Whoever already paid comes first, then a whole number of sessions, then the date.
    rows = ledger.payment_candidates(service)
    assert [row["id"] for row in rows] == [same_payer, multiple, old]
    assert ledger.count_payment_candidates(service) == 3
    assert paid not in [row["id"] for row in rows]
    assert debit not in [row["id"] for row in rows]

    assert [row["id"] for row in ledger.payment_candidates(service, "75")] == [multiple]
    assert ledger.count_payment_candidates(service, "75") == 1
    assert [row["id"] for row in ledger.payment_candidates(service, limit=1)] == [same_payer]
    assert [row["id"] for row in ledger.payment_candidates(service, limit=1, offset=1)] == [multiple]


def test_payments_link_by_iban_in_the_service_direction(ledger):
    service = lesson(ledger)
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    calendar = MemoryCalendar()
    for n, day in enumerate(("2026-11-06", "2026-11-13", "2026-11-20"), 1):
        calendar.add("andrea@cal", f"e{n}", "Lezione Andrea", day)
    sync_calendars(ledger, calendar, NOW, WINDOW)
    credit(ledger, bank, dt.date(2026, 11, 21), "50", iban="IT60 X054 2811 1010 0000 0123 456")
    credit(ledger, bank, dt.date(2026, 11, 22), "-10")  # a debit to the same IBAN is not a payment
    credit(ledger, bank, dt.date(2026, 11, 22), "30", iban="IT00OTHER")
    settled = settle_after_ingest(ledger, [])
    assert settled.service_payments == 1
    view = detail(ledger, service, TODAY)
    assert view["balance"] == "25.00"
    assert [s["state"] for s in view["sessions"]] == ["pagata", "pagata", "da_pagare"]


def test_a_link_by_hand_wins_and_an_unlink_by_hand_stays(ledger):
    service = lesson(ledger)
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    from_iban = credit(ledger, bank, dt.date(2026, 11, 21), "50")
    cash = credit(ledger, bank, dt.date(2026, 11, 22), "25", iban=None)
    ledger.link_payment(from_iban, None)
    ledger.link_payment(cash, service)
    settle_after_ingest(ledger, [])
    assert [row["id"] for row in ledger.payments_of(service)] == [cash]


def test_a_deleted_movement_takes_its_link_with_it(ledger):
    service = lesson(ledger)
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    txn = credit(ledger, bank, dt.date(2026, 11, 21), "50")
    settle_after_ingest(ledger, [])
    ledger.delete_transaction(txn)
    assert ledger.payments_of(service) == []


def test_a_service_refuses_what_it_cannot_be(ledger):
    with pytest.raises(ValueError):
        lesson(ledger, kind="corso")
    with pytest.raises(ValueError):
        lesson(ledger, rate="-1")


# -- the API and the adapter -------------------------------------------------------

@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from amonhen.api import routes
    from amonhen.api.app import create_app
    from amonhen.db import connect, initialize
    from tests.fixed_clock import FixedClock
    from tests.test_amonhen_cli import MINIMAL_CONFIG

    db_path = tmp_path / "services.db"
    conn = connect(db_path)
    initialize(conn)
    conn.close()
    calendar = MemoryCalendar()
    monkeypatch.setattr(routes.services, "calendar_source", lambda: calendar)
    client = TestClient(create_app(
        db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG, clock=FixedClock(TODAY),
    ))
    client.calendar = calendar
    yield client
    client.close()


def test_the_api_creates_a_service_reads_its_calendar_and_corrects_a_session(api):
    created = api.post("/api/services", json={
        "name": "Tennis", "kind": "lezione", "direction": "uscita", "rate": "30",
        "calendar_id": "main@cal", "title_pattern": "Lezione Tennis",
    })
    assert created.status_code == 200, created.text
    service_id = created.json()["id"]
    api.calendar.add("main@cal", "t1", "Lezione Tennis", "2026-11-10T18:00:00+01:00")
    api.calendar.add("main@cal", "t2", "Lezione Tennis", "2026-12-10T18:00:00+01:00")
    synced = api.post("/api/services/sync").json()
    assert synced["calendars"][0]["written"] == 2
    assert synced["calendars"][0]["events"] == 2
    assert synced["window"]["lookback_days"] == 90
    assert synced["services"][0]["balance"] == "30.00"
    view = api.put("/api/services/sessions/t1/amount", json={"amount": "35"}).json()
    assert view["balance"] == "35.00"
    assert [s["state"] for s in view["sessions"]] == ["da_pagare", "futura"]
    assert api.get(f"/api/services/{service_id}/candidates").json() == {"items": [], "total": 0}
    window = api.get("/api/services").json()["calendar_window"]
    assert window["start"] == (TODAY - dt.timedelta(days=90)).isoformat()
    assert window["end"] == (TODAY + dt.timedelta(days=90)).isoformat()
    assert api.get("/api/services/999").status_code == 404


def test_the_adapter_follows_pages_and_reports_an_expired_token(tmp_path):
    import json

    import responses
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from amonhen.adapters.google_calendar import GoogleCalendar

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    key_file = tmp_path / "sa.json"
    key_file.write_text(json.dumps({
        "client_email": "amonhen@p.iam.gserviceaccount.com", "private_key": pem,
        "token_uri": "https://oauth2.googleapis.com/token",
    }))
    url = "https://www.googleapis.com/calendar/v3/calendars/a%40cal/events"
    with responses.RequestsMock() as mock:
        mock.post("https://oauth2.googleapis.com/token", json={"access_token": "tok", "expires_in": 3600})
        mock.get(url, json={"items": [{"id": "e1", "summary": "L", "start": {"date": "2026-11-06"}}],
                            "nextPageToken": "p2"})
        mock.get(url, json={"items": [{"id": "e2", "status": "cancelled"}], "nextSyncToken": "s1"})
        mock.get(url, status=410)
        calendar = GoogleCalendar(key_file)
        changes = calendar.changes("a@cal", None, WINDOW)
        assert [(e.event_id, e.start, e.cancelled) for e in changes.events] == [
            ("e1", "2026-11-06", False), ("e2", "", True),
        ]
        assert changes.next_sync_token == "s1"
        asked = next(call.request.url for call in mock.calls if "/events" in call.request.url)
        assert "timeMin=2026-08-26T00%3A00%3A00" in asked
        assert "timeMax=2027-02-22T23%3A59%3A59" in asked
        with pytest.raises(SyncTokenExpired):
            calendar.changes("a@cal", "s1", WINDOW)
        assert len([c for c in mock.calls if "token" in c.request.url and "oauth2" in c.request.url]) == 1
