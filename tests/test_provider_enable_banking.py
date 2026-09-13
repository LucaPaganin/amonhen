"""Enable Banking provider: pure normalisation plus the HTTP client contract.

No network: fixtures are read from disk and HTTP is intercepted by `responses`.
"""
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import jwt as pyjwt
import pytest
import responses

from amonhen.dedup import content_hash
from amonhen.models import Account, IncomingTransaction
from amonhen.providers import (
    ConsentExpiredError,
    EnableBankingClient,
    normalize_account,
    normalize_transaction,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "enable_banking"
FIXTURES = sorted(FIXTURE_DIR.glob("*.json"))
API = "https://api.test"


def load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def client(rsa_pem):
    pem_path, _pub = rsa_pem
    return EnableBankingClient(
        application_id="app-123",
        pem_path=pem_path,
        redirect_url="https://cb.test/callback",
        api_url=API + "/",  # trailing slash should be stripped
    )


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_every_fixture_transaction_normalizes(path):
    fixture = load_fixture(path)
    for payload in fixture["transactions"]:
        txn = normalize_transaction(
            payload,
            account_id=1,
            balancing_account_id=2,
            bank_name=fixture["account"]["bank_name"],
            source_file=fixture["source_file"],
        )

        assert isinstance(txn, IncomingTransaction)
        assert txn.raw == payload
        assert txn.description, "description must never be empty"
        assert txn.counterparty
        assert txn.source == "psd2"
        assert txn.source_file == fixture["source_file"]

        raw_date = (
            payload.get("booking_date")
            or payload.get("value_date")
            or payload.get("transaction_date")
        )
        assert txn.date == dt.date.fromisoformat(raw_date[:10])
        assert txn.status == payload["status"]
        assert txn.currency == payload["transaction_amount"]["currency"]
        assert txn.external_id == (
            payload.get("entry_reference") or payload.get("transaction_id") or None
        )

        magnitude = Decimal(payload["transaction_amount"]["amount"])
        expected_amount = -magnitude if payload["credit_debit_indicator"] == "DBIT" else magnitude
        assert txn.amount == expected_amount

        side = (
            payload.get("creditor_account")
            if payload["credit_debit_indicator"] == "DBIT"
            else payload.get("debtor_account")
        )
        expected_iban = side.get("iban") if isinstance(side, dict) else None
        assert txn.counterparty_account == expected_iban


def test_same_payload_always_yields_equal_transaction_and_hash_args():
    payload = load_fixture(FIXTURE_DIR / "revolut_personale.json")["transactions"][0]
    kwargs = {"account_id": 7, "balancing_account_id": 9}

    first = normalize_transaction(payload, **kwargs)
    second = normalize_transaction(payload, **kwargs)

    assert first == second
    first_args = (first.account_id, first.date, first.amount, first.description)
    second_args = (second.account_id, second.date, second.amount, second.description)
    assert first_args == second_args
    assert content_hash(*first_args) == content_hash(*second_args)


def test_description_prefers_remittance_then_note_then_bank_code():
    base = {
        "booking_date": "2026-01-02",
        "credit_debit_indicator": "DBIT",
        "transaction_amount": {"amount": "10.00", "currency": "EUR"},
    }
    kwargs = {"account_id": 1, "balancing_account_id": 2}

    with_remittance = normalize_transaction(
        {
            **base,
            "remittance_information": ["POS PURCHASE", "SHOP 42"],
            "note": "ignored",
            "bank_transaction_code": {"code": "CARD_PAYMENT"},
        },
        **kwargs,
    )
    assert with_remittance.description == "POS PURCHASE | SHOP 42"

    with_note = normalize_transaction(
        {**base, "note": "Member note", "bank_transaction_code": {"code": "CARD_PAYMENT"}},
        **kwargs,
    )
    assert with_note.description == "Member note"

    with_code = normalize_transaction(
        {**base, "bank_transaction_code": {"code": "ATM"}}, **kwargs
    )
    assert with_code.description == "ATM"

    empty = normalize_transaction(base, **kwargs)
    assert empty.description == "Unknown"


def test_own_name_counterparty_falls_back_to_remittance():
    payload = {
        "booking_date": "2026-01-02",
        "status": "BOOK",
        "credit_debit_indicator": "DBIT",
        "transaction_amount": {"amount": "10.00", "currency": "EUR"},
        "creditor": {"name": "Nadia Verdi"},
        "remittance_information": ["Weekly groceries"],
        "bank_transaction_code": {"code": "CARD_PAYMENT"},
    }

    txn = normalize_transaction(
        payload,
        account_id=1,
        balancing_account_id=2,
        own_names=frozenset({"nadia verdi"}),
    )

    assert txn.counterparty == "Weekly groceries"


def test_fineco_order_beneficiary_uses_sender_as_counterparty():
    fixture = load_fixture(FIXTURE_DIR / "fineco.json")
    payload = next(
        t
        for t in fixture["transactions"]
        if "Ord:" in " ".join(t.get("remittance_information") or [])
    )

    txn = normalize_transaction(
        payload,
        account_id=1,
        balancing_account_id=2,
        bank_name=fixture["account"]["bank_name"],
    )

    assert txn.counterparty == "Paola Corallo"
    assert txn.counterparty != txn.description
    assert "Ord:" not in txn.counterparty


def test_fineco_card_remittance_strips_the_operative_details():
    fixture = load_fixture(FIXTURE_DIR / "fineco.json")
    payload = next(
        t
        for t in fixture["transactions"]
        if "Carta N." in " ".join(t.get("remittance_information") or [])
    )
    remittance = " ".join(payload["remittance_information"])

    txn = normalize_transaction(
        payload,
        account_id=1,
        balancing_account_id=2,
        bank_name=fixture["account"]["bank_name"],
    )

    # The counterparty is the merchant part of the remittance, before the
    # operative details, whatever the fixture happens to contain.
    assert txn.counterparty == remittance.split("Carta N.")[0].strip()
    assert "Carta N." not in txn.counterparty


def test_normalize_account_maps_uid_iban_and_currency():
    account = normalize_account(
        {
            "uid": "acc-1",
            "account_id": {"iban": "IT60X0542811101000000123456"},
            "currency": "GBP",
        },
        institution="Revolut",
        name="Main",
    )
    assert account == Account(
        name="Main",
        type="real",
        institution="Revolut",
        iban="IT60X0542811101000000123456",
        external_uid="acc-1",
        currency="GBP",
    )

    fallback = normalize_account({"uid": "acc-2"}, institution="X", name="Y", currency="USD")
    assert fallback.currency == "USD"
    assert fallback.iban is None


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

def test_api_url_normalised(client):
    assert client.api_url == API


def test_auth_header_carries_signed_jwt(client, rsa_pem):
    _pem, public_key = rsa_pem
    token = client._headers()["Authorization"].removeprefix("Bearer ")

    claims = pyjwt.decode(
        token, public_key, algorithms=["RS256"], audience="api.enablebanking.com"
    )

    assert claims["iss"] == "enablebanking.com"
    assert claims["sub"] == "app-123"
    assert claims["exp"] - claims["iat"] == 3600
    assert pyjwt.get_unverified_header(token)["kid"] == "app-123"


@responses.activate
def test_start_auth_posts_access_request(client):
    responses.post(f"{API}/auth", json={"url": "https://bank.test/redirect"})

    state, valid_until, url = client.start_auth("Revolut", "IT")

    assert url == "https://bank.test/redirect"
    assert valid_until.endswith("Z")
    body = json.loads(responses.calls[0].request.body)
    assert body["aspsp"] == {"name": "Revolut", "country": "IT"}
    assert body["state"] == state
    assert body["psu_type"] == "personal"
    assert body["redirect_url"] == "https://cb.test/callback"


@responses.activate
def test_complete_auth_exchanges_code(client):
    responses.post(f"{API}/sessions", json={"session_id": "s1", "accounts": [{"uid": "u1"}]})

    out = client.complete_auth("code-1", "state-1")

    assert out["session_id"] == "s1"
    assert json.loads(responses.calls[0].request.body) == {"code": "code-1", "state": "state-1"}


@responses.activate
def test_list_accounts_returns_the_session_accounts(client):
    responses.get(f"{API}/sessions/sess-1", json={"accounts": [{"uid": "u1"}, {"uid": "u2"}]})

    accounts = client.list_accounts("sess-1")

    assert accounts == [{"uid": "u1"}, {"uid": "u2"}]
    assert responses.calls[0].request.url == f"{API}/sessions/sess-1"


@responses.activate
def test_list_accounts_accepts_the_accounts_data_key(client):
    responses.get(f"{API}/sessions/sess-2", json={"accounts_data": [{"uid": "u3"}]})

    assert client.list_accounts("sess-2") == [{"uid": "u3"}]


@responses.activate
def test_list_accounts_skips_the_uid_strings_the_live_api_returns(client):
    responses.get(
        f"{API}/sessions/sess-3",
        json={"accounts": ["u1"], "accounts_data": [{"uid": "u1", "currency": "EUR"}]},
    )

    assert client.list_accounts("sess-3") == [{"uid": "u1", "currency": "EUR"}]


@responses.activate
def test_fetch_account_details_reads_the_details_endpoint(client):
    payload = {"account_id": {"iban": "IT60X0542811101000000123456"}}
    responses.get(f"{API}/accounts/acc-9/details", json=payload)

    assert client.fetch_account_details("acc-9") == payload
    assert responses.calls[0].request.url == f"{API}/accounts/acc-9/details"


@responses.activate
def test_fetch_balances_reads_the_balances_endpoint(client):
    payload = {"balances": [{"balance_amount": {"amount": "12.34", "currency": "EUR"}}]}
    responses.get(f"{API}/accounts/acc-9/balances", json=payload)

    assert client.fetch_balances("acc-9") == payload
    assert responses.calls[0].request.url == f"{API}/accounts/acc-9/balances"


@responses.activate
@pytest.mark.parametrize("status_code", [401, 403])
def test_consent_error_raised_on_rejected_credentials(client, status_code):
    responses.get(f"{API}/accounts/acc-9/balances", status=status_code)

    with pytest.raises(ConsentExpiredError):
        client.fetch_balances("acc-9")


@responses.activate
def test_fetch_transactions_raises_consent_error(client, monkeypatch):
    monkeypatch.setattr("amonhen.providers.enable_banking.time.sleep", lambda _s: None)
    responses.get(f"{API}/accounts/acc-9/transactions", status=403)

    with pytest.raises(ConsentExpiredError):
        client.fetch_transactions("acc-9", dt.date(2026, 1, 1), dt.date(2026, 1, 2))


@responses.activate
def test_fetch_transactions_paginates_repeating_the_window(client, monkeypatch):
    monkeypatch.setattr("amonhen.providers.enable_banking.time.sleep", lambda _s: None)
    url = f"{API}/accounts/acc-1/transactions"
    responses.get(url, json={"transactions": [{"id": 1}], "continuation_key": "next"})
    responses.get(url, json={"transactions": [{"id": 2}]})

    txns = client.fetch_transactions("acc-1", dt.date(2026, 1, 1), dt.date(2026, 1, 2))

    assert [t["id"] for t in txns] == [1, 2]
    first = parse_qs(urlparse(responses.calls[0].request.url).query)
    second = parse_qs(urlparse(responses.calls[1].request.url).query)
    assert first["date_from"] == ["2026-01-01"]
    assert first["date_to"] == ["2026-01-02"]
    assert "continuation_key" not in first
    assert second["date_from"] == first["date_from"]
    assert second["date_to"] == first["date_to"]
    assert second["continuation_key"] == ["next"]


@responses.activate
def test_fetch_transactions_splits_ranges_into_30_day_windows(client, monkeypatch):
    monkeypatch.setattr("amonhen.providers.enable_banking.time.sleep", lambda _s: None)
    url = f"{API}/accounts/acc-1/transactions"
    responses.get(url, json={"transactions": []})
    responses.get(url, json={"transactions": []})

    client.fetch_transactions("acc-1", dt.date(2026, 1, 1), dt.date(2026, 3, 1))

    first = parse_qs(urlparse(responses.calls[0].request.url).query)
    second = parse_qs(urlparse(responses.calls[1].request.url).query)
    assert (first["date_from"], first["date_to"]) == (["2026-01-01"], ["2026-01-30"])
    assert (second["date_from"], second["date_to"]) == (["2026-01-31"], ["2026-03-01"])
    assert len(responses.calls) == 2


@responses.activate
def test_rate_limit_is_retried(client, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("amonhen.providers.enable_banking.time.sleep", slept.append)
    responses.get(f"{API}/accounts/acc-9/balances", status=429)
    responses.get(f"{API}/accounts/acc-9/balances", json={"balances": []})

    assert client.fetch_balances("acc-9") == {"balances": []}
    assert slept and slept[0] > 0


@responses.activate
def test_list_banks_returns_the_aspsp_names(client):
    responses.get(f"{API}/aspsps", json={"aspsps": [
        {"name": "Revolut", "country": "IT"},
        {"name": "FinecoBank", "country": "IT"},
        {"country": "IT"},
    ]})

    banks = client.list_banks()

    assert banks == [{"name": "Revolut", "country": "IT"}, {"name": "FinecoBank", "country": "IT"}]
