"""The first-setup surface: a fresh install writes its own configuration.

The screen starts before `accounts.json` exists, so these tests cover the states
a person actually meets: no file at all, a key that is not a key, an address the
bank would refuse, an account named after another one.
"""
import json
from pathlib import Path

import responses as responses_lib
from fastapi.testclient import TestClient

import amonhen.providers.enable_banking as provider
from amonhen.api import create_app
from amonhen.config import load_config
from amonhen.db import open_ledger_db
from amonhen.ledger import Ledger
from amonhen.models import Account

API = "https://api.enablebanking.test"

REDIRECT = "https://amonhen.example.ts.net/callback"


def make_client(tmp_path: Path) -> TestClient:
    """An app whose configuration file does not exist yet."""
    return TestClient(
        create_app(
            tmp_path / "ledger.db",
            web_dist=tmp_path / "missing",
            config_path=tmp_path / "accounts.json",
        )
    )


def account_entry(uid: str, name: str, start: str = "2026-01-01") -> dict:
    return {
        "session_id": "sess-1",
        "account_uid": uid,
        "bank_name": "Revolut",
        "country": "IT",
        "notes": name,
        "start_sync_date": start,
        "session_expiry": "2027-01-01T00:00:00Z",
    }


def test_a_fresh_install_says_what_is_missing_instead_of_failing(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/setup")

    assert response.status_code == 200
    state = response.json()
    assert state["configured"] is False
    assert state["missing"] == ["application_id", "private_key", "accounts"]
    assert state["accounts"] == []
    assert state["key_loads"] is False
    assert state["last_connect"] is None


def test_the_credentials_are_written_and_the_configuration_reads_back(tmp_path, rsa_pem):
    pem_path, _ = rsa_pem
    client = make_client(tmp_path)

    response = client.put(
        "/api/setup/credentials",
        json={
            "application_id": "app-1",
            "redirect_url": REDIRECT,
            "account_holder_name": "Luca Paganin",
            "private_key": pem_path.read_text(encoding="utf-8"),
        },
    )

    assert response.status_code == 200
    assert response.json()["missing"] == ["accounts"]
    assert response.json()["key_loads"] is True

    # What the sync will read is the file the screen just wrote.
    config = load_config(tmp_path / "accounts.json")
    assert config.application_id == "app-1"
    assert config.redirect_url == REDIRECT
    assert config.own_names == frozenset({"luca paganin"})
    assert config.pem_path == tmp_path / "private.pem"
    assert config.pem_path.is_file()


def test_a_key_that_is_not_a_private_key_is_refused_where_it_is_typed(tmp_path):
    client = make_client(tmp_path)

    response = client.put(
        "/api/setup/credentials",
        json={
            "application_id": "app-1",
            "redirect_url": REDIRECT,
            "private_key": "-----BEGIN CERTIFICATE-----\nnope\n-----END CERTIFICATE-----\n",
        },
    )

    assert response.status_code == 422
    assert "private key" in response.json()["detail"]
    assert not (tmp_path / "private.pem").exists()
    # Nothing else was written either: a refused step leaves the file as it was.
    assert not (tmp_path / "accounts.json").exists()


def test_an_address_the_bank_could_not_use_is_refused(tmp_path):
    client = make_client(tmp_path)

    for address in (
        "https://amonhen.example.ts.net/",
        "amonhen.example.ts.net/callback",
        "ftp://x/callback",
        # Enable Banking registers https only, so an http address on a name is a
        # configuration that cannot work, not one to find out about at connect.
        "http://amonhen.example.ts.net/callback",
    ):
        response = client.put(
            "/api/setup/credentials",
            json={"application_id": "app-1", "redirect_url": address},
        )
        assert response.status_code == 422, address

    assert "callback" in client.put(
        "/api/setup/credentials",
        json={"application_id": "app-1", "redirect_url": "https://a.example/"},
    ).json()["detail"]

    assert "https" in client.put(
        "/api/setup/credentials",
        json={"application_id": "app-1", "redirect_url": "http://a.example/callback"},
    ).json()["detail"]

    # http survives on localhost alone: the rehearsal against the stub bank is
    # served by this machine and has no certificate to offer.
    assert (
        client.put(
            "/api/setup/credentials",
            json={"application_id": "app-1", "redirect_url": "http://localhost:8000/callback"},
        ).status_code
        == 200
    )


def test_the_private_key_never_comes_back_from_the_server(tmp_path, rsa_pem):
    pem_path, _ = rsa_pem
    client = make_client(tmp_path)
    client.put(
        "/api/setup/credentials",
        json={
            "application_id": "app-1",
            "redirect_url": REDIRECT,
            "private_key": pem_path.read_text(encoding="utf-8"),
        },
    )

    answer = client.get("/api/setup")

    assert "PRIVATE KEY" not in answer.text
    assert "private_key" not in answer.json()


def test_a_configured_account_is_renamed_and_dated(tmp_path):
    client = make_client(tmp_path)
    write_accounts(tmp_path, [account_entry("uid-1", "Revolut personale")])

    response = client.patch(
        "/api/setup/accounts/uid-1",
        json={"name": "Revolut mio", "start_sync_date": "2026-03-01"},
    )

    assert response.status_code == 200
    assert response.json()["accounts"] == [
        {
            "account_uid": "uid-1",
            "name": "Revolut mio",
            "institution": "Revolut",
            "country": "IT",
            "start_sync_date": "2026-03-01",
            "session_expiry": "2027-01-01T00:00:00Z",
        }
    ]
    assert load_config(tmp_path / "accounts.json").accounts[0].name == "Revolut mio"


def test_a_name_another_account_already_uses_is_refused(tmp_path):
    """Two entries under one name are one ledger account, and a second history."""
    client = make_client(tmp_path)
    write_accounts(
        tmp_path,
        [account_entry("uid-1", "Revolut personale"), account_entry("uid-2", "Fineco")],
    )

    response = client.patch("/api/setup/accounts/uid-2", json={"name": "Revolut personale"})

    assert response.status_code == 422
    assert "already called" in response.json()["detail"]
    assert load_config(tmp_path / "accounts.json").accounts[1].name == "Fineco"


def test_removing_a_configured_account_leaves_the_ledger_alone(tmp_path):
    client = make_client(tmp_path)
    write_accounts(
        tmp_path,
        [account_entry("uid-1", "Revolut personale"), account_entry("uid-2", "Fineco")],
    )
    conn = open_ledger_db(tmp_path / "ledger.db")
    ledger = Ledger(conn)
    ledger.ensure_account(Account(name="Fineco", type="real"))
    conn.close()

    response = client.delete("/api/setup/accounts/uid-2")

    assert response.status_code == 200
    assert [entry["account_uid"] for entry in response.json()["accounts"]] == ["uid-1"]
    assert [entry.name for entry in load_config(tmp_path / "accounts.json").accounts] == [
        "Revolut personale"
    ]
    # The sync stops asking for the account; what the ledger holds stays.
    conn = open_ledger_db(tmp_path / "ledger.db")
    assert Ledger(conn).find_account(name="Fineco") is not None
    conn.close()


def test_saving_the_credentials_again_keeps_the_key_that_is_already_there(tmp_path, rsa_pem):
    """The step sends the key only when the textarea has one.

    A person who comes back to change the holder's name, or the address, must
    not lose the key that is already on disk.
    """
    pem_path, _ = rsa_pem
    client = make_client(tmp_path)
    first = client.put(
        "/api/setup/credentials",
        json={
            "application_id": "app-1",
            "redirect_url": REDIRECT,
            "private_key": pem_path.read_text(encoding="utf-8"),
        },
    ).json()

    answer = client.put(
        "/api/setup/credentials",
        json={
            "application_id": "app-1",
            "redirect_url": REDIRECT,
            "account_holder_name": "Luca Paganin",
        },
    ).json()

    assert answer["key_loads"] is True
    assert answer["pem_path"] == first["pem_path"]
    assert answer["account_holder_name"] == "Luca Paganin"


def test_a_row_whose_account_is_gone_is_refused_and_changes_nothing(tmp_path):
    """A page left open while the entry was dropped elsewhere still saves nothing."""
    client = make_client(tmp_path)
    write_accounts(tmp_path, [account_entry("uid-1", "Revolut personale")])
    before = (tmp_path / "accounts.json").read_text(encoding="utf-8")

    rename = client.patch("/api/setup/accounts/uid-gone", json={"name": "Altro nome"})
    remove = client.delete("/api/setup/accounts/uid-gone")

    assert rename.status_code == 404
    assert remove.status_code == 404
    assert (tmp_path / "accounts.json").read_text(encoding="utf-8") == before


def test_a_body_without_a_required_field_does_not_echo_what_it_carried(tmp_path):
    """Pydantic's own answer repeats the body, and one of these bodies is a key.

    The response is what the client shows the person, so it names the field that
    is missing and nothing else.
    """
    client = make_client(tmp_path)
    secret = "-----BEGIN PRIVATE KEY-----SECRETMATERIAL-----END PRIVATE KEY-----"

    response = client.put(
        "/api/setup/credentials",
        json={"redirect_url": REDIRECT, "private_key": secret},
    )

    assert response.status_code == 422
    assert "application_id" in response.json()["detail"]
    assert "SECRETMATERIAL" not in response.text


@responses_lib.activate
def test_the_banks_of_a_country_are_listed_by_their_exact_names(tmp_path, rsa_pem, monkeypatch):
    pem_path, _ = rsa_pem
    monkeypatch.setattr(provider, "EB_API", API)
    client = make_client(tmp_path)
    client.put(
        "/api/setup/credentials",
        json={
            "application_id": "app-1",
            "redirect_url": REDIRECT,
            "private_key": pem_path.read_text(encoding="utf-8"),
        },
    )
    responses_lib.get(
        f"{API}/aspsps",
        json={
            "aspsps": [
                {"name": "Revolut", "country": "IT"},
                {"name": "FinecoBank", "country": "IT"},
                {"name": "Banca Sella", "country": "IT"},
                {"name": "Commerzbank", "country": "DE"},
                {"name": None, "country": "IT"},
            ]
        },
    )

    answer = client.get("/api/setup/banks", params={"country": "IT"}).json()

    assert answer["country"] == "IT"
    assert [bank["name"] for bank in answer["banks"]] == ["Banca Sella", "FinecoBank", "Revolut"]


@responses_lib.activate
def test_credentials_the_provider_refuses_are_reported_as_such(tmp_path, rsa_pem, monkeypatch):
    """A key that does not match the application ID is the bank's answer.

    Enable Banking reports it as 401/403, which the client raises as
    `ConsentExpiredError` rather than an HTTPError: the screen must read the
    refusal, not a 500.
    """
    pem_path, _ = rsa_pem
    monkeypatch.setattr(provider, "EB_API", API)
    client = make_client(tmp_path)
    client.put(
        "/api/setup/credentials",
        json={
            "application_id": "app-1",
            "redirect_url": REDIRECT,
            "private_key": pem_path.read_text(encoding="utf-8"),
        },
    )
    responses_lib.get(f"{API}/aspsps", status=403, json={"message": "Application does not exist"})

    answer = client.get("/api/setup/banks", params={"country": "IT"})

    assert answer.status_code == 502
    assert "Application does not exist" in answer.json()["detail"]


@responses_lib.activate
def test_the_setup_asks_for_the_authorization_url_instead_of_redirecting(
    tmp_path, rsa_pem, monkeypatch
):
    """The screen asks for the authorization URL and keeps the wizard open.

    The browser is sent to the bank in the same tab, because the callback has to
    come back to the app; the route answers the URL instead of a redirect so the
    step that asked for it is the one that decides what happens next.
    """
    pem_path, _ = rsa_pem
    monkeypatch.setattr(provider, "EB_API", API)
    client = make_client(tmp_path)
    client.put(
        "/api/setup/credentials",
        json={
            "application_id": "app-1",
            "redirect_url": REDIRECT,
            "private_key": pem_path.read_text(encoding="utf-8"),
        },
    )
    responses_lib.post(f"{API}/auth", json={"url": "https://bank.example/authorize?x=1"})

    response = client.post("/api/setup/connect", json={"bank": "FinecoBank", "country": "IT"})

    assert response.status_code == 200
    assert response.json() == {"url": "https://bank.example/authorize?x=1"}
    conn = open_ledger_db(tmp_path / "ledger.db")
    pending = json.loads(Ledger(conn).setting("pending_oauth"))
    conn.close()
    assert pending["bank"] == "FinecoBank"


@responses_lib.activate
def test_a_refused_redirect_says_which_address_was_sent(tmp_path, rsa_pem, monkeypatch):
    """Enable Banking compares the redirect URL with the application's list.

    Only one half of that comparison is on this machine — the registered URLs
    live in its control panel — so the refusal has to name the address that was
    sent, which is the half the person can change here.
    """
    pem_path, _ = rsa_pem
    monkeypatch.setattr(provider, "EB_API", API)
    client = make_client(tmp_path)
    client.put(
        "/api/setup/credentials",
        json={
            "application_id": "app-1",
            "redirect_url": REDIRECT,
            "private_key": pem_path.read_text(encoding="utf-8"),
        },
    )
    responses_lib.post(
        f"{API}/auth",
        status=400,
        json={
            "code": 400,
            "message": "Redirect URI not allowed",
            "error": "REDIRECT_URI_NOT_ALLOWED",
            "detail": None,
        },
    )

    response = client.post("/api/setup/connect", json={"bank": "FinecoBank", "country": "IT"})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Enable Banking refused the request: 400 Redirect URI not allowed" in detail
    assert REDIRECT in detail
    assert "accounts.json" in detail


def write_accounts(tmp_path: Path, entries: list[dict]) -> None:
    (tmp_path / "private.pem").write_bytes(b"not read by these tests")
    (tmp_path / "accounts.json").write_text(
        json.dumps(
            {
                "application_id": "app-1",
                "pem_path": "private.pem",
                "redirect_url": REDIRECT,
                "account_holder_name": "Luca Paganin",
                "accounts": entries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_renaming_a_connected_account_renames_the_one_in_the_ledger(tmp_path):
    """The first name used to stay for good: the ledger looked the account up by it."""
    client = make_client(tmp_path)
    write_accounts(
        tmp_path,
        [account_entry("uid-1", "FinecoBank"), account_entry("uid-2", "FinecoBank 2")],
    )
    conn = open_ledger_db(tmp_path / "ledger.db")
    ledger = Ledger(conn)
    first = ledger.ensure_account(Account(name="FinecoBank", type="real", external_uid="uid-1"))
    ledger.ensure_account(Account(name="FinecoBank 2", type="real", external_uid="uid-2"))
    conn.close()

    renamed = client.patch("/api/setup/accounts/uid-1", json={"name": "Fineco EUR"})
    clash = client.patch("/api/setup/accounts/uid-2", json={"name": "Fineco EUR"})

    assert renamed.status_code == 200
    assert clash.status_code == 422
    conn = open_ledger_db(tmp_path / "ledger.db")
    names = dict(conn.execute("SELECT external_uid, name FROM accounts WHERE type = 'real'").fetchall())
    conn.close()
    assert names == {"uid-1": "Fineco EUR", "uid-2": "FinecoBank 2"}
    assert load_config(tmp_path / "accounts.json").accounts[1].name == "FinecoBank 2"
    assert first
