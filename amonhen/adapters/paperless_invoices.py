"""Paperless as the place a movement's paperwork lives: searched, not listed.

The ledger knows the movement; Paperless knows the invoice, the receipt, the
bill. A person searches by what they remember — the issuer, the amount, the
month — and picks the document: nothing here guesses, because the wrong
paperwork is worse than none.
"""
from __future__ import annotations

import requests

from amonhen.ports.portfolio import SourceUnavailable

# How many documents one search offers: enough to recognise the right one,
# few enough to stay a choice instead of a wall.
SEARCH_LIMIT = 15

# The documents that justify a payment. A referto or a contract is not one, and
# without this list the view would be a dump of the whole archive.
INVOICE_TYPES = ("Fattura", "Ricevuta sanitaria", "Bolletta")

# The custom field the household writes the total into, when it is there.
AMOUNT_FIELD = "Importo"


class PaperlessInvoices:
    """The documents Paperless holds, found by a search and read one by one."""

    def __init__(self, base_url: str, token: str, *, session: requests.Session | None = None,
                 timeout: float = 30) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.http = session or requests.Session()
        self.http.headers.update({"Authorization": f"Token {token}", "Accept": "application/json"})
        self._names: dict[str, dict[int, str]] = {}

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
        """The documents whose title or text carries the words, newest first.

        Not Paperless's own `query=` search: that one answers nothing for a
        reader who is not the owner of the documents — its full-text index is
        filtered as if the reader owned none — while the two `icontains` filters
        see exactly what the permissions allow. Two questions, one answer: the
        title and the text, merged by document.

        An empty search is the archive's latest documents, which is what a person
        who does not know what to type needs to see.
        """
        text = query.strip()
        fields = "id,title,created,document_type,correspondent"
        if not text:
            page = self._get(f"{self.base}/api/documents/",
                             {"page_size": limit, "ordering": "-created", "fields": fields})
            return [self._document(row) for row in page.get("results", [])]

        found: dict[int, dict] = {}
        for param in ("title__icontains", "content__icontains"):
            page = self._get(f"{self.base}/api/documents/",
                             {param: text, "page_size": limit, "ordering": "-created", "fields": fields})
            for row in page.get("results", []):
                found.setdefault(row["id"], row)
        newest = sorted(found.values(), key=lambda row: row.get("created") or "", reverse=True)
        return [self._document(row) for row in newest[:limit]]

    def invoices(self, query: str = "", offset: int = 0, limit: int = 20) -> tuple[list[dict], int]:
        """The documents that justify a payment, the newest first, and how many there are.

        The search looks at the title: here the titles say who sent it and when
        ("Fattura Lenti - giugno/luglio 2026"), which is what a person types. The
        amount is on the row, to be read rather than searched.
        """
        types = [identifier for identifier in
                 (self._id_of("document_types", name) for name in INVOICE_TYPES)
                 if identifier is not None]
        params = {
            "page": offset // limit + 1,
            "page_size": limit,
            "ordering": "-created",
            "fields": "id,title,created,document_type,correspondent,custom_fields",
        }
        if types:
            params["document_type__id__in"] = ",".join(str(identifier) for identifier in types)
        text = query.strip()
        if text:
            params["title__icontains"] = text
        page = self._get(f"{self.base}/api/documents/", params)
        return ([self._invoiced(row) for row in page.get("results", [])], int(page.get("count") or 0))

    def one(self, paperless_id: int) -> dict:
        """The document as it will be snapshotted on the movement."""
        return self._document(self._get(f"{self.base}/api/documents/{paperless_id}/"))

    # -- private helpers ---------------------------------------------------

    def _document(self, row: dict) -> dict:
        return {
            "paperless_id": row["id"],
            "title": row.get("title") or "",
            "created": row.get("created"),
            "kind": self._name("document_types", row.get("document_type")),
            "correspondent": self._name("correspondents", row.get("correspondent")),
        }

    def _invoiced(self, row: dict) -> dict:
        document = self._document(row)
        document["amount"] = self._amount(row.get("custom_fields") or [])
        return document

    def _amount(self, fields: list[dict]) -> str | None:
        """The total the document states, when the archive has the field."""
        for item in fields:
            if self._name("custom_fields", item.get("field")) == AMOUNT_FIELD and item.get("value"):
                return str(item["value"])
        return None

    def _id_of(self, resource: str, name: str) -> int | None:
        for identifier, found in self._names_of(resource).items():
            if found == name:
                return identifier
        return None

    def _name(self, resource: str, identifier: int | None) -> str | None:
        return None if identifier is None else self._names_of(resource).get(identifier)

    def _names_of(self, resource: str) -> dict[int, str]:
        """Id to name, asked once per process: the taxonomy changes rarely."""
        if resource not in self._names:
            page = self._get(f"{self.base}/api/{resource}/", {"page_size": 500, "fields": "id,name"})
            self._names[resource] = {row["id"]: row["name"] for row in page.get("results", [])}
        return self._names[resource]

    def _get(self, url: str, params: dict | None = None) -> dict:
        try:
            response = self.http.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SourceUnavailable(f"Paperless did not answer: {exc}") from exc
        if response.status_code != 200:
            raise SourceUnavailable(f"Paperless answered {response.status_code}: {response.text[:200]}")
        return response.json()
