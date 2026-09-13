"""Manual-export adapters converge on the same IncomingTransaction shape as PSD2."""
import dataclasses
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from amonhen.adapters import parse_export
from amonhen.adapters.csv_adapter import ACTUAL, FINECO, REVOLUT, CsvProfile, parse_csv
from amonhen.adapters.ofx_adapter import parse_ofx

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "imports"
ACCOUNT = 11
BALANCING = 22


def _parse(name, profile):
    return parse_csv(
        FIXTURES / name, account_id=ACCOUNT, balancing_account_id=BALANCING, profile=profile
    )


def test_revolut_signed_amounts_and_dates():
    txns = _parse("revolut.csv", REVOLUT)

    assert [t.amount for t in txns] == [Decimal("-3.94"), Decimal("1500.00"), Decimal("-200.00")]
    assert [t.date for t in txns] == [
        dt.date(2026, 5, 17), dt.date(2026, 5, 16), dt.date(2026, 5, 15)
    ]
    assert txns[0].description == "ACME Srl"
    assert txns[0].status == "BOOK"
    assert txns[0].source == "import"
    assert txns[0].account_id == ACCOUNT
    assert txns[0].balancing_account_id == BALANCING


def test_fineco_separate_columns_italian_dates_and_decimals():
    txns = _parse("fineco.csv", FINECO)

    # Dare is a debit, Avere a credit; commas are decimals and dots thousands.
    assert [t.amount for t in txns] == [
        Decimal("-1234.56"), Decimal("3000.00"), Decimal("45.50")
    ]
    assert [t.date for t in txns] == [
        dt.date(2026, 5, 15), dt.date(2026, 5, 14), dt.date(2026, 5, 13)
    ]
    assert txns[0].description == "Bonifico a ACME Srl"


def test_actual_payee_and_notes_form_the_description():
    txns = _parse("actual.csv", ACTUAL)

    assert [t.amount for t in txns] == [Decimal("-3.94"), Decimal("-120.00"), Decimal("45.50")]
    assert txns[0].description == "ACME Srl | CARD_PAYMENT | VISA 7883"
    assert "Refund" in txns[2].description


def test_invert_sign_flips_the_amount():
    profile = dataclasses.replace(REVOLUT, invert_sign=True)

    txns = _parse("revolut.csv", profile)

    assert [t.amount for t in txns] == [Decimal("3.94"), Decimal("-1500.00"), Decimal("200.00")]


def test_external_id_is_captured_when_the_export_has_one():
    profile = CsvProfile(
        date_column="Date",
        amount_column="Amount",
        description_columns=("Description",),
        external_id_column="Reference",
    )

    txns = _parse("id_export.csv", profile)

    assert [t.external_id for t in txns] == ["REF-0001", "REF-0002"]


def test_skip_rows_skips_the_preamble():
    profile = CsvProfile(date_column="Date", amount_column="Amount", skip_rows=1)
    txns = _parse("with_preamble.csv", profile)

    assert len(txns) == 1
    assert txns[0].amount == Decimal("-3.94")


def test_parsing_the_same_file_twice_returns_equal_transactions():
    first = _parse("actual.csv", ACTUAL)
    second = _parse("actual.csv", ACTUAL)

    assert first == second


def test_malformed_row_reports_the_line_number():
    with pytest.raises(ValueError, match="line 3"):
        _parse("malformed.csv", CsvProfile(date_column="Date", amount_column="Amount"))


def test_parse_export_dispatches_on_suffix(tmp_path):
    csv_txns = parse_export(
        FIXTURES / "actual.csv", account_id=ACCOUNT, balancing_account_id=BALANCING, profile=ACTUAL
    )
    ofx_txns = parse_export(
        FIXTURES / "statement.ofx", account_id=ACCOUNT, balancing_account_id=BALANCING
    )
    qfx = tmp_path / "statement.qfx"
    qfx.write_text((FIXTURES / "statement.ofx").read_text(encoding="utf-8"), encoding="utf-8")
    qfx_txns = parse_export(qfx, account_id=ACCOUNT, balancing_account_id=BALANCING)

    assert csv_txns and ofx_txns == qfx_txns

    with pytest.raises(ValueError, match="CsvProfile"):
        parse_export(FIXTURES / "actual.csv", account_id=ACCOUNT, balancing_account_id=BALANCING)
    with pytest.raises(ValueError, match="unsupported"):
        parse_export(tmp_path / "statement.txt", account_id=ACCOUNT, balancing_account_id=BALANCING)


def test_ofx_sgml_maps_amount_date_fitid_and_description():
    txns = parse_ofx(FIXTURES / "statement.ofx", account_id=ACCOUNT, balancing_account_id=BALANCING)

    assert len(txns) == 2  # LEDGERBAL is not a transaction
    assert txns[0].amount == Decimal("-3.94")
    assert txns[0].date == dt.date(2026, 5, 17)
    assert txns[0].external_id == "IMP0001"
    assert txns[0].description == "ACME Srl | Card payment"
    assert txns[1].amount == Decimal("1500.00")
    assert txns[1].date == dt.date(2026, 5, 16)
    assert txns[1].external_id == "IMP0002"
    assert txns[0].status == "BOOK" and txns[0].source == "import"


def test_ofx_xml_maps_amount_date_fitid_and_description():
    txns = parse_ofx(FIXTURES / "statement.xml", account_id=ACCOUNT, balancing_account_id=BALANCING)

    assert len(txns) == 2
    assert txns[0].amount == Decimal("-42.50")
    assert txns[0].date == dt.date(2026, 5, 14)
    assert txns[0].external_id == "XML0001"
    assert txns[0].description == "ACME Srl | Utility bill"
    assert txns[1].amount == Decimal("800.00")
    assert txns[1].description == "ACME Srl | Invoice settlement"
