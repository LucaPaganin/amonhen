"""The steps after a write of movements are the same whatever path wrote them.

A transfer rule runs before the pairing (`docs/transfers.md`): a leg the matcher
paired is no rule's to move, so an equal amount on another account would take a
transfer a person named. The sync always did this; the import and a held
movement written by hand paired first, and these tests are the divergence.
"""
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from amonhen.api import create_app
from amonhen.cli import main
from amonhen.db import connect, initialize
from amonhen.ledger import Ledger
from amonhen.merchants import RuleBook
from amonhen.models import Account, IncomingTransaction
from amonhen.services.ingest import settle_after_ingest

MINIMAL_CONFIG = Path(__file__).resolve().parent / "fixtures" / "config" / "minimal.json"

DAY = "2025-09-22"
RULE_TEXT = "conto deposito"


def incoming(ledger, account_id, amount, description, *, source="psd2", external_id=None):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(DAY),
        amount=Decimal(amount),
        description=description,
        status="BOOK",
        source=source,
        balancing_account_id=ledger.uncategorized(),
        external_id=external_id,
        raw={},
    )


def accounts(ledger) -> tuple[int, int, int]:
    """Fineco, where the transfer leaves; Revolut, where an unrelated equal credit
    lands the same day; and the deposit added by hand, which the rule names."""
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    deposit = ledger.ensure_account(Account(name="Deposito", type="real"))
    RuleBook(ledger.conn).set_rule(RULE_TEXT, "Deposito", ledger, action="transfer")
    return fineco, revolut, deposit


def other_leg_account(ledger, transaction_id: int) -> tuple[str, str] | None:
    """The account on the other side of the leg's pair, and how it was paired."""
    link = ledger.transfer_link(transaction_id)
    if link is None:
        return None
    other = link["leg_b"] if link["leg_a"] == transaction_id else link["leg_a"]
    name = ledger.conn.execute(
        "SELECT a.name FROM transactions t JOIN accounts a ON a.id = t.account_id WHERE t.id = ?",
        (other,),
    ).fetchone()[0]
    return name, link["method"]


def leg_id(ledger, description: str) -> int:
    return ledger.conn.execute(
        "SELECT id FROM transactions WHERE description = ?", (description,)
    ).fetchone()[0]


def test_the_transfer_rule_runs_before_the_pairing(ledger):
    fineco, revolut, _ = accounts(ledger)
    ledger.record_batch([
        incoming(ledger, fineco, "-250.00", "Giroconto conto deposito", source="import"),
        incoming(ledger, revolut, "250.00", "Bonifico da Mario", external_id="r-1"),
    ])

    settled = settle_after_ingest(ledger, ())

    leg = leg_id(ledger, "Giroconto conto deposito")
    assert other_leg_account(ledger, leg) == ("Deposito", "rule")
    credit = leg_id(ledger, "Bonifico da Mario")
    assert ledger.transfer_link(credit) is None
    assert ledger.category_of(credit) == "Uncategorized"
    assert settled.transfer_rules == 1
    assert settled.linked == 0


@pytest.fixture
def api(tmp_path):
    db_path = tmp_path / "ledger.db"
    client = TestClient(
        create_app(db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG)
    )
    yield client, db_path
    client.close()


def test_an_imported_transfer_goes_where_the_rule_says(api):
    client, db_path = api
    conn = connect(db_path)
    ledger = Ledger(conn)
    _, revolut, _ = accounts(ledger)
    ledger.record(incoming(ledger, revolut, "250.00", "Bonifico da Mario", external_id="r-1"))
    conn.close()

    response = client.post(
        "/api/import/csv",
        json={
            "content": f"Data;Dare;Avere;Descrizione\n22/09/2025;250,00;;Giroconto {RULE_TEXT}\n",
            "account": "Fineco",
            "mapping": {
                "delimiter": ";",
                "skip_rows": 0,
                "date_column": "Data",
                "date_format": "%d/%m/%Y",
                "amount_column": "",
                "debit_column": "Dare",
                "credit_column": "Avere",
                "decimal_separator": ",",
                "description_columns": ["Descrizione"],
                "external_id_column": "",
                "invert_sign": False,
            },
        },
    )

    assert response.status_code == 200
    conn = connect(db_path)
    ledger = Ledger(conn)
    assert other_leg_account(ledger, leg_id(ledger, f"Giroconto {RULE_TEXT}")) == ("Deposito", "rule")
    assert ledger.transfer_link(leg_id(ledger, "Bonifico da Mario")) is None
    conn.close()


def test_a_held_movement_written_by_hand_goes_where_the_rule_says(api):
    client, db_path = api
    conn = connect(db_path)
    ledger = Ledger(conn)
    fineco, revolut, _ = accounts(ledger)
    # The export wrote the movement under its own words; the bank's wording of
    # the same day and amount is held as a probable duplicate. Two equal credits
    # on Revolut, so the export's row and the held one each have one to pair with.
    ledger.record_batch([
        incoming(ledger, fineco, "-250.00", "Bonifico in uscita", source="import"),
        incoming(ledger, revolut, "250.00", "Bonifico da Mario", external_id="r-1"),
        incoming(ledger, revolut, "250.00", "Bonifico da Anna", external_id="r-2"),
    ])
    ledger.record_batch(
        [incoming(ledger, fineco, "-250.00", f"To {RULE_TEXT}", external_id="f-1")],
        hold_probable=True,
    )
    held = ledger.held_transactions(fineco)
    assert len(held) == 1
    conn.close()

    response = client.post(f"/api/sync/held/{held[0]['id']}/write")

    assert response.status_code == 200
    conn = connect(db_path)
    ledger = Ledger(conn)
    assert other_leg_account(ledger, leg_id(ledger, f"To {RULE_TEXT}")) == ("Deposito", "rule")
    conn.close()


def test_a_transfer_imported_from_the_command_line_goes_where_the_rule_says(tmp_path):
    db_path = tmp_path / "ledger.db"
    conn = connect(db_path)
    initialize(conn)
    ledger = Ledger(conn)
    _, revolut, _ = accounts(ledger)
    ledger.record(incoming(ledger, revolut, "250.00", "Bonifico da Mario", external_id="r-1"))
    conn.close()
    export = tmp_path / "export.csv"
    export.write_text(
        "Account,Date,Payee,Notes,Category_Group,Category,Amount,Split_Amount,Cleared\n"
        f"Fineco,{DAY},Giroconto {RULE_TEXT},,,,-250.00,0,Cleared\n",
        encoding="utf-8",
    )

    exit_code = main([
        "--db", str(db_path), "--config", str(MINIMAL_CONFIG),
        "import", str(export), "--account", "Fineco", "--profile", "actual",
    ])

    assert exit_code == 0
    conn = connect(db_path)
    ledger = Ledger(conn)
    leg = ledger.conn.execute(
        "SELECT id FROM transactions WHERE account_id = (SELECT id FROM accounts WHERE name = 'Fineco')"
    ).fetchone()[0]
    assert other_leg_account(ledger, leg) == ("Deposito", "rule")
    assert ledger.transfer_link(leg_id(ledger, "Bonifico da Mario")) is None
    conn.close()
