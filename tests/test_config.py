"""accounts.json: the keys the monitoring system reads, and their defaults."""
import json

import pytest

from amonhen.config import load_config, save_account


def write_config(tmp_path, **overrides):
    data = {
        "application_id": "app",
        "pem_path": "./private.pem",
        "redirect_url": "http://localhost:8000/callback",
        "account_holder_name": "Nadia Verdi, Ivan Marroni",
        "accounts": [
            {
                "session_id": "s1",
                "account_uid": "u1",
                "bank_name": "Revolut",
                "notes": "Revolut personale",
            }
        ],
    }
    data.update(overrides)
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_the_config_reads_the_declared_destinations(tmp_path):
    path = write_config(
        tmp_path,
        passthrough=[
            {
                "destination": "Conto deposito senza vincoli",
                "labels": ["Conto deposito senza vincoli"],
            },
            {
                "destination": "Rimborsi e quote",
                "labels": ["Chiara Bianchi", "Assicurazioni"],
                "incoming_only": True,
            },
        ],
    )

    config = load_config(path)

    assert [(entry.destination, entry.labels, entry.incoming_only) for entry in config.passthrough] == [
        ("Conto deposito senza vincoli", ("Conto deposito senza vincoli",), False),
        ("Rimborsi e quote", ("Chiara Bianchi", "Assicurazioni"), True),
    ]


def test_a_declaration_that_says_nothing_is_refused_instead_of_skipped(tmp_path):
    """A declaration dropped in silence is money that stays in the burn."""
    assert load_config(write_config(tmp_path)).passthrough == ()
    assert load_config(write_config(tmp_path, passthrough=[])).passthrough == ()

    for broken, message in [
        ({"destination": "Rimborsi"}, "must be a list"),
        (["Rimborsi"], "not an object"),
        ([{"labels": ["X"]}], "without a destination"),
        ([{"destination": "X"}], "declares no label"),
        ([{"destination": "X", "labels": ["  "]}], "declares no label"),
        ([{"destination": "X", "labels": ["Y"], "incoming_only": "sì"}], "incoming_only"),
    ]:
        with pytest.raises(ValueError, match=message):
            load_config(write_config(tmp_path, passthrough=broken))


def test_the_pem_path_is_resolved_next_to_the_config(tmp_path):
    config = load_config(write_config(tmp_path))

    # Relative in the file, absolute here: the same accounts.json works in the
    # checkout and behind the container's /config mount.
    assert config.pem_path == tmp_path / "private.pem"


def test_the_account_holder_names_are_lowercased_and_split(tmp_path):
    config = load_config(write_config(tmp_path))

    assert config.own_names == frozenset({"nadia verdi", "ivan marroni"})
    assert config.accounts[0].name == "Revolut personale"


def test_a_renewed_session_refreshes_the_account_it_already_has(tmp_path):
    """The account uid survives a re-authorization; the session does not."""
    path = write_config(
        tmp_path,
        accounts=[
            {
                "session_id": "s1",
                "account_uid": "u1",
                "bank_name": "Revolut",
                "notes": "Revolut personale",
                "start_sync_date": "2026-03-01",
                "skip_pending": True,
            }
        ],
    )

    action, name = save_account(
        path,
        {
            "session_id": "s2",
            "account_uid": "u1",
            "bank_name": "Revolut",
            "country": "IT",
            "notes": "Nadia Verdi",
            "start_sync_date": "2026-09-13",
            "session_expiry": "2027-03-12",
        },
    )

    accounts = json.loads(path.read_text(encoding="utf-8"))["accounts"]
    assert (action, name) == ("refreshed", "Revolut personale")
    assert len(accounts) == 1
    entry = accounts[0]
    assert (entry["session_id"], entry["session_expiry"]) == ("s2", "2027-03-12")
    # The name the ledger knows the account by, the history it already imported
    # and the keys a person set by hand.
    assert entry["notes"] == "Revolut personale"
    assert entry["start_sync_date"] == "2026-03-01"
    assert entry["skip_pending"] is True
    # And the reader still sees one account, under the name it had.
    assert [account.name for account in load_config(path).accounts] == ["Revolut personale"]


def test_an_account_that_was_never_connected_is_added(tmp_path):
    path = write_config(tmp_path)

    action, name = save_account(
        path,
        {
            "session_id": "s2",
            "account_uid": "u9",
            "bank_name": "FinecoBank",
            "country": "IT",
            "notes": "FinecoBank",
            "start_sync_date": "2026-09-13",
        },
    )

    accounts = json.loads(path.read_text(encoding="utf-8"))["accounts"]
    assert (action, name) == ("added", "FinecoBank")
    assert [entry["account_uid"] for entry in accounts] == ["u1", "u9"]


def test_the_same_authorization_twice_leaves_one_entry(tmp_path):
    path = write_config(tmp_path)

    action, _ = save_account(
        path,
        {
            "session_id": "s1",
            "account_uid": "u1",
            "bank_name": "Revolut",
            "notes": "Revolut personale",
        },
    )

    accounts = json.loads(path.read_text(encoding="utf-8"))["accounts"]
    assert action == "refreshed"
    assert len(accounts) == 1
