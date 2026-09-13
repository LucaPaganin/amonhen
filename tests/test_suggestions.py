"""LLM proposals: only discrete labels, only for unseen merchants, never applied."""
import datetime as dt
import json
from decimal import Decimal

import pytest
import responses as responses_lib

from amonhen.ledger import Ledger
from amonhen.models import Account, IncomingTransaction
from amonhen.llm import LlmConfig
from amonhen.suggestions import (
    propose_for_unseen,
    unseen_merchants,
)

URL = "https://llm.example.test/v1/chat/completions"


def make_txn(ledger, account_id, amount, description):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date(2026, 9, 1),
        amount=Decimal(amount),
        description=description,
        status="BOOK",
        source="import",
        balancing_account_id=ledger.uncategorized(),
        raw={},
    )


def seed(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "-12.30", "NEVER SEEN SHOP"))
    ledger.record(make_txn(ledger, account, "-5.00", "NEVER SEEN SHOP"))
    ledger.record(make_txn(ledger, account, "-9.90", "KNOWN MERCHANT"))
    ledger.category("Groceries")
    ledger.category("Transport")
    from amonhen.merchants import RuleBook

    RuleBook(ledger.conn).set_rule("KNOWN MERCHANT", "Groceries", ledger)
    return account


def config(**overrides) -> LlmConfig:
    values = {"url": URL, "api_key": "secret", "model": "test-model"}
    values.update(overrides)
    return LlmConfig(**values)


def test_unseen_merchants_skips_ruled_and_duplicated_merchants(ledger):
    seed(ledger)

    merchants = unseen_merchants(ledger)

    assert merchants == ["NEVER SEEN SHOP"]


@responses_lib.activate
def test_proposals_are_recorded_as_pending_and_never_applied(ledger):
    seed(ledger)
    responses_lib.post(
        URL,
        json={"choices": [{"message": {"content": json.dumps({"proposte": {"NEVER SEEN SHOP": "Groceries"}})}}]},
    )

    recorded = propose_for_unseen(ledger, config())

    assert recorded == 1
    request = json.loads(responses_lib.calls[0].request.body)
    assert request["temperature"] == 0
    assert "NEVER SEEN SHOP" in request["messages"][1]["content"]
    assert responses_lib.calls[0].request.headers["Authorization"] == "Bearer secret"
    suggestion = ledger.suggestions()[0]
    assert suggestion["merchant"] == "NEVER SEEN SHOP"
    assert suggestion["category"] == "Groceries"
    assert suggestion["source"] == "llm"
    # Nothing was categorized: the human decides.
    transaction = ledger.conn.execute("SELECT id FROM transactions LIMIT 1").fetchone()
    assert ledger.category_of(transaction["id"]) == "Uncategorized"


@responses_lib.activate
def test_a_category_outside_the_list_is_ignored(ledger):
    seed(ledger)
    responses_lib.post(
        URL,
        json={"choices": [{"message": {"content": json.dumps({"proposte": {"NEVER SEEN SHOP": "Invented"}})}}]},
    )

    assert propose_for_unseen(ledger, config()) == 0
    assert ledger.suggestions() == []


@responses_lib.activate
def test_a_merchant_that_was_not_asked_about_is_ignored(ledger):
    seed(ledger)
    responses_lib.post(
        URL,
        json={"choices": [{"message": {"content": json.dumps({"proposte": {"SOMETHING ELSE": "Groceries"}})}}]},
    )

    assert propose_for_unseen(ledger, config()) == 0


def test_nothing_is_sent_when_there_is_nothing_unseen(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    ledger.record(make_txn(ledger, account, "-9.90", "KNOWN MERCHANT"))
    ledger.category("Groceries")
    from amonhen.merchants import RuleBook

    RuleBook(ledger.conn).set_rule("KNOWN MERCHANT", "Groceries", ledger)

    assert propose_for_unseen(ledger, config()) == 0


def test_an_unconfigured_model_is_an_error_not_a_crash(ledger):
    with pytest.raises(RuntimeError, match="no LLM configured"):
        propose_for_unseen(ledger, LlmConfig(url="", api_key="", model=""))


@responses_lib.activate
def test_an_http_error_propagates_to_the_caller(ledger):
    seed(ledger)
    responses_lib.post(URL, status=500)

    with pytest.raises(Exception):
        propose_for_unseen(ledger, config())

    assert ledger.suggestions() == []
