"""The bank port: the sync over a bank in memory, and Enable Banking's translation.

The first half tests `SyncService` against `MemoryBank`, which implements the
port directly: no Enable Banking JSON, no HTTP, no credentials. The second half
tests the other side of the same contract: that the Enable Banking adapter turns
its client's payloads and errors into the port's types.
"""
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
import requests

from amonhen.adapters.enable_banking import EnableBankingProvider
from amonhen.adapters.enable_banking.client import (
    ConsentExpiredError,
    FetchedWindow as ClientWindow,
    RateLimitedError,
)
from amonhen.config import ConfiguredAccount, MonitorConfig
from amonhen.ports.bank import (
    BankAccount,
    BankProvider,
    BankUnavailable,
    ConsentExpired,
    DeclaredBalance,
    RateLimited,
)
from amonhen.sync import SyncService
from memory_bank import MemoryBank, Movement

TODAY = dt.date(2026, 9, 12)


def entry(name: str, uid: str, **fields) -> ConfiguredAccount:
    return ConfiguredAccount(name=name, institution="Banca", session_id="s", account_uid=uid, **fields)


def config(*accounts: ConfiguredAccount) -> MonitorConfig:
    return MonitorConfig(
        application_id="app",
        pem_path=Path("private.pem"),
        redirect_url="http://localhost/callback",
        own_names=frozenset(),
        accounts=accounts,
    )


def sync(ledger, bank, *accounts, today=TODAY):
    return SyncService(ledger, bank, config(*accounts), today=today)


def descriptions(ledger, name: str) -> list[str]:
    return [
        row["description"]
        for row in ledger.conn.execute(
            """SELECT t.description FROM transactions t JOIN accounts a ON a.id = t.account_id
               WHERE a.name = ? ORDER BY t.date, t.id""",
            (name,),
        )
    ]


# -- the contract ---------------------------------------------------------------


def test_both_banks_implement_the_port():
    assert isinstance(MemoryBank(), BankProvider)
    assert isinstance(EnableBankingProvider(client=object()), BankProvider)


# -- the sync, against the port alone ---------------------------------------------


def test_the_sync_writes_what_the_bank_reports_and_its_balance(ledger):
    bank = MemoryBank(
        movements={"uid-a": [
            Movement(dt.date(2026, 9, 1), "-12.30", "Caffè", external_id="a-1"),
            Movement(dt.date(2026, 9, 2), "1500.00", "Stipendio", external_id="a-2"),
        ]},
        balances_by_uid={"uid-a": [DeclaredBalance(dt.date(2026, 9, 11), Decimal("1487.70"), "ITBD")]},
        accounts={"uid-a": BankAccount(uid="uid-a", iban="IT00A", currency="EUR")},
    )

    result = sync(ledger, bank, entry("Conto", "uid-a")).run()

    assert result.errors == []
    assert result.accounts[0].fetched == 2
    assert result.accounts[0].balances == 1
    assert descriptions(ledger, "Conto") == ["Caffè", "Stipendio"]
    assert ledger.find_account(name="Conto")["iban"] == "IT00A"
    assert [row["source"] for row in ledger.declarations(ledger.find_account(name="Conto")["id"])] == ["eb:ITBD"]


def test_a_balance_without_a_date_stands_for_today(ledger):
    bank = MemoryBank(balances_by_uid={"uid-a": [DeclaredBalance(None, Decimal("10.00"), "ITAV")]})

    sync(ledger, bank, entry("Conto", "uid-a")).run()

    declared = ledger.declarations(ledger.find_account(name="Conto")["id"])
    assert [row["date"] for row in declared] == [TODAY.isoformat()]


def test_an_iban_the_listing_leaves_out_comes_from_the_details(ledger):
    class ListingWithoutIban(MemoryBank):
        def connected_accounts(self, account):
            super().connected_accounts(account)
            return [BankAccount(uid="uid-a")]

    bank = ListingWithoutIban(accounts={"uid-a": BankAccount(uid="uid-a", iban="IT00DETAILS")})

    sync(ledger, bank, entry("Conto", "uid-a")).run()

    assert ledger.find_account(name="Conto")["iban"] == "IT00DETAILS"
    assert ("account_details", "uid-a") in bank.calls


def test_each_failure_is_the_account_s_own_and_the_others_carry_on(ledger):
    bank = MemoryBank(
        movements={"ok": [Movement(dt.date(2026, 9, 1), "-5.00", "Pane", external_id="ok-1")]},
        failures={
            "dead": ConsentExpired("the consent was revoked"),
            "busy": RateLimited("429 Too Many Requests: quota"),
            "down": BankUnavailable("connection refused"),
        },
    )
    accounts = [entry(name, name) for name in ("dead", "busy", "down", "ok")]

    result = sync(ledger, bank, *accounts).run()

    by_name = {account.account: account for account in result.accounts}
    assert by_name["dead"].error == "consent expired: the consent was revoked"
    assert by_name["busy"].rate_limited is True
    assert by_name["busy"].error == "rate limited: 429 Too Many Requests: quota"
    assert by_name["down"].error == "fetch failed: connection refused"
    assert by_name["ok"].error is None
    assert descriptions(ledger, "ok") == ["Pane"]


