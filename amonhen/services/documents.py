"""Desiderata 5.16-bis: the documents Paperless holds, and the movements that pay them.

Paperless answers a page at a time; the rules work on the whole archive, because
a payment can only be found by looking at every movement the ledger has. Reading
the pages costs one request per hundred documents, and the rules skip the
documents already linked before anything else.
"""
from __future__ import annotations

from amonhen.ledger import Ledger
from amonhen.ledger.documents import DocumentLinks

# How many documents one request asks Paperless for: enough to keep the number
# of requests low, small enough that one page is never a wall in the log.
PAGE = 100


def link_documents(ledger: Ledger, source, *, now: str) -> DocumentLinks:
    """Read what Paperless holds and let the rules link the certain couplings."""
    documents: list[dict] = []
    offset = 0
    while True:
        found, total = source.invoices("", offset, PAGE)
        documents.extend(found)
        offset += len(found)
        if not found or offset >= total:
            break
    return ledger.link_documents_by_rules(documents, now=now)
