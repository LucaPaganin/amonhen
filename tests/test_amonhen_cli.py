"""CLI end to end on a temporary ledger; no network, no real data."""
import datetime as dt
import hashlib
import json
from pathlib import Path

from amonhen.cli import main

# A configuration of its own: the default is the operator's `accounts.json`,
# which is not in version control.
MINIMAL_CONFIG = Path(__file__).resolve().parent / "fixtures" / "config" / "minimal.json"

ACTUAL_EXPORT = """Account,Date,Payee,Notes,Category_Group,Category,Amount,Split_Amount,Cleared
Revolut,2026-08-03,ACME Srl,CARD_PAYMENT | VISA 1234,Spese,Cibo,-3.94,0,Cleared
Revolut,2026-08-04,Trattoria Due,CARD_PAYMENT | VISA 5319,Spese,Ristoranti,-53.80,0,Cleared
Revolut,2026-08-05,Stipendio,Income,Income,Stipendio,1200.00,0,Cleared
"""


def run(db, *args) -> int:
    return main(["--db", str(db), "--config", str(MINIMAL_CONFIG), *args])


def make_export(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text(ACTUAL_EXPORT, encoding="utf-8")
    return path


def test_import_then_spend_excludes_incoming_money(tmp_path, capsys):
    export = make_export(tmp_path)
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Revolut", "--opening", "0.00", "--opening-date", "2026-08-01")
    run(db, "import", str(export), "--account", "Revolut", "--profile", "actual")
    capsys.readouterr()

    assert run(db, "spend", "--month", "2026-08") == 0

    out = capsys.readouterr().out
    assert "57.74" in out


def test_reimporting_the_export_changes_nothing(tmp_path, capsys):
    export = make_export(tmp_path)
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Revolut", "--opening", "0.00", "--opening-date", "2026-08-01")
    run(db, "import", str(export), "--account", "Revolut", "--profile", "actual")
    capsys.readouterr()

    assert run(db, "import", str(export), "--account", "Revolut", "--profile", "actual") == 0

    out = capsys.readouterr().out
    assert "duplicate=3" in out
    assert "inserted" not in out


def test_validate_passes_after_import(tmp_path, capsys):
    export = make_export(tmp_path)
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Revolut", "--opening", "0.00", "--opening-date", "2026-08-01")
    run(db, "import", str(export), "--account", "Revolut", "--profile", "actual")
    capsys.readouterr()

    assert run(db, "validate") == 0
    assert "balances" in capsys.readouterr().out


def test_balance_check_reports_a_mismatch(tmp_path, capsys):
    export = make_export(tmp_path)
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Revolut", "--opening", "0.00", "--opening-date", "2026-08-01")
    run(db, "import", str(export), "--account", "Revolut", "--profile", "actual")
    capsys.readouterr()

    exit_code = run(db, "balance-check", "--account", "Revolut", "--as-of", "2026-08-31",
                    "--declared", "1000.00")

    assert exit_code == 1
    assert "MISMATCH" in capsys.readouterr().err


def test_balance_check_passes_when_the_numbers_agree(tmp_path, capsys):
    export = make_export(tmp_path)
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Revolut", "--opening", "0.00", "--opening-date", "2026-08-01")
    run(db, "import", str(export), "--account", "Revolut", "--profile", "actual")
    capsys.readouterr()

    assert run(db, "balance-check", "--account", "Revolut", "--as-of", "2026-08-31",
               "--declared", "1142.26") == 0


def test_anchor_then_balance_check_agrees(tmp_path, capsys):
    export = make_export(tmp_path)
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Revolut", "--opening", "0.00", "--opening-date", "2026-08-01")
    run(db, "import", str(export), "--account", "Revolut", "--profile", "actual")
    capsys.readouterr()

    assert run(db, "anchor", "--account", "Revolut", "--as-of", "2026-08-31",
               "--declared", "1142.26") == 0
    capsys.readouterr()

    assert run(db, "balance-check", "--account", "Revolut", "--as-of", "2026-08-31") == 0
    out = capsys.readouterr().out
    assert "difference=0.00" in out


def test_anchoring_from_the_contabile_figure_leaves_the_pending_movements_out(tmp_path, capsys):
    """An opening derived from the booked balance must not swallow the pending sum."""
    from decimal import Decimal

    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger
    from amonhen.models import IncomingTransaction

    export = tmp_path / "export.csv"
    export.write_text(
        "Account,Date,Payee,Notes,Category_Group,Category,Amount,Split_Amount,Cleared\n"
        "Acct,2026-08-10,ACME Srl,Invoice,Spese,Servizi,-100.00,0,Cleared\n",
        encoding="utf-8",
    )
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Acct", "--opening", "0.00", "--opening-date", "2026-08-01")
    run(db, "import", str(export), "--account", "Acct", "--profile", "actual")
    conn = open_ledger_db(db)
    internal = Ledger(conn)
    # Something the bank has not settled: inside the available figure, outside the booked one.
    internal.record(IncomingTransaction(
        account_id=internal.find_account(name="Acct")["id"],
        date=dt.date(2026, 8, 20),
        amount=Decimal("-40.00"),
        description="CARD_PAYMENT | Pending",
        status="PDNG",
        source="import",
        balancing_account_id=internal.transfer_account(),
    ))
    conn.close()
    capsys.readouterr()

    # The bank's booked figure has the pending movement already left out.
    assert run(db, "anchor", "--account", "Acct", "--as-of", "2026-08-31",
               "--declared", "-100.00", "--kind", "booked") == 0
    assert "opening 0.00" in capsys.readouterr().out

    assert run(db, "balance-check", "--account", "Acct", "--as-of", "2026-08-31") == 0
    out = capsys.readouterr().out
    assert "difference=0.00" in out
    assert "kind=booked" in out

    # The pending movement is still counted where it belongs, and only there.
    assert run(db, "balance-check", "--account", "Acct", "--as-of", "2026-08-31",
               "--declared", "-140.00") == 0
    assert run(db, "balance-check", "--account", "Acct", "--as-of", "2026-08-31",
               "--declared", "-100.00") == 1


def test_balances_reports_expired_consent_and_continues(tmp_path, capsys, monkeypatch):
    from amonhen import cli
    from amonhen.config import ConfiguredAccount, MonitorConfig
    from amonhen.providers.enable_banking import ConsentExpiredError

    class FakeClient:
        def fetch_balances(self, uid):
            if uid == "dead":
                raise ConsentExpiredError("expired")
            return {"balances": [{"balance_type": "ITAV", "reference_date": "2026-08-31",
                                  "balance_amount": {"amount": "10.00", "currency": "EUR"}}]}

    config = MonitorConfig(
        application_id="app", pem_path=tmp_path / "private.pem", redirect_url="http://x",
        own_names=frozenset(),
        accounts=(
            ConfiguredAccount(name="Dead", institution="Fineco", session_id="s1", account_uid="dead"),
            ConfiguredAccount(name="Alive", institution="Revolut", session_id="s2", account_uid="ok"),
        ),
    )
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "build_client", lambda cfg: FakeClient())
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Dead")
    run(db, "account-add", "Alive")
    capsys.readouterr()

    exit_code = run(db, "balances")

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Dead: consent expired" in captured.err
    assert "Alive: 2026-08-31 ITAV 10.00 EUR" in captured.out


