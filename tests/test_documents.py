"""The paperwork behind a movement: what Paperless holds, linked and unlinked by hand."""
import datetime as dt
from decimal import Decimal

import pytest

from amonhen.models import Account, IncomingTransaction


def movement(ledger) -> int:
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    txn_id, _ = ledger.record(IncomingTransaction(
        account_id=bank, date=dt.date(2026, 11, 2), amount=Decimal("-51"),
        description="Saldo 1 sedute - Lenti", status="BOOK", source="psd2",
        balancing_account_id=ledger.category("Spese"), external_id="m1",
    ))
    return txn_id


def test_a_document_links_to_a_movement_and_comes_off_again(ledger):
    txn = movement(ledger)
    ledger.link_document(txn, 42, title="Ricevuta Lenti - 02/11/2026", created="2026-11-02",
                         kind="Ricevuta sanitaria", linked_at="2026-11-25T10:00:00")
    assert [(row["paperless_id"], row["title"], row["kind"]) for row in ledger.documents_of(txn)] == [
        (42, "Ricevuta Lenti - 02/11/2026", "Ricevuta sanitaria"),
    ]
    ledger.unlink_document(txn, 42)
    assert ledger.documents_of(txn) == []


def test_linking_the_same_document_twice_rewrites_it_once(ledger):
    txn = movement(ledger)
    for title in ("Ricevuta Lenti", "Ricevuta Lenti - 02/11/2026"):
        ledger.link_document(txn, 42, title=title, created="2026-11-02", kind=None,
                             linked_at="2026-11-25T10:00:00")
    assert [row["title"] for row in ledger.documents_of(txn)] == ["Ricevuta Lenti - 02/11/2026"]


def test_a_document_cannot_link_to_a_movement_that_is_not_there(ledger):
    with pytest.raises(ValueError):
        ledger.link_document(9999, 42, title="x", created=None, kind=None, linked_at="now")


def test_a_deleted_movement_takes_its_documents_with_it(ledger):
    txn = movement(ledger)
    ledger.link_document(txn, 42, title="Ricevuta Lenti", created="2026-11-02", kind=None,
                         linked_at="2026-11-25T10:00:00")
    ledger.delete_transaction(txn)
    assert ledger.documents_of(txn) == []


# -- the API and the adapter -------------------------------------------------------

