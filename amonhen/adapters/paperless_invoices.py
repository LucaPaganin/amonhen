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
        params = {
            "query": query.strip(),
            "page_size": limit,
            "ordering": "-created",
            "fields": "id,title,created,document_type,correspondent",
        }
        page = self._get(f"{self.base}/api/documents/", params)
        return [self._document(row) for row in page.get("results", [])]

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