def test_anchor_and_check_use_the_declared_balances_date(tmp_path, capsys):
    """A declared balance dated earlier than --as-of must not shift the opening."""
    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger
    from decimal import Decimal

    export = tmp_path / "export.csv"
    export.write_text(
        "Account,Date,Payee,Notes,Category_Group,Category,Amount,Split_Amount,Cleared\n"
        "Acct,2026-08-10,ACME Srl,Invoice,Spese,Servizi,-100.00,0,Cleared\n"
        "Acct,2026-09-05,ACME Srl,Invoice,Spese,Servizi,-50.00,0,Cleared\n",
        encoding="utf-8",
    )
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Acct", "--opening", "0.00", "--opening-date", "2026-08-01")
    run(db, "import", str(export), "--account", "Acct", "--profile", "actual")
    conn = open_ledger_db(db)
    internal = Ledger(conn)
    internal.record_declared_balance(
        internal.find_account(name="Acct")["id"], dt.date(2026, 8, 31), Decimal("900.00"), "manual"
    )
    conn.close()
    capsys.readouterr()

    assert run(db, "anchor", "--account", "Acct", "--as-of", "2026-09-10") == 0

    out = capsys.readouterr().out
    assert "opening 1000.00" in out
    assert "2026-08-31" in out
    assert run(db, "balance-check", "--account", "Acct", "--as-of", "2026-09-10") == 0
    assert "2026-08-31" in capsys.readouterr().out


