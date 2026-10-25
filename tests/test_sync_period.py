"""A sync of one account over a chosen period, driven by the fake bank and the fixtures."""
import copy
import datetime as dt
from dataclasses import replace
from decimal import Decimal

import pytest

from amonhen.models import Account, IncomingTransaction
from amonhen.sync import PeriodInvalid, SyncBusy, SyncService, _SYNC_LOCK

from test_sync_service import TODAY, FakeClient, build_config, fixture_transactions

ACCOUNT = "Revolut personale"
SEPTEMBER = (dt.date(2025, 9, 1), dt.date(2025, 9, 30))


def count(ledger, sql="SELECT COUNT(*) FROM transactions", params=()):
    return ledger.conn.execute(sql, params).fetchone()[0]


def period(ledger, client, start=None, *, preview=False, config=None, dates=SEPTEMBER):
    service = SyncService(ledger, client, config or build_config(start), today=TODAY)
    return service.run_period(ACCOUNT, *dates, preview=preview)


def test_a_past_period_is_written_window_by_window(ledger):
    transactions = fixture_transactions(60)
    config = build_config()
    config = replace(config, accounts=(replace(config.accounts[0], max_window_days=10),))
    client = FakeClient(transactions)

    result = period(ledger, client, config=config)

    assert client.window_calls == [("uid-1", *SEPTEMBER, 10)]
    assert [(w.date_from.day, w.date_to.day) for w in result.windows] == [(1, 10), (11, 20), (21, 30)]
    in_september = sum(window.fetched for window in result.windows)
    assert result.actions == {"inserted": in_september}
    assert count(ledger) == in_september
    assert result.errors == []
    ledger.validate()


def test_the_same_period_twice_writes_nothing(ledger):
    client = FakeClient(fixture_transactions(60))
    first = period(ledger, client)

    second = period(ledger, client)

    assert second.actions == {"duplicate": first.actions["inserted"]}
    assert count(ledger) == first.actions["inserted"]


def test_a_failed_window_does_not_take_the_others_with_it(ledger):
    client = FakeClient(fixture_transactions(60), failing={dt.date(2025, 9, 1)})

    result = period(ledger, client)

    failed = [window for window in result.windows if window.error]
    assert [(w.date_from, w.date_to) for w in failed] == [(dt.date(2025, 9, 1), dt.date(2025, 9, 30))]
    # One thirty-day window here, so nothing else to write: narrow it.
    assert result.actions == {}
    assert result.errors == ["Revolut personale: 2025-09-01..2025-09-30: 400 period too long"]

    narrow = FakeClient(fixture_transactions(60), failing={dt.date(2025, 9, 1)})
    config = build_config()
    config = replace(config, accounts=(replace(config.accounts[0], max_window_days=15),))
    result = period(ledger, narrow, config=config)
    assert [bool(w.error) for w in result.windows] == [True, False]
    assert result.actions["inserted"] == result.windows[1].fetched == count(ledger)


def test_a_deleted_movement_stays_out_unless_the_account_takes_it_back(ledger):
    client = FakeClient(fixture_transactions(60))
    period(ledger, client)
    victim = ledger.conn.execute("SELECT id, account_id FROM transactions ORDER BY id LIMIT 1").fetchone()
    ledger.delete_transaction(victim["id"])

    assert period(ledger, client).actions.get("suppressed") == 1

    ledger.set_reimport_deleted(victim["account_id"], True)
    assert period(ledger, client).actions.get("reimported") == 1


def test_a_settled_movement_promotes_its_pending_twin(ledger):
    booked = fixture_transactions(1)[0]
    pending = copy.deepcopy(booked)
    pending["status"] = "PDNG"
    pending["entry_reference"] = "pending-reference"
    period(ledger, FakeClient([pending]))

    result = period(ledger, FakeClient([booked]))

    assert result.actions == {"promoted": 1}
    assert count(ledger, "SELECT COUNT(*) FROM transactions WHERE status = 'BOOK'") == 1


def test_the_incremental_cursor_and_start_sync_date_stay_where_they_were(ledger):
    transactions = fixture_transactions(60)
    recent = [raw for raw in transactions if raw["booking_date"] >= "2025-09-15"]
    SyncService(ledger, FakeClient(recent), build_config("2025-09-15"), today=TODAY).run()
    config = build_config("2025-09-15")

    # Older than start_sync_date, and still fetched: a period is not limited by it.
    result = period(ledger, FakeClient(transactions), config=config,
                    dates=(dt.date(2025, 9, 1), dt.date(2025, 9, 14)))
    assert result.actions["inserted"] == len(transactions) - len(recent)
    assert config.accounts[0].start_sync_date == dt.date(2025, 9, 15)

    after = FakeClient(recent)
    SyncService(ledger, after, config, today=TODAY).run()
    newest = max(raw["booking_date"] for raw in recent)
    assert after.fetch_calls[0][1] == dt.date.fromisoformat(newest) - dt.timedelta(days=7)


