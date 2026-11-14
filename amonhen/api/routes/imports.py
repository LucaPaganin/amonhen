"""The CSV import and its preview."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from amonhen.api.context import AppContext
from amonhen.api.payloads import _import_account, _passthrough, _refuse_oversized
from amonhen.api.schemas import CsvImportRequest
from amonhen.csv_import import (
    csv_file,
    missing_from_mapping,
    preview_csv,
    profile_from_mapping,
    read_mapped,
)
from amonhen.services.ingest import settle_after_ingest


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    config_path = ctx.config_path
    ledger_scope = ctx.ledger_scope

    @router.post("/api/import/csv/preview")
    def csv_import_preview(body: CsvImportRequest) -> dict:
        """What the statement would become, before anything is written.

        The column names come back even when the mapping is not finished: they
        are what the screen needs in order to finish choosing.
        """
        _refuse_oversized(body.content)
        mapping = body.mapping.model_dump()
        problem = missing_from_mapping(mapping)
        with ledger_scope() as ledger:
            account = _import_account(ledger, body.account)
            with csv_file(body.content) as path:
                payload = preview_csv(
                    path,
                    mapping=mapping,
                    account_id=account["id"],
                    balancing_account_id=ledger.uncategorized(),
                )
        return {"ready": problem is None, "problem": problem, **payload}
    @router.post("/api/import/csv")
    def csv_import(body: CsvImportRequest) -> dict:
        """Write the mapped rows, then settle them as `import` and the sync do.

        The rows land, then `settle_after_ingest`: the transfer rules, the
        matcher, the configured passthrough labels, the rules on what is left.
        """
        _refuse_oversized(body.content)
        mapping = body.mapping.model_dump()
        problem = missing_from_mapping(mapping)
        if problem is not None:
            raise HTTPException(status_code=422, detail=problem)
        profile = profile_from_mapping(mapping)
        with ledger_scope() as ledger:
            account = _import_account(ledger, body.account)
            with csv_file(body.content) as path:
                transactions, errors = read_mapped(
                    path,
                    profile=profile,
                    account_id=account["id"],
                    balancing_account_id=ledger.uncategorized(),
                    source_file=body.filename or None,
                )
            counts = ledger.record_batch(transactions)
            settled = settle_after_ingest(ledger, _passthrough(config_path))
            return {
                "account": account["name"],
                "filename": body.filename,
                "parsed": len(transactions),
                "actions": counts,
                "rejected": [{"line": error.line, "reason": error.reason} for error in errors],
                "links": settled.linked,
                "passthrough": settled.passthrough,
                "rules": settled.categorized,
            }

    return router
