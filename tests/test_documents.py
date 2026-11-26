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
