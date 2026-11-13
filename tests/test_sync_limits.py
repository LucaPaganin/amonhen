"""A bank's rate limit, a restart, and a transfer rule that does not wait."""
import datetime as dt
from pathlib import Path

import pytest
import requests

from amonhen.config import ConfiguredAccount, MonitorConfig
from amonhen.db import open_ledger_db
from amonhen.ledger import Ledger
from amonhen.merchants import RuleBook
from amonhen.adapters.enable_banking.client import RateLimitedError
from amonhen.models import Account
from amonhen.sync import sync_limit
from amonhen.transfers import link_transfers
from test_sync_service import sync_service

TODAY = dt.date(2026, 9, 12)
TEXT = "From Conto di prova"


def raw(reference, amount, description, indicator):
    return {
        "entry_reference": reference,
        "booking_date": "2026-09-10",
        "status": "BOOK",
        "credit_debit_indicator": indicator,
        "transaction_amount": {"amount": amount, "currency": "EUR"},
        "remittance_information": [description],
    }


class Bank:
    """Accounts by uid: their movements, or `limited` to answer a 429."""

    def __init__(self, movements=None, limited=(), details_limited=()):
        self.movements = movements or {}
        self.limited = set(limited)
        self.details_limited = set(details_limited)
        self.calls: list[tuple[str, str]] = []
        self.on_fetch = None

    def _refused(self):
        return RateLimitedError("429 Too Many Requests: quota exceeded")

    def fetch_transactions(self, uid, date_from, date_to=None, window_days=30):
        self.calls.append(("transactions", uid))
        if self.on_fetch is not None:
            self.on_fetch(uid)
        if uid in self.limited:
            raise self._refused()
        return list(self.movements.get(uid, []))

    def fetch_balances(self, uid):
        self.calls.append(("balances", uid))
        return {"balances": []}

    def fetch_account_details(self, uid):
        self.calls.append(("details", uid))
        if uid in self.details_limited:
            raise self._refused()
        return {"account_id": {"iban": f"IT00{uid}"}}

    def list_accounts(self, session_id):
        return [{"uid": "A", "currency": "EUR"}, {"uid": "B", "currency": "EUR"}]


def config(*names):
    return MonitorConfig(
        application_id="app",
        pem_path=Path("private.pem"),
        redirect_url="http://localhost/callback",
        own_names=frozenset(),
        accounts=tuple(
            ConfiguredAccount(name=name, institution="Banca", session_id="s", account_uid=name)
            for name in names
        ),
    )


@pytest.fixture
def ledger(tmp_path):
    conn = open_ledger_db(tmp_path / "ledger.db")
    yield Ledger(conn)
    conn.close()


def service(ledger, bank, *names):
    return sync_service(ledger, bank, config(*names), today=TODAY)


def mirrors(ledger):
    return ledger.conn.execute(
        "SELECT COUNT(*) AS c FROM transactions WHERE mirror_of IS NOT NULL"
    ).fetchone()["c"]


def test_a_limited_account_is_left_alone_and_the_others_are_read(ledger):
    bank = Bank({"B": [raw("r1", "10.00", "Spesa", "DBIT")]}, limited={"A"})

    result = service(ledger, bank, "A", "B").run()

    assert result.accounts[0].rate_limited and "quota exceeded" in result.accounts[0].error
    assert result.accounts[1].actions.get("inserted") == 1
    assert ("balances", "A") not in bank.calls


def test_a_limit_on_the_details_spares_the_transactions_too(ledger):
    bank = Bank(details_limited={"A"})

    result = service(ledger, bank, "A").run()

    assert result.accounts[0].rate_limited
    assert ("transactions", "A") not in bank.calls


def test_the_account_says_it_until_a_read_works(ledger):
    service(ledger, Bank(), "A").run()
    account = ledger.find_account(name="A")["id"]
    assert sync_limit(ledger, account) is None

    service(ledger, Bank(limited={"A"}), "A").run()
    limit = sync_limit(ledger, account)
    assert limit["since"] and limit["last_read"]

    service(ledger, Bank(), "A").run()
    assert sync_limit(ledger, account) is None


def test_a_known_iban_is_not_asked_again(ledger):
    service(ledger, Bank(), "A").run()
    bank = Bank()

    service(ledger, bank, "A").run()

    assert ledger.find_account(name="A")["iban"]
    assert ("details", "A") not in bank.calls


def test_a_pass_is_due_when_none_ended_and_not_again_until_the_interval(ledger):
    first = service(ledger, Bank(), "A")
    assert first.due_in(6) == 0

    first.run()

    now = dt.datetime.now(dt.timezone.utc)
    assert 21000 < first.due_in(6, now) <= 21600
    assert first.due_in(6, now + dt.timedelta(hours=7)) == 0


def test_a_pass_that_hit_a_limit_still_counts_as_ended(ledger):
    limited = service(ledger, Bank(limited={"A"}), "A")

    limited.run()

    assert limited.due_in(6) > 0


def _deposit_rule(ledger):
    ledger.ensure_account(Account(name="Deposito", type="real"))
    RuleBook(ledger.conn).set_rule("conto di prova", "Deposito", ledger, action="transfer")


def test_the_other_half_does_not_wait_for_the_slowest_bank(ledger):
    _deposit_rule(ledger)
    seen = []
    bank = Bank({"A": [raw("r1", "112.00", TEXT, "CRDT")]})
    bank.on_fetch = lambda uid: seen.append((uid, mirrors(ledger)))

    service(ledger, bank, "A", "B").run()

    assert seen == [("A", 0), ("B", 1)]


def test_a_stopped_process_is_finished_with_no_bank_asked(ledger):
    bank = Bank({"A": [raw("r1", "112.00", TEXT, "CRDT")]})
    service(ledger, bank, "A").run()
    _deposit_rule(ledger)
    idle = Bank()

    service(ledger, idle, "A").settle()

    assert mirrors(ledger) == 1
    assert not [call for call in idle.calls if call[0] != "details"]


def test_a_rule_keeps_its_transfer_from_an_equal_amount_elsewhere(ledger):
    _deposit_rule(ledger)
    bank = Bank({
        "A": [raw("r1", "112.00", TEXT, "CRDT")],
        "B": [raw("r2", "112.00", "Bonifico qualsiasi", "DBIT")],
    })

    service(ledger, bank, "A", "B").run()

    assert mirrors(ledger) == 1
    leg = ledger.conn.execute(
        "SELECT id FROM transactions WHERE description = 'Bonifico qualsiasi'"
    ).fetchone()["id"]
    assert ledger.conn.execute(
        "SELECT COUNT(*) AS c FROM transfer_links WHERE leg_a = ? OR leg_b = ?", (leg, leg)
    ).fetchone()["c"] == 0
    assert link_transfers(ledger) == 0
