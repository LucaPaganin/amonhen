"""PSD2 sync orchestration, driven by a fake client and the real fixtures."""
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest
import requests

from amonhen.config import ConfiguredAccount, MonitorConfig
from amonhen.providers.enable_banking import ConsentExpiredError
from amonhen.sync import SyncBusy, SyncService, _SYNC_LOCK

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "enable_banking" / "revolut_personale.json"
TODAY = dt.date(2026, 9, 12)


class FakeClient:
    SESSION_ACCOUNTS = [{"uid": "uid-1", "account_id": {"iban": "IT00X1"}, "currency": "EUR"}]
    DETAILS = {"account_id": {"iban": "IT68C0366901600600286658365"}}

    def __init__(
        self,
        transactions,
        *,
        expires=False,
        balances=(),
        balance_error=False,
        session_accounts=None,
        details=None,
        details_error=False,
    ):
        self.transactions = transactions
        self.expires = expires
        self.balances = list(balances)
        self.balance_error = balance_error
        self.session_accounts = (
            self.SESSION_ACCOUNTS if session_accounts is None else session_accounts
        )
        self.details = self.DETAILS if details is None else details
        self.details_error = details_error
        self.fetch_calls: list[tuple[str, dt.date, dt.date]] = []
        self.balance_calls: list[str] = []
        self.detail_calls: list[str] = []

    def fetch_transactions(self, account_uid, date_from, date_to=None):
        self.fetch_calls.append((account_uid, date_from, date_to))
        if self.expires:
            raise ConsentExpiredError("expired")
        return list(self.transactions)

    def fetch_balances(self, account_uid):
        self.balance_calls.append(account_uid)
        if self.balance_error:
            raise requests.ConnectionError("no route to the bank")
        return {"balances": list(self.balances)}

    def fetch_account_details(self, account_uid):
        self.detail_calls.append(account_uid)
        if self.details_error:
            raise ConsentExpiredError("expired")
        return dict(self.details)

    def list_accounts(self, session_id):
        return list(self.session_accounts)


def reported_balance(amount="304.60", balance_type="ITAV", reference="2026-09-12"):
    return {
        "balance_amount": {"amount": amount, "currency": "EUR"},
        "balance_type": balance_type,
        "reference_date": reference,
    }


def build_config(start=None):
    return MonitorConfig(
        application_id="app",
        pem_path=Path("private.pem"),
        redirect_url="http://localhost/callback",
        own_names=frozenset({"titolare conto"}),
        accounts=(
            ConfiguredAccount(
                name="Revolut personale",
                institution="Revolut",
                session_id="session-1",
                account_uid="uid-1",
                start_sync_date=dt.date.fromisoformat(start) if start else None,
            ),
        ),
    )


def fixture_transactions(limit=5):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data["transactions"][:limit]


def test_first_sync_inserts_every_transaction(ledger):
    transactions = fixture_transactions()
    service = SyncService(ledger, FakeClient(transactions), build_config(), today=TODAY)

    result = service.run()

    assert result.accounts[0].actions.get("inserted") == len(transactions)
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == len(transactions)
    ledger.validate()


def test_second_sync_over_the_same_window_duplicates_nothing(ledger):
    transactions = fixture_transactions()
    SyncService(ledger, FakeClient(transactions), build_config(), today=TODAY).run()

    result = SyncService(ledger, FakeClient(transactions), build_config(), today=TODAY).run()

    assert result.accounts[0].actions.get("duplicate") == len(transactions)
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == len(transactions)


def test_sync_refetches_a_short_overlap_after_the_last_transaction(ledger):
    transactions = fixture_transactions()
    SyncService(ledger, FakeClient(transactions), build_config(), today=TODAY).run()
    client = FakeClient(transactions)

    SyncService(ledger, client, build_config(), today=TODAY).run()

    _, date_from, _ = client.fetch_calls[0]
    last_date = max(t["booking_date"] for t in transactions)
    assert date_from == dt.date.fromisoformat(last_date) - dt.timedelta(days=7)


