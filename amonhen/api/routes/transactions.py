"""Movements: the list, one movement, and the writes on one or many."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from amonhen import queries
from amonhen import db
from amonhen.api.context import AppContext
from amonhen.api.payloads import _require_transaction, _size, _transaction
from amonhen.api.schemas import (
    BatchCategoryRequest,
    BatchTagRequest,
    CategoryRequest,
    DocumentRuleRequest,
    NotesRequest,
    SplitsRequest,
    TagsRequest,
    TransactionIdsRequest,
)
from amonhen.models import parse_decimal
from amonhen.composition import invoice_source
from amonhen.ports.portfolio import SourceUnavailable


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    ledger_scope = ctx.ledger_scope

    @router.get("/api/transactions")
    def transactions(
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
        account_id: int | None = None,
        category: str | None = None,
        status: str | None = None,
        search: str | None = None,
        transfer: bool | None = None,
        virtual_account_id: int | None = None,
        tag: str | None = None,
        amount_min: str | None = None,
        amount_max: str | None = None,
        everyday: bool = False,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict:
        """A page of movements. `everyday` leaves out what only moves own money:
        the legs of a transfer, and everything on a deposit whose balance is its
        movements, the daily interest included. `hidden` says how many that was,
        so the list can never look shorter than the ledger without saying so.
        """
        filters = queries.TransactionFilter(
            from_date=from_date, to_date=to_date, account_id=account_id, category=category,
            status=status, search=search, transfer=transfer,
            virtual_account_id=virtual_account_id, tag=tag,
            amount_min=_size(amount_min), amount_max=_size(amount_max),
        )
        with ledger_scope() as ledger:
            page = queries.transaction_page(
                ledger, filters, everyday=everyday, limit=limit, offset=offset
            )
            return {
                "total": page.total,
                "hidden": page.hidden,
                "limit": limit,
                "offset": offset,
                "items": [_transaction(row, ledger) for row in page.rows],
            }

    @router.get("/api/transactions/{transaction_id}")
    def transaction(transaction_id: int) -> dict:
        with ledger_scope() as ledger:
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @router.put("/api/transactions/{transaction_id}/splits")
    def put_splits(transaction_id: int, body: SplitsRequest) -> dict:
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            if ledger.is_transfer(transaction_id):
                raise HTTPException(
                    status_code=409,
                    detail="the transaction is a leg of a transfer: review the link first",
                )
            try:
                ledger.set_splits(
                    transaction_id,
                    [(ledger.category(item.category), parse_decimal(item.amount)) for item in body.splits],
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @router.delete("/api/transactions/{transaction_id}")
    def delete_transaction(transaction_id: int) -> dict:
        """Take a movement out of the ledger, remembered as a tombstone.

        The row goes: this is not a flag on a movement that stays visible. What
        it carried — the bank's payload, the note, the identity the ledger
        dedupes by — is copied aside, so the next sync does not write it back
        and a person can still see and undo the deletion.
        """
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            deletion = ledger.delete_transaction(transaction_id)
            return {"id": deletion.transaction_id, "unlinked_pair": deletion.unlinked_pair}

    @router.post("/api/transactions/delete")
    def delete_transactions(body: TransactionIdsRequest) -> dict:
        """Delete several movements at once — a page selected in Movimenti.

        Each one as the single delete does it, tombstone and all, in one
        transaction; an id the ledger does not hold refuses the whole batch.
        """
        if not body.ids:
            raise HTTPException(status_code=422, detail="no movement to delete")
        with ledger_scope() as ledger:
            try:
                deletions = ledger.delete_transactions(body.ids)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
            return {
                "deleted": len(deletions),
                "unlinked_pairs": sum(deletion.unlinked_pair for deletion in deletions),
            }

    @router.post("/api/transactions/category")
    def categorize_transactions(body: BatchCategoryRequest) -> dict:
        """Give several movements one category, as a person's own decision.

        A transfer leg and a split are skipped and counted: one category would
        hide the transfer or throw the split away, and each is decided by opening
        it.
        """
        if not body.ids:
            raise HTTPException(status_code=422, detail="no movement to categorize")
        with ledger_scope() as ledger:
            for transaction_id in body.ids:
                _require_transaction(ledger, transaction_id)
            account = ledger.category(body.category)
            categorized = 0
            with db.deferred_commits(ledger.conn):
                for transaction_id in dict.fromkeys(body.ids):
                    if ledger.is_transfer(transaction_id) or len(ledger.splits(transaction_id)) > 1:
                        continue
                    ledger.set_category(transaction_id, account)
                    categorized += 1
            return {"categorized": categorized, "skipped": len(set(body.ids)) - categorized}

    @router.post("/api/transactions/tag")
    def tag_transactions(body: BatchTagRequest) -> dict:
        """Put one tag on several movements, as a person's own decision."""
        if not body.ids:
            raise HTTPException(status_code=422, detail="no movement to tag")
        with ledger_scope() as ledger:
            for transaction_id in body.ids:
                _require_transaction(ledger, transaction_id)
            try:
                with db.deferred_commits(ledger.conn):
                    for transaction_id in dict.fromkeys(body.ids):
                        ledger.add_tag(transaction_id, body.tag)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {"tagged": len(set(body.ids))}

    @router.put("/api/transactions/{transaction_id}/tags")
    def put_tags(transaction_id: int, body: TagsRequest) -> dict:
        """Make a movement carry exactly these tags."""
        with ledger_scope() as ledger:
            row = _require_transaction(ledger, transaction_id)
            ledger.set_tags(row["id"], body.tags)
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @router.get("/api/invoices")
    def invoices(
        q: str = "",
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict:
        """The documents that justify a payment, and which movements already pay them."""
        try:
            source = invoice_source()
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if source is None:
            return {"configured": False, "items": [], "total": 0, "limit": limit, "offset": offset}
        try:
            found, total = source.invoices(q, offset, limit)
        except SourceUnavailable as exc:
            raise HTTPException(status_code=502, detail=f"Paperless non risponde: {exc}") from exc
        with ledger_scope() as ledger:
            links = ledger.movements_of_documents([item["paperless_id"] for item in found])
        return {
            "configured": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [
                {
                    **item,
                    "movements": [
                        {"id": row["id"], "date": row["date"], "amount": row["amount"],
                         "description": row["description"]}
                        for row in links.get(item["paperless_id"], [])
                    ],
                }
                for item in found
            ],
        }

    @router.get("/api/documents/search")
    def search_documents(q: str = "") -> dict:
        """What Paperless holds for this search: the paperwork behind a movement."""
        try:
            source = invoice_source()
        except ValueError as exc:  # a misconfigured URL or token
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if source is None:
            return {"configured": False, "items": []}
        try:
            return {"configured": True, "items": source.search(q)}
        except SourceUnavailable as exc:
            raise HTTPException(status_code=502, detail=f"Paperless non risponde: {exc}") from exc

    @router.put("/api/transactions/{transaction_id}/documents/{paperless_id}")
    def link_document(transaction_id: int, paperless_id: int) -> dict:
        """Attach a Paperless document to the movement, keeping its title as it was."""
        try:
            source = invoice_source()
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if source is None:
            raise HTTPException(status_code=503, detail="Paperless non configurato")
        try:
            document = source.one(paperless_id)
        except SourceUnavailable as exc:
            raise HTTPException(status_code=502, detail=f"Paperless non risponde: {exc}") from exc
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            ledger.link_document(
                transaction_id, paperless_id, title=document["title"], created=document["created"],
                kind=document["kind"], linked_at=ctx.clock.now().isoformat(timespec="seconds"),
            )
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @router.delete("/api/transactions/{transaction_id}/documents/{paperless_id}")
    def unlink_document(transaction_id: int, paperless_id: int) -> dict:
        """The document is not this movement's: the link goes, the document stays in Paperless."""
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            ledger.unlink_document(transaction_id, paperless_id)
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @router.put("/api/transactions/{transaction_id}/notes")
    def put_notes(transaction_id: int, body: NotesRequest) -> dict:
        """Write the local note of a movement, or clear it.

        The only field of a movement a person may rewrite: everything else is
        what the bank said, and the 5.4 assertion compares that statement with
        the ledger, so a hand-edited amount or date would break the one check
        that says whether the numbers can be trusted.
        """
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            ledger.set_notes(transaction_id, body.notes)
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @router.post("/api/transactions/{transaction_id}/category")
    def set_category(transaction_id: int, body: CategoryRequest) -> dict:
        with ledger_scope() as ledger:
            _require_transaction(ledger, transaction_id)
            if ledger.is_transfer(transaction_id):
                raise HTTPException(
                    status_code=409,
                    detail="the transaction is a leg of a transfer: review the link first",
                )
            ledger.set_category(transaction_id, ledger.category(body.category))
            return _transaction(queries.transaction(ledger, transaction_id), ledger)

    # -- the rules that link a document to its payment (desiderata 5.16-bis) ----

    @router.get("/api/document-rules")
    def document_rules() -> dict:
        """One rule per issuer, each window written as a person would say it."""
        from amonhen.core.documents import window_text

        with ledger_scope() as ledger:
            return {"rules": [
                {
                    "correspondent": row["correspondent"],
                    "before_days": row["before_days"],
                    "after_days": row["after_days"],
                    "window": window_text(row["before_days"], row["after_days"]),
                    "match_text": row["match_text"],
                    "active": bool(row["active"]),
                }
                for row in ledger.document_rules()
            ]}

    @router.put("/api/document-rules/{correspondent}")
    def put_document_rule(correspondent: str, body: DocumentRuleRequest) -> dict:
        """Write how far from a document its payment may sit, for one issuer."""
        from amonhen.core.documents import window_text

        with ledger_scope() as ledger:
            try:
                ledger.set_document_rule(
                    correspondent, before_days=body.before_days, after_days=body.after_days,
                    match_text=body.match_text, active=body.active,
                    created_at=ctx.clock.now().isoformat(timespec="seconds"),
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            row = ledger.document_rule(correspondent)
            return {
                "correspondent": row["correspondent"],
                "before_days": row["before_days"],
                "after_days": row["after_days"],
                "window": window_text(row["before_days"], row["after_days"]),
                "match_text": row["match_text"],
                "active": bool(row["active"]),
            }

    @router.delete("/api/document-rules/{correspondent}")
    def delete_document_rule(correspondent: str) -> dict:
        """Forget one issuer's rule: its documents go back to linking by hand."""
        with ledger_scope() as ledger:
            ledger.remove_document_rule(correspondent)
            return {"removed": correspondent}

    @router.post("/api/documents/link")
    def link_documents() -> dict:
        """Run the rules over what Paperless holds, and say what they could not decide."""
        from amonhen.services.documents import link_documents as run

        try:
            source = invoice_source()
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if source is None:
            raise HTTPException(status_code=503, detail="Paperless non configurato")
        try:
            with ledger_scope() as ledger:
                links = run(ledger, source, now=ctx.clock.now().isoformat(timespec="seconds"))
                return {"linked": links.linked, "ambiguous": list(links.ambiguous),
                        "skipped": links.skipped}
        except SourceUnavailable as exc:
            raise HTTPException(status_code=502, detail=f"Paperless non risponde: {exc}") from exc

    return router
