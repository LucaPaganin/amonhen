"""A category renamed carries with it everything that names it."""
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from amonhen.api import create_app
from amonhen.db import connect, initialize
from amonhen.ledger import Ledger
from amonhen.merchants import RuleBook, categorize
from amonhen.models import Account, IncomingTransaction

MINIMAL_CONFIG = Path(__file__).resolve().parent / "fixtures" / "config" / "minimal.json"


@pytest.fixture
def ledger(tmp_path):
    conn = connect(tmp_path / "ledger.db")
    initialize(conn)
    yield Ledger(conn)
    conn.close()


def _movement(ledger, account, description):
    ledger.record(
        IncomingTransaction(
            account_id=account,
            date=dt.date(2026, 8, 3),
            amount=Decimal("-10.00"),
            description=description,
            status="BOOK",
            source="psd2",
            balancing_account_id=ledger.uncategorized(),
            raw={},
        )
    )


def test_the_rules_follow_and_no_sync_brings_the_old_name_back(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    _movement(ledger, account, "To Marco")
    category = ledger.category("Rimborsi")
    book = RuleBook(ledger.conn)
    book.set_rule("to marco", "Rimborsi", ledger)

    ledger.rename_category(category, "Pagamenti a persone")
    _movement(ledger, account, "To Marco di nuovo")
    categorize(ledger, book)

    assert ledger.find_account(name="Rimborsi") is None
    assert [rule.target for rule in book.rules()] == ["Pagamenti a persone"]
    assert ledger.conn.execute(
        """SELECT COUNT(*) AS c FROM postings p WHERE p.account_id = ?""", (category,)
    ).fetchone()["c"] == 2


def test_a_pending_proposal_follows(ledger):
    category = ledger.category("Rimborsi")
    ledger.conn.execute(
        "INSERT INTO merchant_suggestions (merchant, category, source, created_at)"
        " VALUES ('x', 'Rimborsi', 'llm', '2026-11-01')"
    )

    ledger.rename_category(category, "Persone")

    assert [row["category"] for row in ledger.suggestions("pending")] == ["Persone"]


@pytest.mark.parametrize("name", ["Revolut", "Svago", "  "])
def test_a_name_taken_or_empty_is_refused(ledger, name):
    ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.category("Svago")
    category = ledger.category("Rimborsi")

    with pytest.raises(ValueError):
        ledger.rename_category(category, name)
    assert ledger.account(category)["name"] == "Rimborsi"


def test_the_review_bucket_keeps_its_name(ledger):
    with pytest.raises(ValueError):
        ledger.rename_category(ledger.uncategorized(), "Da vedere")


def test_the_same_name_is_not_a_clash_with_itself(ledger):
    category = ledger.category("Rimborsi")

    ledger.rename_category(category, " Rimborsi ")

    assert ledger.account(category)["name"] == "Rimborsi"


def test_the_api_renames_and_answers_the_row(tmp_path):
    db_path = tmp_path / "ledger.db"
    client = TestClient(create_app(db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG))
    conn = connect(db_path)
    category = Ledger(conn).category("Rimborsi")
    Ledger(conn).category("Svago")

    renamed = client.patch(f"/api/categories/{category}", json={"name": "Persone"})
    refused = client.patch(f"/api/categories/{category}", json={"name": "Svago"})

    assert renamed.json()["name"] == "Persone"
    assert refused.status_code == 422
    conn.close()
    client.close()