def test_first_sync_uses_the_configured_start_date(ledger):
    client = FakeClient(fixture_transactions())

    SyncService(ledger, client, build_config(start="2026-03-01"), today=TODAY).run()

    assert client.fetch_calls[0][1] == dt.date(2026, 3, 1)


def test_expired_consent_is_reported_and_does_not_raise(ledger):
    service = SyncService(ledger, FakeClient([], expires=True), build_config(), today=TODAY)

    result = service.run()

    assert result.errors and "consent expired" in result.errors[0]
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"] == 0


def test_sync_reports_a_declared_balance_mismatch(ledger):
    """Desiderata 5.4: the invariant is asserted in the sync process itself."""
    transactions = fixture_transactions()
    SyncService(ledger, FakeClient(transactions), build_config(), today=TODAY).run()
    account = ledger.find_account(name="Revolut personale")
    ledger.record_declared_balance(account["id"], TODAY, Decimal("999999.00"), "manual")

    result = SyncService(ledger, FakeClient(transactions), build_config(), today=TODAY).run()

    assert result.errors
    assert "disagrees with the declared balance" in result.errors[0]


def test_sync_records_the_raw_payload_and_its_provenance(ledger):
    transactions = fixture_transactions(1)
    SyncService(ledger, FakeClient(transactions), build_config(), today=TODAY).run()

    row = ledger.conn.execute("SELECT * FROM transactions").fetchone()

    assert json.loads(row["raw_payload"]) == transactions[0]
    assert row["source"] == "psd2"
    assert row["source_file"] is None


def test_sync_applies_the_deterministic_rules(ledger):
    """Every sync path, including the one inside the server, categorizes."""
    from amonhen.merchants import RuleBook, merchant_name
    from amonhen.providers.eb_normalize import normalize_transaction

    # The rule is in place before the sync fetches, so the movements have to come
    # out of the sync itself categorized, not out of writing the rule.
    incoming = normalize_transaction(
        fixture_transactions(1)[0], account_id=0, balancing_account_id=0
    )
    RuleBook(ledger.conn).set_rule(merchant_name(incoming.description), "Trasporti", ledger)

    result = SyncService(ledger, FakeClient(fixture_transactions()), build_config(), today=TODAY).run()

    assert result.rules_applied > 0
    categorized = ledger.conn.execute(
        """SELECT COUNT(*) AS c FROM postings p JOIN accounts a ON a.id = p.account_id
           WHERE a.name = 'Trasporti'"""
    ).fetchone()["c"]
    assert categorized == result.rules_applied


def test_sync_stores_the_balance_the_bank_reports(ledger):
    """The net worth chart is fed by observations, so the sync takes them."""
    service = SyncService(
        ledger,
        FakeClient(fixture_transactions(), balances=[reported_balance("304.60", "ITAV")]),
        build_config(),
        today=TODAY,
    )

    result = service.run()

    account = ledger.find_account(name="Revolut personale")
    row = ledger.conn.execute(
        "SELECT date, balance, source FROM account_balances WHERE account_id = ?",
        (account["id"],),
    ).fetchone()
    assert result.accounts[0].balances == 1
    assert (row["date"], row["balance"], row["source"]) == ("2026-09-12", "304.60", "eb:ITAV")


def test_sync_keeps_the_transactions_when_the_balance_call_fails(ledger):
    transactions = fixture_transactions()
    service = SyncService(
        ledger,
        FakeClient(transactions, balance_error=True),
        build_config(),
        today=TODAY,
    )

    result = service.run()

    assert result.accounts[0].actions.get("inserted") == len(transactions)
    assert result.accounts[0].balances == 0
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM account_balances").fetchone()["c"] == 0