def test_identical_rows_in_one_export_are_both_kept(tmp_path, capsys):
    export = tmp_path / "export.csv"
    export.write_text(
        "Account,Date,Payee,Notes,Category_Group,Category,Amount,Split_Amount,Cleared\n"
        "Acct,2026-04-06,Trenitalia,Biglietto,Spese,Trasporti,-25.60,0,Cleared\n"
        "Acct,2026-04-06,Trenitalia,Biglietto,Spese,Trasporti,-25.60,0,Cleared\n",
        encoding="utf-8",
    )
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Acct")
    capsys.readouterr()

    assert run(db, "import", str(export), "--account", "Acct", "--profile", "actual") == 0
    assert "inserted=2" in capsys.readouterr().out
    assert run(db, "spend", "--month", "2026-04") == 0
    assert "51.20" in capsys.readouterr().out

    assert run(db, "import", str(export), "--account", "Acct", "--profile", "actual") == 0
    assert "duplicate=2" in capsys.readouterr().out


def test_unknown_profile_is_rejected(tmp_path):
    export = make_export(tmp_path)
    db = tmp_path / "ledger.db"

    try:
        run(db, "import", str(export), "--account", "Revolut", "--profile", "nope")
    except SystemExit as exc:
        assert "unknown profile" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_spend_defaults_to_last_month(tmp_path, capsys):
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Revolut")
    capsys.readouterr()

    assert run(db, "spend") == 0

    out = capsys.readouterr().out
    today = dt.date.today()
    first_of_this_month = today.replace(day=1)
    previous = first_of_this_month - dt.timedelta(days=1)
    assert f"{previous.year:04d}-{previous.month:02d}-01" in out


def test_backup_writes_a_snapshot_that_reads_back(tmp_path, capsys):
    """The snapshot is a ledger, not a file: every command works on it."""
    export = make_export(tmp_path)
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Revolut", "--opening", "0.00", "--opening-date", "2026-08-01")
    run(db, "import", str(export), "--account", "Revolut", "--profile", "actual")
    dest = tmp_path / "backups"
    capsys.readouterr()

    assert run(db, "backup", "--dest", str(dest)) == 0

    assert "3 movements" in capsys.readouterr().out
    snapshots = list(dest.iterdir())
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert (snapshot / "amonhen.db").is_file()
    assert (snapshot / "manifest.json").is_file()

    assert run(snapshot / "amonhen.db", "validate") == 0
    capsys.readouterr()
    assert run(snapshot / "amonhen.db", "accounts") == 0
    from_snapshot = capsys.readouterr().out
    assert run(db, "accounts") == 0
    assert from_snapshot == capsys.readouterr().out
    assert "Revolut" in from_snapshot


def test_backup_copies_the_configuration_and_hashes_what_it_wrote(tmp_path, capsys):
    """A ledger without the accounts.json that names its sessions is not restorable."""
    db = tmp_path / "ledger.db"
    run(db, "account-add", "Revolut")
    key = tmp_path / "private.pem"
    key.write_text("-----BEGIN PRIVATE KEY-----\nnot a real key\n", encoding="utf-8")
    config = tmp_path / "accounts.json"
    config.write_text(json.dumps({"pem_path": "private.pem", "accounts": []}), encoding="utf-8")
    dest = tmp_path / "backups"
    capsys.readouterr()

    # `run` puts the fixture configuration before the subcommand; this one is
    # passed where argparse reads it, in the global option group.
    assert main(["--db", str(db), "--config", str(config), "backup", "--dest", str(dest)]) == 0

    snapshot = next(dest.iterdir())
    assert (snapshot / "accounts.json").read_bytes() == config.read_bytes()
    assert (snapshot / "private.pem").read_bytes() == key.read_bytes()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["configuration"] == ["accounts.json", "private.pem"]
    assert manifest["accounts"] == 1
    written = (snapshot / "amonhen.db").read_bytes()
    assert manifest["db_sha256"] == hashlib.sha256(written).hexdigest()