def test_a_period_reports_a_refused_window_and_writes_the_others(ledger):
    bank = MemoryBank(
        movements={"uid-a": [
            Movement(dt.date(2026, 6, 5), "-1.00", "Giugno", external_id="m-1"),
            Movement(dt.date(2026, 7, 10), "-2.00", "Luglio", external_id="m-2"),
        ]},
        refused_windows={dt.date(2026, 7, 1): "400 period too long"},
    )
    bank.window_days = 30

    result = sync(ledger, bank, entry("Conto", "uid-a")).run_period(
        "Conto", dt.date(2026, 6, 1), dt.date(2026, 7, 30)
    )

    assert [(w.date_from, w.error) for w in result.windows] == [
        (dt.date(2026, 6, 1), None),
        (dt.date(2026, 7, 1), "400 period too long"),
    ]
    assert descriptions(ledger, "Conto") == ["Giugno"]


def test_a_dead_consent_stops_the_period_before_any_window(ledger):
    bank = MemoryBank(failures={"uid-a": ConsentExpired("expired")})

    result = sync(ledger, bank, entry("Conto", "uid-a")).run_period(
        "Conto", dt.date(2026, 6, 1), dt.date(2026, 6, 30)
    )

    assert result.error == "consent expired: expired"
    assert result.windows == []


# -- the adapter: Enable Banking's data and errors in the port's words -----------


class ScriptedClient:
    """Enable Banking's client as the adapter sees it, answering from a script."""

    def __init__(self, **answers):
        self.answers = answers

    def _answer(self, name):
        answer = self.answers[name]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def list_accounts(self, session_id):
        return self._answer("list_accounts")

    def fetch_account_details(self, uid):
        return self._answer("fetch_account_details")

    def fetch_transactions(self, uid, date_from, date_to, window_days):
        return self._answer("fetch_transactions")

    def fetch_transaction_windows(self, uid, date_from, date_to, window_days):
        return self._answer("fetch_transaction_windows")

    def fetch_balances(self, uid):
        return self._answer("fetch_balances")


@pytest.mark.parametrize(
    ("raised", "translated"),
    [
        (ConsentExpiredError("revoked"), ConsentExpired),
        (RateLimitedError("429 Too Many Requests: quota"), RateLimited),
        (requests.ConnectionError("unreachable"), BankUnavailable),
        (requests.HTTPError("500 Server Error"), BankUnavailable),
    ],
)
def test_the_adapter_speaks_the_port_s_errors(raised, translated):
    bank = EnableBankingProvider(ScriptedClient(fetch_transactions=raised))

    with pytest.raises(translated) as caught:
        bank.transactions(
            entry("Conto", "uid"), dt.date(2026, 9, 1), TODAY, account_id=1, balancing_account_id=2
        )

    # The provider's words survive: the app shows them to a person.
    assert str(caught.value) == str(raised)
    # And the original is still there for whoever reads a traceback.
    assert caught.value.__cause__ is raised


def test_the_adapter_reads_accounts_balances_and_windows_from_the_payloads():
    raw = {
        "entry_reference": "r-1",
        "booking_date": "2026-09-01",
        "transaction_amount": {"amount": "12.30", "currency": "EUR"},
        "credit_debit_indicator": "DBIT",
        "status": "BOOK",
        "remittance_information": ["Caffè"],
    }
    client = ScriptedClient(
        list_accounts=[{"uid": "uid-a", "account_id": {"iban": "IT00A"}, "currency": "EUR"}],
        fetch_account_details={"account_id": "IT00B"},
        fetch_balances={"balances": [
            {"balance_type": "ITAV", "reference_date": "2026-09-11",
             "balance_amount": {"amount": "10.5", "currency": "EUR"}},
            {"balance_type": "CLBD", "balance_amount": {"amount": ""}},
        ]},
        fetch_transaction_windows=[
            ClientWindow(dt.date(2026, 9, 1), dt.date(2026, 9, 30), [raw]),
            ClientWindow(dt.date(2026, 10, 1), dt.date(2026, 10, 30), error="400 refused"),
        ],
    )
    bank = EnableBankingProvider(client)
    account = entry("Conto", "uid-a")

    assert bank.connected_accounts(account) == [BankAccount("uid-a", "IT00A", "EUR")]
    assert bank.account_details(account) == BankAccount(iban="IT00B")
    # A figure with no amount is no figure; the amount is read as the bank wrote it.
    assert bank.balances(account) == [
        DeclaredBalance(dt.date(2026, 9, 11), Decimal("10.5"), "ITAV", "EUR")
    ]
    first, second = bank.transaction_windows(
        account, dt.date(2026, 9, 1), dt.date(2026, 10, 30), account_id=7, balancing_account_id=8
    )
    assert [(t.amount, t.account_id, t.raw) for t in first.transactions] == [(Decimal("-12.30"), 7, raw)]
    assert (second.transactions, second.error) == ([], "400 refused")
