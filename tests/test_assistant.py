"""Desiderata 5.9: a reading of the numbers already computed, and its guards.

Every test here is one of the promises the section makes: the packet carries no
identifier, a figure nobody computed is refused, a proposal outside the
vocabulary is dropped, nothing is applied without a person, and the same
question about the same numbers does not reach the model twice.
"""
import datetime as dt
import json
from decimal import Decimal

import pytest
import responses as responses_lib

from amonhen import assistant
from amonhen.llm import LlmConfig
from amonhen.models import Account, IncomingTransaction

URL = "https://llm.example.test/v1/chat/completions"
TODAY = dt.date(2026, 9, 12)
# A payment whose description carries an IBAN, as a bank does print them.
IBAN = "IT60X0542811101000000123456"


def make_txn(ledger, account_id, day, amount, description, balancing):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(day),
        amount=Decimal(amount),
        description=description,
        status="BOOK",
        source="import",
        balancing_account_id=balancing,
        raw={"creditor": {"name": "Somebody"}, "raw_only": "payload that must not travel"},
    )


def seed(ledger):
    """Two months of money, one merchant nobody has categorized, one IBAN."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    ledger.category("Transport")
    ledger.record(make_txn(ledger, account, "2026-07-10", "-120.00", "ESSELUNGA | CARD", groceries))
    ledger.record(make_txn(ledger, account, "2026-08-10", "-120.00", "ESSELUNGA | CARD", groceries))
    ledger.record(make_txn(ledger, account, "2026-09-05", "-30.00", "ESSELUNGA | CARD", groceries))
    ledger.record(make_txn(ledger, account, "2026-08-11", "-60.00", "TRENITALIA", ledger.category("Transport")))
    ledger.record(
        make_txn(ledger, account, "2026-08-12", "1800.00", "STIPENDIO", ledger.category("Stipendio"))
    )
    unseen = ledger.record(
        make_txn(
            ledger,
            account,
            "2026-08-20",
            "-45.50",
            f"BONIFICO {IBAN}",
            ledger.uncategorized(),
        )
    )[0]
    return account, unseen


def config(**overrides) -> LlmConfig:
    values = {"url": URL, "api_key": "secret", "model": "test-model"}
    values.update(overrides)
    return LlmConfig(**values)


def stub(mock, answer: dict, status: int = 200) -> None:
    """Register the answer on the mock in scope, not on the global one."""
    mock.post(
        URL,
        json={"choices": [{"message": {"content": json.dumps(answer)}}]},
        status=status,
    )


def packet_of(ledger) -> dict:
    return assistant.data_packet(ledger, TODAY)


def quoting_reading(ledger) -> str:
    """A reading that breaks no rule: the figures are the packet's own."""
    packet = packet_of(ledger)
    slice_ = packet["spese_per_categoria"][0]
    return f"La categoria {slice_['categoria']} ha preso {slice_['importo']} nel periodo."


# -- what the model is handed ----------------------------------------------


def test_the_packet_carries_the_computed_numbers_and_no_identifier(ledger):
    seed(ledger)

    packet = packet_of(ledger)
    text = json.dumps(packet, ensure_ascii=False)

    # The figures the screens read, and nothing the bank sent.
    assert set(packet) >= {
        "metriche",
        "flussi_mensili",
        "spese_per_categoria",
        "budget",
        "saldi",
        "coda",
        "merchant_senza_categoria",
        "categorie",
        "contesto",
    }
    assert IBAN not in text
    assert "[iban]" in text
    assert "raw_only" not in text
    assert packet["coda"]["senza_categoria"] == 1
    assert packet["merchant_senza_categoria"] != []