class FakePaperless:
    """The Paperless port, answering what the tests put in it."""

    def __init__(self) -> None:
        self.documents = [{
            "paperless_id": 42, "title": "Ricevuta Lenti - 02/11/2026",
            "created": "2026-11-02", "kind": "Ricevuta sanitaria",
            "correspondent": "Gabriele Lenti",
        }]

    def search(self, query: str, limit: int = 15) -> list[dict]:
        return [document for document in self.documents if query.lower() in document["title"].lower()]

    def one(self, paperless_id: int) -> dict:
        return next(document for document in self.documents if document["paperless_id"] == paperless_id)

    def invoices(self, query: str = "", offset: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        found = [
            {**document, "amount": "51.00"}
            for document in self.documents
            if query.lower() in document["title"].lower()
        ]
        return found, len(found)


@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from amonhen.api import routes
    from amonhen.api.app import create_app
    from amonhen.db import connect, initialize
    from tests.fixed_clock import FixedClock
    from tests.test_amonhen_cli import MINIMAL_CONFIG

    db_path = tmp_path / "documents.db"
    conn = connect(db_path)
    initialize(conn)
    conn.close()
    monkeypatch.setattr(routes.transactions, "invoice_source", lambda: FakePaperless())
    client = TestClient(create_app(
        db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG,
        clock=FixedClock(dt.date(2026, 11, 25)),
    ))
    client.db_path = db_path
    yield client
    client.close()


def test_the_api_searches_paperless_and_links_the_document_it_found(api):
    from amonhen.db import connect
    from amonhen.ledger import Ledger

    conn = connect(api.db_path)
    txn = movement(Ledger(conn))
    conn.close()

    found = api.get("/api/documents/search?q=Lenti").json()
    assert found["configured"] is True
    assert [item["title"] for item in found["items"]] == ["Ricevuta Lenti - 02/11/2026"]

    linked = api.put(f"/api/transactions/{txn}/documents/42")
    assert linked.status_code == 200, linked.text
    assert [document["paperless_id"] for document in linked.json()["documents"]] == [42]

    unlinked = api.delete(f"/api/transactions/{txn}/documents/42")
    assert unlinked.json()["documents"] == []


def test_without_paperless_the_search_says_so_and_linking_refuses(api, monkeypatch):
    from amonhen.api import routes

    monkeypatch.setattr(routes.transactions, "invoice_source", lambda: None)
    assert api.get("/api/documents/search?q=x").json() == {"configured": False, "items": []}
    assert api.put("/api/transactions/1/documents/42").status_code == 503


def test_the_invoice_search_names_the_type_and_the_issuer():
    import responses

    from amonhen.adapters.paperless_invoices import PaperlessInvoices

    base = "http://paperless:8000"
    with responses.RequestsMock() as mock:
        page = {"results": [{
            "id": 42, "title": "Ricevuta Lenti - 02/11/2026", "created": "2026-11-02",
            "document_type": 6, "correspondent": 11,
        }]}
        mock.get(f"{base}/api/documents/", json=page)
        mock.get(f"{base}/api/documents/", json=page)
        mock.get(f"{base}/api/document_types/", json={"results": [{"id": 6, "name": "Ricevuta sanitaria"}]})
        mock.get(f"{base}/api/correspondents/", json={"results": [{"id": 11, "name": "Gabriele Lenti"}]})
        source = PaperlessInvoices(base, "token")
        assert source.search("Lenti") == [{
            "paperless_id": 42, "title": "Ricevuta Lenti - 02/11/2026", "created": "2026-11-02",
            "kind": "Ricevuta sanitaria", "correspondent": "Gabriele Lenti",
        }]


def test_the_api_lists_the_documents_and_what_pays_them(api):
    from amonhen.db import connect
    from amonhen.ledger import Ledger

    listing = api.get("/api/invoices").json()
    assert listing["configured"] is True
    assert listing["total"] == 1
    assert listing["items"][0]["amount"] == "51.00"
    assert listing["items"][0]["movements"] == []

    conn = connect(api.db_path)
    txn = movement(Ledger(conn))
    conn.close()
    api.put(f"/api/transactions/{txn}/documents/42")

    linked = api.get("/api/invoices").json()["items"][0]["movements"]
    assert [(row["id"], row["amount"]) for row in linked] == [(txn, "-51.00")]


def test_the_invoice_list_asks_paperless_for_the_three_kinds_and_their_totals():
    import responses

    from amonhen.adapters.paperless_invoices import PaperlessInvoices

    base = "http://paperless:8000"
    with responses.RequestsMock() as mock:
        mock.get(f"{base}/api/document_types/", json={"results": [
            {"id": 6, "name": "Fattura"}, {"id": 8, "name": "Referto medico"},
        ]})
        mock.get(f"{base}/api/correspondents/", json={"results": [{"id": 11, "name": "Gabriele Lenti"}]})
        mock.get(f"{base}/api/custom_fields/", json={"results": [{"id": 3, "name": "Importo"}]})
        mock.get(f"{base}/api/documents/", json={"count": 1, "results": [{
            "id": 42, "title": "Fattura Lenti - giugno 2026", "created": "2026-09-26",
            "document_type": 6, "correspondent": 11,
            "custom_fields": [{"field": 3, "value": "255.00"}],
        }]})
        source = PaperlessInvoices(base, "token")
        items, total = source.invoices(limit=20)
        assert total == 1
        assert items == [{
            "paperless_id": 42, "title": "Fattura Lenti - giugno 2026", "created": "2026-09-26",
            "kind": "Fattura", "correspondent": "Gabriele Lenti", "amount": "255.00",
        }]
        asked = next(c for c in mock.calls if "/api/documents/" in c.request.url).request.url
        assert "document_type__id__in=6" in asked  # the referto is not an invoice


# -- the rules that link a document to its payment (desiderata 5.16-bis) ----------


def spend(ledger, day: str, amount: str, description: str, external: str) -> int:
    """One outflow of the checking account, as a bill would be paid."""
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    txn_id, _ = ledger.record(IncomingTransaction(
        account_id=bank, date=dt.date.fromisoformat(day), amount=Decimal(amount),
        description=description, status="BOOK", source="psd2",
        balancing_account_id=ledger.category("Spese"), external_id=external,
    ))
    return txn_id


def paperless(paperless_id: int, created: str, amount: str, correspondent: str = "Dolomiti Energia",
              title: str = "Bolletta Dolomiti") -> dict:
    return {"paperless_id": paperless_id, "title": title, "created": created,
            "kind": "Bolletta", "correspondent": correspondent, "amount": amount}


def test_the_window_is_read_as_a_sentence_not_two_numbers():
    from amonhen.core.documents import window_text

    assert window_text(0, 0) == "lo stesso giorno del documento"
    assert window_text(0, 20) == "entro 20 giorni dal documento"
    assert window_text(40, 0) == "fino a 40 giorni prima del documento"
    assert window_text(40, 20) == "da 40 giorni prima a 20 giorni dopo il documento"


def test_a_rule_links_the_document_to_its_only_payment(ledger):
    ledger.set_document_rule("Dolomiti Energia", before_days=0, after_days=30, created_at="2026-11-26")
    txn = spend(ledger, "2026-11-09", "-173.30", "PAG. 3100616684", "d1")
    links = ledger.link_documents_by_rules([paperless(7, "2026-10-20", "173.30")], now="2026-11-26")
    assert links.linked == 1
    assert [(row["paperless_id"], row["by_rule"]) for row in ledger.documents_of(txn)] == [(7, 1)]


def test_a_payment_outside_the_window_is_not_taken(ledger):
    ledger.set_document_rule("Dolomiti Energia", before_days=0, after_days=10, created_at="2026-11-26")
    spend(ledger, "2026-11-09", "-173.30", "PAG. 3100616684", "d1")
    links = ledger.link_documents_by_rules([paperless(7, "2026-10-20", "173.30")], now="2026-11-26")
    assert links.linked == 0


def test_a_window_may_look_backwards_for_a_payment_made_in_advance(ledger):
    ledger.set_document_rule("Gabriele Lenti", before_days=120, after_days=10, created_at="2026-11-26")
    txn = spend(ledger, "2025-10-24", "-204.00", "To Gabriele Lenti", "d1")
    links = ledger.link_documents_by_rules(
        [paperless(9, "2025-10-31", "204.00", correspondent="Gabriele Lenti",
                   title="Ricevuta Lenti - 31/10/2025")], now="2026-11-26")
    assert links.linked == 1
    assert [row["paperless_id"] for row in ledger.documents_of(txn)] == [9]


def test_two_candidates_are_a_choice_and_a_choice_is_a_person_s(ledger):
    ledger.set_document_rule("Dolomiti Energia", before_days=0, after_days=30, created_at="2026-11-26")
    spend(ledger, "2026-11-05", "-33.09", "PAG. uno", "d1")
    spend(ledger, "2026-11-08", "-33.09", "PAG. due", "d2")
    links = ledger.link_documents_by_rules([paperless(7, "2026-10-20", "33.09")], now="2026-11-26")
    assert links.linked == 0
    assert links.ambiguous == (7,)
    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transaction_documents").fetchone()["c"] == 0


def test_the_amount_must_be_exact_to_the_cent(ledger):
    ledger.set_document_rule("Dolomiti Energia", before_days=0, after_days=30, created_at="2026-11-26")
    spend(ledger, "2026-11-09", "-173.31", "PAG.", "d1")
    assert ledger.link_documents_by_rules([paperless(7, "2026-10-20", "173.30")], now="now").linked == 0


def test_a_rule_never_takes_a_leg_of_a_transfer(ledger):
    ledger.set_document_rule("Dolomiti Energia", before_days=0, after_days=30, created_at="2026-11-26")
    first = spend(ledger, "2026-11-09", "-173.30", "giroconto", "d1")
    second = spend(ledger, "2026-11-09", "173.30", "giroconto", "d2")
    with ledger.conn:
        ledger.conn.execute(
            "INSERT INTO transfer_links (leg_a, leg_b, confidence, method) VALUES (?, ?, 'alta', 'manuale')",
            (first, second))
    assert ledger.link_documents_by_rules([paperless(7, "2026-10-20", "173.30")], now="now").linked == 0


def test_a_rule_can_ask_for_the_description_to_confirm_the_issuer(ledger):
    ledger.set_document_rule("Eni Plenitude", before_days=0, after_days=40, match_text="eni",
                             created_at="2026-11-26")
    txn = spend(ledger, "2026-06-03", "-127.42", "Eni Spa - Regolamento Monetario", "d1")
    links = ledger.link_documents_by_rules(
        [paperless(11, "2026-05-09", "127.42", correspondent="Eni Plenitude")], now="now")
    assert links.linked == 1
    assert [row["paperless_id"] for row in ledger.documents_of(txn)] == [11]


def test_the_confirming_text_may_be_an_expression_between_slashes(ledger):
    ledger.set_document_rule("ASL", before_days=40, after_days=20, match_text="/asl|pago/",
                             created_at="2026-11-26")
    txn = spend(ledger, "2026-01-15", "-40.28", "pagoPA", "d1")
    assert ledger.link_documents_by_rules(
        [paperless(21, "2026-01-14", "40.28", correspondent="ASL")], now="now").linked == 1
    assert [row["paperless_id"] for row in ledger.documents_of(txn)] == [21]


def test_a_person_unlinking_keeps_the_rule_from_putting_it_back(ledger):
    ledger.set_document_rule("Dolomiti Energia", before_days=0, after_days=30, created_at="2026-11-26")
    txn = spend(ledger, "2026-11-09", "-173.30", "PAG.", "d1")
    document = paperless(7, "2026-10-20", "173.30")
    assert ledger.link_documents_by_rules([document], now="now").linked == 1
    ledger.unlink_document(txn, 7)
    again = ledger.link_documents_by_rules([document], now="now")
    assert again.linked == 0
    assert ledger.documents_of(txn) == []


def test_a_movement_a_person_linked_is_not_a_candidate(ledger):
    ledger.set_document_rule("Dolomiti Energia", before_days=0, after_days=30, created_at="2026-11-26")
    txn = spend(ledger, "2026-11-09", "-173.30", "PAG.", "d1")
    ledger.link_document(txn, 5, title="altra bolletta", created="2026-10-20", kind="Bolletta",
                         linked_at="2026-11-26", by_rule=False)
    assert ledger.link_documents_by_rules([paperless(7, "2026-10-20", "173.30")], now="now").linked == 0
    assert [row["paperless_id"] for row in ledger.documents_of(txn)] == [5]


def test_a_document_without_an_amount_is_left_alone(ledger):
    ledger.set_document_rule("Dolomiti Energia", before_days=0, after_days=30, created_at="2026-11-26")
    spend(ledger, "2026-11-09", "-173.30", "PAG.", "d1")
    assert ledger.link_documents_by_rules([paperless(7, "2026-10-20", None)], now="now").linked == 0


def test_without_a_rule_nothing_links_itself(ledger):
    spend(ledger, "2026-11-09", "-173.30", "PAG.", "d1")
    assert ledger.link_documents_by_rules([paperless(7, "2026-10-20", "173.30")], now="now").linked == 0


def test_a_rule_window_is_written_and_replaced(ledger):
    ledger.set_document_rule("Iliad", before_days=0, after_days=20, created_at="2026-11-26")
    ledger.set_document_rule("Iliad", before_days=0, after_days=25, created_at="2026-11-26")
    rules = ledger.document_rules()
    assert [(row["correspondent"], row["after_days"]) for row in rules] == [("Iliad", 25)]
    ledger.remove_document_rule("Iliad")
    assert ledger.document_rules() == []


def test_a_negative_window_is_refused(ledger):
    with pytest.raises(ValueError):
        ledger.set_document_rule("Iliad", before_days=-1, after_days=10, created_at="now")


def test_the_api_writes_a_rule_and_links_what_it_can_decide(api):
    from amonhen.db import connect
    from amonhen.ledger import Ledger

    conn = connect(api.db_path)
    txn = movement(Ledger(conn))
    conn.close()

    written = api.put("/api/document-rules/Gabriele%20Lenti",
                      json={"before_days": 120, "after_days": 10})
    assert written.status_code == 200, written.text
    assert written.json()["window"] == "da 120 giorni prima a 10 giorni dopo il documento"

    listed = api.get("/api/document-rules").json()["rules"]
    assert [row["correspondent"] for row in listed] == ["Gabriele Lenti"]

    linked = api.post("/api/documents/link")
    assert linked.status_code == 200, linked.text
    assert linked.json() == {"linked": 1, "ambiguous": [], "skipped": 0}

    again = api.post("/api/documents/link").json()
    assert again["linked"] == 0 and again["skipped"] == 1

    document = api.get(f"/api/transactions/{txn}").json()["documents"]
    assert [item["paperless_id"] for item in document] == [42]

    assert api.delete("/api/document-rules/Gabriele%20Lenti").status_code == 200
    assert api.get("/api/document-rules").json()["rules"] == []


def test_a_rule_needs_a_non_negative_window(api):
    refused = api.put("/api/document-rules/Iliad", json={"before_days": -5, "after_days": 10})
    assert refused.status_code == 422