def test_a_reported_balance_is_what_the_5_4_assertion_compares_against(ledger):
    """The bank's own balance lands in the ledger, so the check needs no help."""
    transactions = fixture_transactions()
    SyncService(ledger, FakeClient(transactions), build_config(), today=TODAY).run()
    account = ledger.find_account(name="Revolut personale")
    expected = ledger.balance(account["id"], TODAY)
    client = FakeClient(
        transactions, balances=[reported_balance(str(expected), "ITAV", TODAY.isoformat())]
    )

    result = SyncService(ledger, client, build_config(), today=TODAY).run()

    assert result.errors == []


def test_the_account_details_fill_the_iban_the_transfer_matcher_compares(ledger):
    """A session names an account without identifying it; the IBAN comes from details."""
    client = FakeClient(fixture_transactions(1), session_accounts=[{"uid": "uid-1"}])

    SyncService(ledger, client, build_config(), today=TODAY).run()

    account = ledger.find_account(name="Revolut personale")
    assert account["iban"] == FakeClient.DETAILS["account_id"]["iban"]
    # The details payload carries no uid, and the configured one must survive it.
    assert account["external_uid"] == "uid-1"
    assert client.detail_calls == ["uid-1"]


def test_an_unreachable_details_call_leaves_the_sync_alone(ledger):
    """A bank that will not answer about its account must not stop its movements."""
    transactions = fixture_transactions()
    client = FakeClient(
        transactions, session_accounts=[{"uid": "uid-1"}], details_error=True
    )

    result = SyncService(ledger, client, build_config(), today=TODAY).run()

    assert result.errors == []
    assert result.accounts[0].actions.get("inserted") == len(transactions)
    assert ledger.find_account(name="Revolut personale")["iban"] is None


def test_the_sync_does_not_call_an_explained_difference_a_mismatch(ledger):
    """A deleted movement makes the ledger short by design, and says why.

    The assertion exists to catch duplicates and gaps; a decision taken by hand
    is neither, and a sync that cried wolf about it would teach everyone to
    ignore the one line that matters.
    """
    transactions = fixture_transactions()
    SyncService(ledger, FakeClient(transactions), build_config(), today=TODAY).run()
    account = ledger.find_account(name="Revolut personale")
    expected = ledger.balance(account["id"], TODAY)
    victim = ledger.conn.execute(
        "SELECT id, amount FROM transactions WHERE status = 'BOOK' LIMIT 1"
    ).fetchone()
    ledger.delete_transaction(victim["id"])

    result = SyncService(
        ledger,
        FakeClient(transactions, balances=[reported_balance(str(expected), "ITAV", TODAY.isoformat())]),
        build_config(),
        today=TODAY,
    ).run()

    assert result.errors == []
    assert result.accounts[0].balance_mismatch is None
    # What it did write, it says: the deleted movement came back from the bank
    # and was left out.
    assert result.accounts[0].actions.get("suppressed") == 1

    # But a difference the deletion does not explain is still reported.
    wrong = SyncService(
        ledger,
        FakeClient(
            transactions,
            balances=[reported_balance(str(expected + Decimal("5.00")), "ITAV", TODAY.isoformat())],
        ),
        build_config(),
        today=TODAY,
    ).run()

    assert "disagrees with the declared balance" in wrong.errors[0]


def test_only_one_sync_runs_at_a_time_in_a_process(ledger):
    """The app's button and the scheduled loop of `serve` share one process.

    Two runs writing the same SQLite file is not a state worth having, so the
    second caller is turned away instead of being queued behind the first.
    """
    service = SyncService(ledger, FakeClient([]), build_config(), today=TODAY)

    with _SYNC_LOCK:  # a run already in progress, wherever it was asked from
        with pytest.raises(SyncBusy):
            service.run()

    # The same service run twice: a lock that went back after the first run is
    # the only way the second one gets in, so a leaked lock — a button dead
    # until the process restarts — fails here instead of in production.
    assert service.run().errors == []
    assert service.run().errors == []
