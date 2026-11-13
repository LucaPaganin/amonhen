"""A second bank behind the port: the CSV stub, from the adapter to the button.

The point of these tests is the measure in `docs/architettura.md`: the stub is
a new adapter and one branch in the composition root, and the sync, the routes
and the command line take it without a line changed.
"""
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from amonhen import settings
from amonhen.adapters.csv_bank import CsvBankProvider
from amonhen.api import create_app
from amonhen.cli import main
from amonhen.composition import bank_provider
from amonhen.config import ConfiguredAccount, MonitorConfig
from amonhen.db import connect
from amonhen.ledger import Ledger
from amonhen.ports.bank import BankProvider
from amonhen.sync import SyncService

FEED = (
    "date,amount,description,id\n"
    "2026-09-01,-12.30,Caffè,c-1\n"
    "2026-09-02,1500.00,Stipendio,c-2\n"
)
BALANCES = "date,amount,type\n2026-09-11,1487.70,ITBD\n"


def feed(directory: Path, uid: str = "conto-csv") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{uid}.csv").write_text(FEED, encoding="utf-8")
    (directory / f"{uid}.balances.csv").write_text(BALANCES, encoding="utf-8")
    return directory


def account() -> ConfiguredAccount:
    return ConfiguredAccount(
        name="Conto CSV", institution="Banca CSV", session_id="-", account_uid="conto-csv"
    )


def config() -> MonitorConfig:
    return MonitorConfig(
        application_id="",
        pem_path=Path("nowhere.pem"),
        redirect_url="",
        own_names=frozenset(),
        accounts=(account(),),
    )


def test_the_stub_implements_the_port():
    assert isinstance(CsvBankProvider("."), BankProvider)


def test_the_sync_writes_the_feed_and_its_balance(ledger, tmp_path):
    bank = CsvBankProvider(feed(tmp_path / "bank"))

    result = SyncService(ledger, bank, config(), today=dt.date(2026, 9, 12)).run()

    assert result.errors == []
    rows = ledger.conn.execute("SELECT description, amount, source FROM transactions ORDER BY date").fetchall()
    assert [tuple(row) for row in rows] == [("Caffè", "-12.30", "psd2"), ("Stipendio", "1500.00", "psd2")]
    conto = ledger.find_account(name="Conto CSV")["id"]
    assert [(row["source"], row["balance"]) for row in ledger.declarations(conto)] == [("eb:ITBD", "1487.70")]
    # The ledger's own check agrees with the feed's declared balance.
    assert result.accounts[0].balance_mismatch is None


def test_a_missing_file_is_the_account_s_failure_not_the_run_s(ledger, tmp_path):
    bank = CsvBankProvider(tmp_path / "empty")

    result = SyncService(ledger, bank, config(), today=dt.date(2026, 9, 12)).run()

    assert result.accounts[0].error.startswith("fetch failed: cannot read conto-csv.csv")


def test_the_composition_root_is_where_the_bank_is_chosen(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BANK_PROVIDER", "csv")
    monkeypatch.setattr(settings, "CSV_BANK_DIR", tmp_path)

    chosen = bank_provider(config())

    assert isinstance(chosen, CsvBankProvider)
    assert chosen.directory == tmp_path


def test_the_sync_button_and_the_command_line_take_the_stub_unchanged(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "BANK_PROVIDER", "csv")
    monkeypatch.setattr(settings, "CSV_BANK_DIR", feed(tmp_path / "bank"))
    accounts_json = tmp_path / "accounts.json"
    accounts_json.write_text(
        json.dumps({
            "application_id": "",
            "pem_path": "nowhere.pem",
            "redirect_url": "http://localhost:8000/callback",
            "accounts": [{"session_id": "-", "account_uid": "conto-csv", "bank_name": "Banca CSV",
                          "notes": "Conto CSV"}],
        }),
        encoding="utf-8",
    )

    # The button: no override, no fake, no key on disk.
    app = create_app(tmp_path / "api.db", web_dist=tmp_path / "missing", config_path=accounts_json)
    response = TestClient(app).post("/api/sync")
    assert response.status_code == 200
    assert [a["account"] for a in response.json()["accounts"]] == ["Conto CSV"]

    # The command line, on a ledger of its own.
    assert main(["--db", str(tmp_path / "cli.db"), "--config", str(accounts_json), "sync"]) == 0
    assert "Conto CSV: fetched=2" in capsys.readouterr().out
    conn = connect(tmp_path / "cli.db")
    total = Ledger(conn).balance(
        Ledger(conn).find_account(name="Conto CSV")["id"], dt.date(2026, 9, 30)
    )
    conn.close()
    assert total == Decimal("1487.70")