def test_a_movement_worded_differently_by_the_export_is_held(ledger):
    raw = fixture_transactions(1)[0]
    account_id = ledger.ensure_account(Account(name=ACCOUNT, type="real"))
    amount = Decimal(raw["transaction_amount"]["amount"])
    if raw["credit_debit_indicator"] == "DBIT":
        amount = -amount
    ledger.record(
        IncomingTransaction(
            account_id=account_id,
            date=dt.date.fromisoformat(raw["booking_date"]),
            amount=amount,
            description="As the export words it",
            status="BOOK",
            source="import",
            balancing_account_id=ledger.uncategorized(),
            source_file="export.csv",
        )
    )

    preview = period(ledger, FakeClient([raw]), preview=True)
    assert preview.actions == {"held": 1}
    assert preview.movements[0].twin_description == "As the export words it"
    assert preview.movements[0].twin_source == "import"
    assert count(ledger, "SELECT COUNT(*) FROM held_transactions") == 0

    result = period(ledger, FakeClient([raw]))
    assert result.actions == {"held": 1}
    assert result.held == 1
    assert count(ledger) == 1
    # Asked once: the same period again does not hold it a second time.
    assert period(ledger, FakeClient([raw])).held == 1

    held = ledger.held_transactions(account_id)
    assert [row["twin_description"] for row in held] == ["As the export words it"]
    transaction_id, action = ledger.decide_held(held[0]["id"], "write")
    assert action == "inserted" and transaction_id
    assert count(ledger) == 2
    assert period(ledger, FakeClient([raw])).actions == {"duplicate": 1}
    with pytest.raises(ValueError):
        ledger.decide_held(held[0]["id"], "discard")


def test_a_discarded_movement_is_not_asked_again(ledger):
    raw = fixture_transactions(1)[0]
    period(ledger, FakeClient([]))
    account_id = ledger.find_account(name=ACCOUNT)["id"]
    amount = Decimal(raw["transaction_amount"]["amount"])
    amount = -amount if raw["credit_debit_indicator"] == "DBIT" else amount
    ledger.record(
        IncomingTransaction(
            account_id=account_id, date=dt.date.fromisoformat(raw["booking_date"]),
            amount=amount, description="Other words", status="BOOK", source="import",
            balancing_account_id=ledger.uncategorized(),
        )
    )
    period(ledger, FakeClient([raw]))
    ledger.decide_held(ledger.held_transactions(account_id)[0]["id"], "discard")

    again = period(ledger, FakeClient([raw]))

    assert again.actions == {"discarded": 1}
    assert again.held == 0
    assert count(ledger) == 1


def test_a_preview_writes_nothing(ledger):
    result = period(ledger, FakeClient(fixture_transactions(60)), preview=True)

    assert result.actions["inserted"] == len(result.movements) > 0
    assert count(ledger) == 0


def test_transfers_inside_the_period_are_paired_before_start_sync_date(ledger):
    raw = next(t for t in fixture_transactions(60) if t["credit_debit_indicator"] == "CRDT")
    other = ledger.ensure_account(Account(name="Altro", type="real"))
    ledger.record(
        IncomingTransaction(
            account_id=other, date=dt.date.fromisoformat(raw["booking_date"]),
            amount=-Decimal(raw["transaction_amount"]["amount"]), description="Giroconto",
            status="BOOK", source="import", balancing_account_id=ledger.uncategorized(),
        )
    )

    # The configured start is later than anything in the period: the incremental
    # pass would never pair these legs.
    result = period(ledger, FakeClient([raw]), "2026-01-01")

    assert result.transfers_linked == 1


def test_the_period_is_checked_before_the_bank_is_asked(ledger):
    client = FakeClient(fixture_transactions(5))
    service = SyncService(ledger, client, build_config(), today=TODAY)

    with pytest.raises(PeriodInvalid, match="after it ends"):
        service.run_period(ACCOUNT, dt.date(2025, 9, 2), dt.date(2025, 9, 1))
    with pytest.raises(PeriodInvalid, match="after today"):
        service.run_period(ACCOUNT, dt.date(2026, 9, 1), TODAY + dt.timedelta(days=1))
    with pytest.raises(PeriodInvalid, match="no account named"):
        service.run_period("Nessuno", *SEPTEMBER)
    assert client.window_calls == []


def test_a_period_waits_for_no_one(ledger):
    _SYNC_LOCK.acquire()
    try:
        with pytest.raises(SyncBusy):
            period(ledger, FakeClient([]))
    finally:
        _SYNC_LOCK.release()


def test_an_expired_consent_is_reported_not_raised(ledger):
    result = period(ledger, FakeClient([], expires=True))

    assert result.error.startswith("consent expired")
    assert result.windows == []


def test_a_period_before_the_opening_leaves_the_verification_alone(ledger):
    transactions = fixture_transactions(60)
    recent = [raw for raw in transactions if raw["booking_date"] >= "2025-09-15"]
    SyncService(ledger, FakeClient(recent), build_config(), today=TODAY).run()
    account_id = ledger.find_account(name=ACCOUNT)["id"]
    as_of = dt.date(2025, 9, 30)
    ledger.anchor_opening(account_id, as_of, Decimal("1000.00"), "booked")
    ledger.record_declared_balance(account_id, as_of, Decimal("1000.00"), "eb:CLBD")

    result = period(ledger, FakeClient(transactions), dates=(dt.date(2025, 9, 1), dt.date(2025, 9, 14)))

    assert result.actions["inserted"] > 0
    assert result.balance_mismatch is None