def test_a_context_hands_over_a_figure_not_a_row(ledger):
    _, unseen = seed(ledger)

    packet = assistant.data_packet(ledger, TODAY, context={"kind": "movimento", "id": unseen})
    context = packet["contesto"]

    assert context["tipo"] == "movimento"
    assert context["importo"] == "-45.50"
    assert context["categoria"] == "Uncategorized"
    assert IBAN not in json.dumps(context, ensure_ascii=False)
    assert "raw_only" not in json.dumps(context, ensure_ascii=False)

    # A budget enters as the three figures it is made of, not as a row: the
    # month it answers for is the one running, which is what a monthly budget is.
    # The id stays here — it is how the row is found, not something to send.
    groceries = ledger.find_account(name="Groceries")
    assert groceries is not None
    packet = assistant.data_packet(ledger, TODAY, context={"kind": "budget", "id": groceries["id"]})
    assert packet["contesto"] == {
        "tipo": "budget",
        "categoria": "Groceries",
        "budget": None,
        "speso": "30.00",
        "rimasto": None,
    }
    assert set(packet["budget"][0]) == {"categoria", "budget", "speso", "rimasto"}


# -- the numbers rule -------------------------------------------------------


def test_a_reading_that_quotes_the_numbers_is_kept_and_not_asked_twice(ledger):
    seed(ledger)
    with responses_lib.RequestsMock() as mock:
        stub(mock, {"lettura": quoting_reading(ledger)})

        first = assistant.ask(ledger, config(), "Come sta andando?", today=TODAY)
        second = assistant.ask(ledger, config(), "Come sta andando?", today=TODAY)

        assert len(mock.calls) == 1

    assert first.cached is False
    assert second.cached is True
    assert second.answer == first.answer
    assert len(first.fingerprint) == 16
    kept = ledger.readings()[0]
    assert kept["model"] == "test-model"
    assert kept["question"] == "Come sta andando?"
    assert kept["refused"] is None


def test_an_answer_that_proposed_something_is_still_not_asked_twice(ledger):
    """The proposals are the assistant's own trail, not data it should re-read."""
    seed(ledger)
    offered = packet_of(ledger)["merchant_senza_categoria"][0]
    with responses_lib.RequestsMock() as mock:
        stub(
            mock,
            {
                "lettura": quoting_reading(ledger),
                "proposte": [{"tipo": "categoria", "merchant": offered, "categoria": "Groceries"}],
            },
        )

        first = assistant.ask(ledger, config(), "Cosa posso smistare?", today=TODAY)
        second = assistant.ask(ledger, config(), "Cosa posso smistare?", today=TODAY)

        assert len(mock.calls) == 1

    assert first.cached is False
    assert second.cached is True
    assert len(ledger.readings()) == 1


def test_a_reading_that_cites_a_figure_nobody_computed_is_refused(ledger):
    seed(ledger)
    with responses_lib.RequestsMock() as mock:
        stub(mock, {"lettura": "Questo mese hai speso 3000,00 in più del solito."})

        with pytest.raises(ValueError, match="cifre non calcolate"):
            assistant.ask(ledger, config(), "", today=TODAY)

        assert len(mock.calls) == 1

    refused = ledger.readings()[0]
    assert refused["answer"] == ""
    assert "3000" in refused["refused"]


def test_the_numbers_rule_reads_the_separators_the_italian_way():
    allowed = assistant.allowed_numbers({"saldo": "1234.56", "giorno": "2026-06-30"})

    assert assistant.unsupported_numbers("Il saldo è 1.234,56 €.", allowed) == []
    assert assistant.unsupported_numbers("Il giorno è 30/06/2026.", allowed) == []
    assert assistant.unsupported_numbers("Sono 3.000 €.", allowed) == ["3.000"]


def test_the_numbers_rule_reads_a_comparison_as_the_figures_it_is_made_of():
    """A model writes "entrate/uscite", and both halves were in the packet."""
    allowed = assistant.allowed_numbers({"entrate": "1200.00", "uscite": "40.00"})

    assert assistant.unsupported_numbers("Il mese: 1.200,00/40,00.", allowed) == []
    assert assistant.unsupported_numbers("Il mese: 1.200,00/40,00, cioè 9.", allowed) == ["9"]


# -- proposing and deciding -------------------------------------------------


