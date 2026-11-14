"""Movements: the list, one movement, and the writes on one or many."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from amonhen import db
from amonhen.api.context import AppContext
from amonhen.api.payloads import _require_transaction, _size, _transaction, _transaction_filters
from amonhen.api.schemas import (
    BatchCategoryRequest,
    BatchTagRequest,
    CategoryRequest,
    NotesRequest,
    SplitsRequest,
    TagsRequest,
    TransactionIdsRequest,
)
from amonhen.models import parse_decimal


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
        filters = (from_date, to_date, account_id, category, status, search, transfer,
                   virtual_account_id, tag, _size(amount_min), _size(amount_max))
        where, params = _transaction_filters(*filters, everyday=everyday)
        with ledger_scope() as ledger:
            count = (
                "SELECT COUNT(*) AS c FROM transactions t"
                " JOIN accounts a ON a.id = t.account_id "
            )
            total = ledger.conn.execute(count + where, params).fetchone()["c"]
            hidden = 0
            if everyday:
                unfiltered, unfiltered_params = _transaction_filters(*filters)
                hidden = (
                    ledger.conn.execute(count + unfiltered, unfiltered_params).fetchone()["c"]
                    - total
                )
            rows = ledger.conn.execute(
                f"""SELECT t.* FROM transactions t JOIN accounts a ON a.id = t.account_id
                    {where} ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?""",
                params + [limit, offset],
            ).fetchall()
            return {
                "total": total,
                "hidden": hidden,
                "limit": limit,
                "offset": offset,
                "items": [_transaction(row, ledger) for row in rows],
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
            return _transaction(ledger.conn.execute(
                "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
            ).fetchone(), ledger)

    return router
