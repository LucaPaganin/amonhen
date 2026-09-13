"""The consent flow: /connect redirects, /callback stores the authorized session.

Desiderata section 7 keeps this in the application rather than in the client
module, so both routes are exercised over the real HTTP surface against a
stubbed Enable Banking.
"""
import json
from pathlib import Path

import responses as responses_lib
from fastapi.testclient import TestClient

import amonhen.providers.enable_banking as provider
from amonhen.api import create_app
from amonhen.db import open_ledger_db
from amonhen.ledger import Ledger

API = "https://api.enablebanking.test"


def make_config(tmp_path: Path, pem_path: Path, accounts: tuple[dict, ...] = ()) -> Path:
    (tmp_path / "private.pem").write_bytes(pem_path.read_bytes())
    config = tmp_path / "accounts.json"
    config.write_text(
        json.dumps(
            {
                "application_id": "app-1",
                "pem_path": "private.pem",
                "redirect_url": "http://localhost:8000/callback",
                "account_holder_name": "Tester",
                "accounts": list(accounts),
            }
        ),
        encoding="utf-8",
    )
    return config


def make_client(tmp_path: Path, config: Path) -> TestClient:
    return TestClient(
        create_app(tmp_path / "ledger.db", web_dist=tmp_path / "missing", config_path=config)
    )


def pending_state(tmp_path: Path) -> str:
    conn = open_ledger_db(tmp_path / "ledger.db")
    try:
        return json.loads(Ledger(conn).setting("pending_oauth"))["state"]
    finally:
        conn.close()


@responses_lib.activate
def test_connect_redirects_and_callback_stores_the_session(tmp_path, rsa_pem, monkeypatch):
    pem_path, _ = rsa_pem
    monkeypatch.setattr(provider, "EB_API", API)
    config = make_config(tmp_path, pem_path)
    client = make_client(tmp_path, config)
    responses_lib.post(f"{API}/auth", json={"url": "https://bank.example/authorize?x=1"})

    started = client.get(
        "/connect", params={"bank": "Revolut", "country": "IT"}, follow_redirects=False
    )

    assert started.status_code == 302
    assert started.headers["location"] == "https://bank.example/authorize?x=1"
    state = pending_state(tmp_path)

    responses_lib.post(
        f"{API}/sessions",
        json={
            "session_id": "sess-1",
            "accounts_data": [{"uid": "uid-1", "name": "Revolut personale", "currency": "EUR"}],
        },
    )
    done = client.get("/callback", params={"code": "code-1", "state": state})

    assert done.status_code == 200
    assert done.json()["session_id"] == "sess-1"
    assert done.json()["accounts"] == ["uid-1"]
    assert done.json()["written"] == [{"account": "Revolut personale", "action": "added"}]
    saved = json.loads(config.read_text(encoding="utf-8"))
    assert len(saved["accounts"]) == 1
    entry = saved["accounts"][0]
    assert entry["session_id"] == "sess-1"
    assert entry["account_uid"] == "uid-1"
    assert entry["bank_name"] == "Revolut"
    assert entry["notes"] == "Revolut personale"
    assert entry["start_sync_date"]
    # The pending state is consumed, so a replay cannot re-open a session.
    conn = open_ledger_db(tmp_path / "ledger.db")
    assert Ledger(conn).setting("pending_oauth") == ""
    conn.close()
    # The credentials are untouched.
    assert saved["application_id"] == "app-1"


@responses_lib.activate
def test_a_second_authorization_refreshes_the_entry_instead_of_appending(
    tmp_path, rsa_pem, monkeypatch
):
    """Renewing an expired consent restarts the session, not the account.

    The session id changes at every authorization while the account uid does
    not, and the ledger knows an account by the name in `notes`: a second entry
    would be a second account with the history imported into it again.
    """
    pem_path, _ = rsa_pem
    monkeypatch.setattr(provider, "EB_API", API)
    config = make_config(
        tmp_path,
        pem_path,
        accounts=(
            {
                "session_id": "sess-old",
                "account_uid": "uid-1",
                "bank_name": "Revolut",
                "country": "IT",
                "notes": "Revolut personale",
                "start_sync_date": "2026-01-01",
            },
        ),
    )
    client = make_client(tmp_path, config)
    responses_lib.post(f"{API}/auth", json={"url": "https://bank.example/authorize?x=1"})

    started = client.get(
        "/connect", params={"bank": "Revolut", "country": "IT"}, follow_redirects=False
    )

    assert started.status_code == 302
    state = pending_state(tmp_path)

    responses_lib.post(
        f"{API}/sessions",
        json={
            "session_id": "sess-new",
            "accounts_data": [{"uid": "uid-1", "name": "Nadia Verdi", "currency": "EUR"}],
        },
    )
    done = client.get("/callback", params={"code": "code-2", "state": state})

    saved = json.loads(config.read_text(encoding="utf-8"))
    assert done.json()["written"] == [{"account": "Revolut personale", "action": "refreshed"}]
    assert len(saved["accounts"]) == 1
    entry = saved["accounts"][0]
    assert entry["session_id"] == "sess-new"
    assert entry["notes"] == "Revolut personale"
    assert entry["start_sync_date"] == "2026-01-01"
    assert entry["session_expiry"]


@responses_lib.activate
def test_callback_without_a_started_authorization_is_refused(tmp_path, rsa_pem, monkeypatch):
    pem_path, _ = rsa_pem
    monkeypatch.setattr(provider, "EB_API", API)
    client = make_client(tmp_path, make_config(tmp_path, pem_path))

    response = client.get("/callback", params={"code": "c", "state": "whatever"})

    assert response.status_code == 400
    assert "no authorization" in response.json()["detail"]


@responses_lib.activate
def test_callback_with_a_mismatched_state_is_refused(tmp_path, rsa_pem, monkeypatch):
    pem_path, _ = rsa_pem
    monkeypatch.setattr(provider, "EB_API", API)
    config = make_config(tmp_path, pem_path)
    client = make_client(tmp_path, config)
    responses_lib.post(f"{API}/auth", json={"url": "https://bank.example/authorize?x=1"})
    client.get("/connect", params={"bank": "Revolut", "country": "IT"}, follow_redirects=False)

    response = client.get("/callback", params={"code": "c", "state": "not-the-state"})

    assert response.status_code == 400
    assert "does not match" in response.json()["detail"]
    assert json.loads(config.read_text(encoding="utf-8"))["accounts"] == []


@responses_lib.activate
def test_a_bank_name_the_provider_rejects_is_reported_as_an_upstream_failure(
    tmp_path, rsa_pem, monkeypatch
):
    pem_path, _ = rsa_pem
    monkeypatch.setattr(provider, "EB_API", API)
    client = make_client(tmp_path, make_config(tmp_path, pem_path))
    responses_lib.post(f"{API}/auth", status=400, json={"message": "Unknown ASPSP"})

    response = client.get("/connect", params={"bank": "Nope", "country": "IT"})

    assert response.status_code == 502
    assert "Unknown ASPSP" in response.json()["detail"]
