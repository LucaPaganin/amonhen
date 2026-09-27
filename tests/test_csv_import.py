"""CSV import: the mapping, the preview, and the write."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from amonhen.adapters.csv_adapter import read_csv
from amonhen.api import create_app
from amonhen.csv_import import missing_from_mapping, profile_from_mapping
from amonhen.db import connect
from amonhen.ledger import Ledger
from amonhen.models import Account, format_decimal

# A configuration of its own: the default is the operator's `accounts.json`,
# which is not in version control.
MINIMAL_CONFIG = Path(__file__).resolve().parent / "fixtures" / "config" / "minimal.json"

FINECO_STATEMENT = (
    "Data;Dare;Avere;Descrizione\n"
    "22/09/2025;12,30;;Caffè\n"
    "23/09/2025;;100,00;Stipendio\n"
)

# The mapping the import screen builds for that statement: money out in Dare,
# money in in Avere, Italian dates and decimals, no signed amount column.
FINECO_MAPPING = {
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
}


def mapping(**overrides) -> dict:
    """The Fineco mapping, with the fields a test is about replaced."""
    return {**FINECO_MAPPING, **overrides}


def write_statement(tmp_path, text: str) -> Path:
    path = tmp_path / "statement.csv"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def api(tmp_path):
    db_path = tmp_path / "ledger.db"
    client = TestClient(
        create_app(db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG)
    )
    conn = connect(db_path)
    Ledger(conn).ensure_account(Account(name="Fineco", type="real"))
    conn.close()

    yield client, db_path
    client.close()


def test_a_debit_and_a_credit_column_become_a_signed_amount(tmp_path):
    statement = write_statement(tmp_path, FINECO_STATEMENT)

    transactions, errors = read_csv(
        statement,
        account_id=1,
        balancing_account_id=2,
        profile=profile_from_mapping(FINECO_MAPPING),
    )

    assert errors == []
    assert [format_decimal(txn.amount) for txn in transactions] == ["-12.30", "100.00"]
    assert [txn.date.isoformat() for txn in transactions] == ["2025-09-22", "2025-09-23"]
    assert transactions[0].description == "Caffè"


def test_a_signed_amount_column_with_an_italian_separator(tmp_path):
    statement = write_statement(tmp_path, "Data;Importo;Descrizione\n22/09/2025;-12,30;Caffè\n")

    transactions, errors = read_csv(
        statement,
        account_id=1,
        balancing_account_id=2,
        profile=profile_from_mapping(
            mapping(
                date_column="Data",
                date_format="%d/%m/%Y",
                amount_column="Importo",
                debit_column="",
                credit_column="",
            )
        ),
    )

    assert errors == []
    assert [format_decimal(txn.amount) for txn in transactions] == ["-12.30"]


def test_invert_sign_flips_every_amount(tmp_path):
    statement = write_statement(tmp_path, FINECO_STATEMENT)

    transactions, _ = read_csv(
        statement,
        account_id=1,
        balancing_account_id=2,
        profile=profile_from_mapping(mapping(invert_sign=True)),
    )

    assert [format_decimal(txn.amount) for txn in transactions] == ["12.30", "-100.00"]


def test_empty_choices_are_unmapped_and_blank_columns_are_dropped():
    profile = profile_from_mapping(
        mapping(
            amount_column="Amount",
            debit_column="",
            credit_column="",
            external_id_column="",
            description_columns=["Payee", " ", "Notes"],
        )
    )

    assert profile.amount_column == "Amount"
    assert profile.debit_column is None
    assert profile.credit_column is None
    assert profile.external_id_column is None
    assert profile.description_columns == ("Payee", "Notes")


def test_an_incomplete_mapping_says_what_is_missing():
    assert missing_from_mapping(mapping(date_column="")) == "choose the date column"
    assert missing_from_mapping(mapping(description_columns=[""])) == "choose the description column"
    assert missing_from_mapping(mapping(amount_column="", debit_column="", credit_column="")) == (
        "choose the amount column, or both the debit and the credit column"
    )
    assert missing_from_mapping(mapping(amount_column="", credit_column="")) == (
        "choose the amount column, or both the debit and the credit column"
    )
    assert missing_from_mapping(FINECO_MAPPING) is None


def test_read_csv_keeps_the_good_rows_and_names_the_broken_line(tmp_path):
    statement = write_statement(
        tmp_path,
        "Data;Dare;Avere;Descrizione\n"
        "22/09/2025;12,30;;Caffè\n"
        "non-una-data;1,00;;Pagamento rotto\n"
        "23/09/2025;;100,00;Stipendio\n",
    )

    transactions, errors = read_csv(
        statement,
        account_id=1,
        balancing_account_id=2,
        profile=profile_from_mapping(FINECO_MAPPING),
    )

    assert [txn.description for txn in transactions] == ["Caffè", "Stipendio"]
    assert [(error.line, error.reason) for error in errors] == [
        (3, "unparseable date 'non-una-data' for format '%d/%m/%Y'")
    ]


def test_preview_shows_the_columns_and_the_rows_before_writing(api):
    client, _ = api

    payload = client.post(
        "/api/import/csv/preview",
        json={"content": FINECO_STATEMENT, "account": "Fineco", "mapping": FINECO_MAPPING},
    ).json()

    assert payload["columns"] == ["Data", "Dare", "Avere", "Descrizione"]
    assert payload["ready"] is True
    assert payload["problem"] is None
    assert payload["parsed"] == 2
    assert payload["rows"][0] == {
        "line": 2,
        "date": "2025-09-22",
        "amount": "-12.30",
        "description": "Caffè",
    }
    assert client.get("/api/transactions").json()["total"] == 0


def test_preview_gives_a_kept_row_its_own_line_when_an_earlier_row_is_broken(api):
    client, _ = api

    payload = client.post(
        "/api/import/csv/preview",
        json={
            "content": (
                "Data;Dare;Avere;Descrizione\n"
                "non-una-data;1,00;;Guasto\n"
                "23/09/2025;;100,00;Stipendio\n"
            ),
            "account": "Fineco",
            "mapping": FINECO_MAPPING,
        },
    ).json()

    assert [row["line"] for row in payload["rows"]] == [3]
    assert payload["rejected"] == [
        {"line": 2, "reason": "unparseable date 'non-una-data' for format '%d/%m/%Y'"}
    ]


def test_preview_offers_the_columns_while_the_mapping_is_incomplete(api):
    client, _ = api

    payload = client.post(
        "/api/import/csv/preview",
        json={
            "content": FINECO_STATEMENT,
            "account": "Fineco",
            "mapping": mapping(date_column="", amount_column="", debit_column="", credit_column=""),
        },
    ).json()

    assert payload["columns"] == ["Data", "Dare", "Avere", "Descrizione"]
    assert payload["ready"] is False
    assert payload["problem"] == "choose the date column"
    assert payload["rows"] == []


def test_import_writes_the_rows_and_reports_what_it_did(api):
    client, db_path = api

    response = client.post(
        "/api/import/csv",
        json={
            "filename": "movimenti.csv",
            "content": FINECO_STATEMENT,
            "account": "Fineco",
            "mapping": FINECO_MAPPING,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["account"] == "Fineco"
    assert payload["filename"] == "movimenti.csv"
    assert payload["parsed"] == 2
    assert payload["actions"]["inserted"] == 2
    assert payload["rejected"] == []

    written = client.get("/api/transactions").json()["items"]
    assert sorted(item["description"] for item in written) == ["Caffè", "Stipendio"]
    assert {item["amount"] for item in written} == {"-12.30", "100.00"}

    conn = connect(db_path)
    sources = {row["source_file"] for row in conn.execute("SELECT source_file FROM transactions")}
    conn.close()
    assert sources == {"movimenti.csv"}


def test_importing_the_same_content_again_writes_nothing(api):
    client, _ = api
    body = {"content": FINECO_STATEMENT, "account": "Fineco", "mapping": FINECO_MAPPING}

    first = client.post("/api/import/csv", json=body).json()
    second = client.post("/api/import/csv", json=body).json()

    assert first["actions"]["inserted"] == 2
    # The vocabulary names only the actions that happened: a second pass over the
    # same rows is all duplicates, so `inserted` is absent rather than zero.
    assert second["actions"].get("inserted", 0) == 0
    assert client.get("/api/transactions").json()["total"] == 2


def test_a_broken_row_does_not_fail_the_import(api):
    client, _ = api

    response = client.post(
        "/api/import/csv",
        json={
            "content": FINECO_STATEMENT + "non-una-data;1,00;;Guasto\n",
            "account": "Fineco",
            "mapping": FINECO_MAPPING,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actions"]["inserted"] == 2
    assert payload["rejected"] == [
        {"line": 4, "reason": "unparseable date 'non-una-data' for format '%d/%m/%Y'"}
    ]
    assert client.get("/api/transactions").json()["total"] == 2


def test_an_unknown_account_is_refused_and_nothing_is_written(api):
    client, _ = api
    body = {"content": FINECO_STATEMENT, "account": "Banca", "mapping": FINECO_MAPPING}

    response = client.post("/api/import/csv", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "no account named Banca: add it in Conti first, or import from the command line"
    )
    assert client.post("/api/import/csv/preview", json=body).status_code == 422
    assert client.get("/api/transactions").json()["total"] == 0
    assert [account["name"] for account in client.get("/api/accounts").json()] == ["Fineco"]


def test_a_statement_over_the_cap_is_refused(api):
    client, _ = api

    response = client.post(
        "/api/import/csv",
        json={"content": "x" * 8_000_001, "account": "Fineco", "mapping": FINECO_MAPPING},
    )

    assert response.status_code == 413
    assert "larger than 8 MB" in response.json()["detail"]
