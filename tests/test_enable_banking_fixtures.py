"""Phase 0 fixtures: anonymized Enable Banking dumps and the tool that builds them.

The fixtures are the committed evidence that the fetch path works and the
input for every parsing test. The anonymizer is shipped tooling, so its
contract (no real identifier survives, semantics survive) is tested directly.
"""
import decimal
import json
from pathlib import Path

import pytest

from tools.anonymize_dump import Anonymizer, select

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "enable_banking"
FIXTURES = sorted(FIXTURE_DIR.glob("*.json"))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixtures_exist():
    assert FIXTURES, f"no fixtures in {FIXTURE_DIR}"


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_is_wellformed(path):
    fixture = load(path)
    assert fixture["account"]["bank_name"]
    assert fixture["count"] == len(fixture["transactions"]) > 0
    for txn in fixture["transactions"]:
        assert txn["credit_debit_indicator"] in ("CRDT", "DBIT")
        assert txn["status"]
        assert decimal.Decimal(txn["transaction_amount"]["amount"]) >= 0
        assert txn["booking_date"]


def test_fixtures_cover_booked_and_pending_across_banks():
    banks, statuses = set(), set()
    for path in FIXTURES:
        fixture = load(path)
        banks.add(fixture["account"]["bank_name"])
        statuses.update(txn["status"] for txn in fixture["transactions"])
    assert len(banks) >= 2, f"need two institutions, got {banks}"
    assert {"BOOK", "PDNG"} <= statuses, f"need BOOK and PDNG, got {statuses}"


def test_select_keeps_every_pending_row_beyond_the_limit():
    txns = [{"status": "BOOK", "bank_transaction_code": {"code": "CARD_PAYMENT"}} for _ in range(5)]
    txns.insert(3, {"status": "PDNG", "bank_transaction_code": {"code": "CARD_PAYMENT"}})

    selected = select(txns, 2)

    assert [t["status"] for t in selected].count("PDNG") == 1


def test_anonymizer_preserves_semantics_and_scrubs_text_lists():
    anonymizer = Anonymizer("test-salt", ["Nadia Verdi"])
    anonymizer.date_shift = anonymizer.shift_for("Revolut")
    raw = {
        "booking_date": "2026-04-27",
        "status": "PDNG",
        "credit_debit_indicator": "DBIT",
        "transaction_amount": {"amount": "10.00", "currency": "EUR"},
        "bank_transaction_code": {"code": "TRANSFER"},
        "creditor": {"name": "VERDI NADIA"},
        "remittance_information": ["Payment from VERDI NADIA", "IBAN IT60X0542811101000000123456"],
    }

    out = anonymizer.anonymize(raw, amount_key="txn-1")
    text = json.dumps(out)

    assert "verdi" not in text.lower() and "nadia" not in text.lower()
    assert "IT60X0542811101000000123456" not in text
    assert out["status"] == "PDNG"
    assert out["credit_debit_indicator"] == "DBIT"
    assert out["bank_transaction_code"] == {"code": "TRANSFER"}
    assert out["booking_date"] != raw["booking_date"]
    assert decimal.Decimal(out["transaction_amount"]["amount"]) != decimal.Decimal("10.00")


def test_anonymizer_replaces_party_names_with_synthetic_ones():
    anonymizer = Anonymizer("test-salt", [])
    out = anonymizer.anonymize({"creditor": {"name": "Mario Rossi"}})
    assert out["creditor"]["name"] != "Mario Rossi"


def test_salt_lives_outside_the_repository(tmp_path, monkeypatch):
    from tools.anonymize_dump import load_salt

    salt_file = tmp_path / "salt"
    monkeypatch.delenv("AMONHEN_ANON_SALT", raising=False)

    first = load_salt(salt_file)

    assert salt_file.exists()
    assert load_salt(salt_file) == first
    monkeypatch.setenv("AMONHEN_ANON_SALT", "from-the-environment")
    assert load_salt(salt_file) == "from-the-environment"


def test_amount_mapping_depends_on_the_salt():
    raw = {
        "booking_date": "2026-01-01",
        "status": "BOOK",
        "credit_debit_indicator": "DBIT",
        "transaction_amount": {"amount": "99.99", "currency": "EUR"},
    }
    first = Anonymizer("salt-a", []).anonymize(raw, amount_key="k")["transaction_amount"]["amount"]
    second = Anonymizer("salt-b", []).anonymize(raw, amount_key="k")["transaction_amount"]["amount"]

    assert first != second