def test_a_proposal_outside_the_vocabulary_is_dropped_and_a_valid_one_waits(ledger):
    _, unseen = seed(ledger)
    offered = packet_of(ledger)["merchant_senza_categoria"][0]
    with responses_lib.RequestsMock() as mock:
        stub(
            mock,
            {
                "lettura": quoting_reading(ledger),
                "proposte": [
                    {"tipo": "categoria", "merchant": "MAI VISTO", "categoria": "Groceries"},
                    {"tipo": "categoria", "merchant": offered, "categoria": "Non esiste"},
                    {"tipo": "badget", "categoria": "Groceries"},
                    {"tipo": "categoria", "merchant": offered, "categoria": "Groceries"},
                ],
            }
        )

        reading = assistant.ask(ledger, config(), "", today=TODAY)

    assert [item["merchant"] for item in reading.proposals] == [offered]
    assert [row["merchant"] for row in ledger.suggestions("pending")] == [offered]
    # Waiting, not applied: the movement still sits where it sat.
    assert ledger.category_of(unseen) == "Uncategorized"


def test_a_budget_proposal_is_applied_only_when_a_person_accepts_it(ledger):
    seed(ledger)
    with responses_lib.RequestsMock() as mock:
        stub(
            mock,
            {
                "lettura": quoting_reading(ledger),
                "proposte": [
                    {"tipo": "budget", "categoria": "Transport", "importo": "50.00"},
                    {"tipo": "budget", "categoria": "Non esiste", "importo": "10.00"},
                    {"tipo": "budget", "categoria": "Groceries", "importo": "-5.00"},
                ],
            }
        )

        assistant.ask(ledger, config(), "", today=TODAY)

    proposals = assistant.budget_proposals(ledger)
    assert [(item["category"], item["amount"], item["source"]) for item in proposals] == [
        ("Transport", "50.00", "llm")
    ]
    start, end = dt.date(2026, 9, 1), dt.date(2026, 9, 30)
    transport = next(row for row in ledger.budget_status(start, end) if row["category"] == "Transport")
    assert transport["budget"] is None

    assistant.decide_budget_proposal(ledger, "Transport", "accept")

    transport = next(row for row in ledger.budget_status(start, end) if row["category"] == "Transport")
    assert transport["budget"] == "50.00"
    assert assistant.budget_proposals(ledger) == []
    with pytest.raises(KeyError):
        assistant.decide_budget_proposal(ledger, "Transport", "accept")


# -- how it is controlled ---------------------------------------------------


def test_the_day_has_a_ceiling_and_the_state_says_how_much_is_left(ledger):
    seed(ledger)
    ledger.set_setting(f"assistant_calls:{TODAY.isoformat()}", str(assistant.CALL_LIMIT))

    with pytest.raises(RuntimeError, match="already answered"):
        assistant.ask(ledger, config(), "", today=TODAY)

    state = assistant.state(ledger, config(), TODAY)
    assert state["configured"] is True
    assert state["model"] == "test-model"
    assert state["calls_today"] == assistant.CALL_LIMIT
    assert state["call_limit"] == assistant.CALL_LIMIT


def test_without_a_model_the_section_says_so_instead_of_failing(ledger):
    seed(ledger)
    off = LlmConfig(url="", api_key="", model="")

    with pytest.raises(RuntimeError, match="no LLM configured"):
        assistant.ask(ledger, off, "Come va?", today=TODAY)

    assert assistant.state(ledger, off, TODAY)["configured"] is False


def test_the_request_follows_the_protocol_the_provider_needs(ledger):
    seed(ledger)
    with responses_lib.RequestsMock() as mock:
        stub(mock, {"lettura": quoting_reading(ledger)})

        assistant.ask(ledger, config(), "Come sta andando?", context={"kind": "cruscotto"}, today=TODAY)

        request = mock.calls[0].request
        body = json.loads(request.body)

    assert request.headers["Authorization"] == "Bearer secret"
    assert body["model"] == "test-model"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    # DeepSeek and OpenAI refuse json_object unless the prompt says "json".
    assert "json" in body["messages"][0]["content"].lower()
    sent = json.loads(body["messages"][1]["content"])
    assert sent["domanda"] == "Come sta andando?"
    assert sent["dati"]["contesto"]["tipo"] == "cruscotto"


def test_an_http_failure_reaches_the_caller_as_an_error(ledger):
    seed(ledger)
    with responses_lib.RequestsMock() as mock:
        mock.post(URL, status=500)

        with pytest.raises(Exception):
            assistant.ask(ledger, config(), "", today=TODAY)

    assert ledger.readings() == []