def test_backup_keeps_the_newest_and_refuses_an_empty_ledger(tmp_path, capsys):
    import sqlite3

    from amonhen.backup import make_snapshot
    from amonhen.db import open_ledger_db

    db = tmp_path / "ledger.db"
    run(db, "account-add", "Revolut")
    capsys.readouterr()
    dest = tmp_path / "backups"
    ten_oh_one = dt.datetime(2026, 9, 26, 10, 1, tzinfo=dt.timezone.utc)

    conn = open_ledger_db(db)
    try:
        make_snapshot(conn, dest, now=dt.datetime(2026, 9, 26, 10, 0, tzinfo=dt.timezone.utc))
        newest = make_snapshot(conn, dest, keep=1, now=ten_oh_one)
        # keep=0 is what the default does not do: leave everything in place.
        keep_all = tmp_path / "keep-all"
        make_snapshot(conn, keep_all, now=dt.datetime(2026, 9, 26, 10, 0, tzinfo=dt.timezone.utc))
        make_snapshot(conn, keep_all, now=ten_oh_one)
        # A stamp older than one already in the folder must not cost the snapshot
        # just written: retention holds that folder back from the comparison.
        backwards = tmp_path / "backwards"
        make_snapshot(conn, backwards, now=ten_oh_one)
        older = make_snapshot(
            conn, backwards, keep=1, now=dt.datetime(2026, 9, 26, 10, 0, tzinfo=dt.timezone.utc)
        )
        # A run that dies halfway must leave no folder that looks like a
        # snapshot, and must not touch the ones already there.
        dead = open_ledger_db(db)
        dead.close()
        try:
            make_snapshot(dead, dest, now=dt.datetime(2026, 9, 26, 10, 2, tzinfo=dt.timezone.utc))
        except sqlite3.Error:
            pass
        else:
            raise AssertionError("expected a closed connection to fail the copy")
    finally:
        conn.close()

    assert [entry.name for entry in dest.iterdir()] == [newest.path.name]
    assert newest.created_at == "2026-09-26T10:01:00Z"
    assert older.path.is_dir()
    assert [entry.name for entry in backwards.iterdir()] == [older.path.name]
    assert sorted(entry.name for entry in keep_all.iterdir()) == [
        "2026-09-26T100000Z",
        "2026-09-26T100100Z",
    ]

    assert run(tmp_path / "empty.db", "backup", "--dest", str(tmp_path / "nowhere")) == 1
    assert "no accounts" in capsys.readouterr().err
    assert not (tmp_path / "nowhere").exists()


def test_sync_of_one_account_over_a_period(tmp_path, capsys, monkeypatch):
    from amonhen import cli
    from test_sync_service import FakeClient, build_config, fixture_transactions

    transactions = fixture_transactions(60)
    fake = FakeClient(transactions)
    monkeypatch.setattr(cli, "load_config", lambda path: build_config())
    monkeypatch.setattr(cli, "build_client", lambda cfg: fake)
    db = tmp_path / "ledger.db"
    args = ("sync", "--account", "Revolut personale", "--from", "2025-09-01", "--to", "2025-09-30")

    assert run(db, *args, "--preview") == 0
    preview = capsys.readouterr().out
    assert "2025-09-01..2025-09-30: fetched=" in preview
    assert "would be inserted=" in preview

    assert run(db, *args) == 0
    assert "written inserted=" in capsys.readouterr().out
    assert run(db, *args) == 0
    assert "written duplicate=" in capsys.readouterr().out


def test_sync_period_is_validated_before_the_bank(tmp_path, capsys, monkeypatch):
    from amonhen import cli
    from test_sync_service import FakeClient, build_config

    fake = FakeClient([])
    monkeypatch.setattr(cli, "load_config", lambda path: build_config())
    monkeypatch.setattr(cli, "build_client", lambda cfg: fake)
    db = tmp_path / "ledger.db"

    assert run(db, "sync", "--account", "Revolut personale", "--from", "2025-09-01") == 2
    assert "together" in capsys.readouterr().err
    assert run(db, "sync", "--account", "Revolut personale",
               "--from", "2025-09-30", "--to", "2025-09-01") == 2
    assert "after it ends" in capsys.readouterr().err
    assert run(db, "sync", "--account", "Nessuno", "--from", "2025-09-01", "--to", "2025-09-30") == 2
    assert "no account named" in capsys.readouterr().err
    assert fake.window_calls == []
