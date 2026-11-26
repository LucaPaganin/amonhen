"""Desiderata 5.18: the copy of the ledger a phone takes offline, and the way back."""
from __future__ import annotations

import sqlite3
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query

from amonhen import queries
from amonhen.api.context import AppContext
from amonhen.api.payloads import (
    _account_payload,
    _category_payload,
    _day,
    _review_transaction,
    _tag_payload,
    _transaction,
)
from amonhen.api.schemas import OfflineQueueRequest
from amonhen.api.version import API_VERSION
from amonhen.config import load_config
from amonhen.ledger import Ledger
from amonhen.services import offline
from amonhen.settings import CREDITS_REVIEW_FROM
from amonhen.transfers import pair_candidates

# One query takes at most this many ids: SQLite caps the number of variables of a
# statement, and a long queue is more than any page the screens ask for.
CHUNK = 500
# A bound for "all of them": the queue, the proposed pairs and the waiting credits come
# whole, because a phone that is offline cannot ask for the next page.
EVERYTHING = 1_000_000


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    clock = ctx.clock
    config_path = ctx.config_path
    ledger_scope = ctx.ledger_scope

    @router.get("/api/offline/bundle")
    def bundle(
        from_date: str = Query(alias="from"),
        to_date: str = Query(alias="to"),
    ) -> dict:
        """What the phone needs to work without the server: the movements of a period
        and the whole review queue, with what each row already says (its postings,
        tags, note, transfer) and the candidates a transfer could be paired with, so
        the phone computes no matching of its own.

        One read of one ledger: the pieces agree with each other, which separate
        requests would not promise.
        """
        first, last = _day(from_date), _day(to_date)
        if first > last:
            raise HTTPException(status_code=422, detail="the period ends before it starts")
        with ledger_scope() as ledger:
            pending = {row["merchant"]: row["category"] for row in ledger.suggestions("pending")}
            backlog = queries.uncategorized_backlog(ledger)
            transfers_total, links = queries.proposed_transfers(ledger, EVERYTHING)
            credits_total, credits = queries.waiting_credits(ledger, CREDITS_REVIEW_FROM, EVERYTHING)

            period = queries.transaction_page(
                ledger,
                queries.TransactionFilter(from_date=first.isoformat(), to_date=last.isoformat()),
                everyday=False,
                limit=EVERYTHING,
                offset=0,
            ).rows
            rows: dict[int, sqlite3.Row] = {row["id"]: row for row in period}
            queue = _queue_rows(ledger, [row["id"] for row in backlog])
            rows.update({row["id"]: row for row in queue})
            rows.update({row["id"]: row for row in credits})
            for link in links:
                for leg in (link["leg_a"], link["leg_b"]):
                    rows.setdefault(leg, queries.transaction(ledger, leg))

            queued = {row["id"] for row in queue}
            candidates = _candidates(ledger, rows)
            for ids in candidates.values():
                for found in ids:
                    rows.setdefault(found, queries.transaction(ledger, found))

            return {
                "format": offline.FORMAT,
                "api_version": API_VERSION,
                "created_at": clock.now().isoformat(timespec="seconds"),
                "from": first.isoformat(),
                "to": last.isoformat(),
                "accounts": [
                    _account_payload(ledger, row["id"], clock.today())
                    for row in queries.real_account_ids(ledger)
                ],
                "categories": [_category_payload(row) for row in queries.category_rows(ledger)],
                "tags": [_tag_payload(row) for row in ledger.tags()],
                "transfer_labels": {
                    "configured": [d.destination for d in load_config(config_path).passthrough],
                    "recorded": ledger.virtual_accounts(),
                    "accounts": queries.mirror_destinations(ledger),
                },
                "transactions": [
                    _review_transaction(row, ledger, pending)
                    if row["id"] in queued
                    else _transaction(row, ledger)
                    for row in sorted(rows.values(), key=lambda r: (r["date"], r["id"]), reverse=True)
                ],
                "review": {
                    "queue": [row["id"] for row in backlog],
                    "pending": pending,
                    "proposals_total": len(pending),
                    "transfers": [
                        {
                            "confidence": link["confidence"],
                            "method": link["method"],
                            "leg_a": link["leg_a"],
                            "leg_b": link["leg_b"],
                        }
                        for link in links
                    ],
                    "transfers_total": transfers_total,
                    "credits": [row["id"] for row in credits],
                    "credits_total": credits_total,
                    "accounts": [
                        {"id": row["id"], "name": row["name"]}
                        for row in queries.backlog_accounts(ledger)
                    ],
                },
                "candidates": {str(key): ids for key, ids in candidates.items()},
            }

    @router.post("/api/offline/preview")
    def preview(body: OfflineQueueRequest) -> dict:
        """What sending these operations would do, written nowhere."""
        operations = _operations(body)
        with ledger_scope() as ledger:
            return {"outcomes": [asdict(o) for o in offline.preview(ledger, operations)]}

    @router.post("/api/offline/commit")
    def commit(body: OfflineQueueRequest) -> dict:
        """Apply what can be applied, in one transaction. A conflict is written only
        when the request answers it with the value the preview showed."""
        operations = _operations(body)
        resolutions = {
            r.id: offline.Resolution(choice=r.choice, seen=r.seen) for r in body.resolutions
        }
        with ledger_scope() as ledger:
            return {
                "outcomes": [asdict(o) for o in offline.commit(ledger, operations, resolutions)]
            }

    return router


def _operations(body: OfflineQueueRequest) -> list[offline.Operation]:
    # A format this server does not know is the whole queue's problem, not an
    # outcome: the queue stays on the phone.
    if body.format != offline.FORMAT:
        raise HTTPException(
            status_code=409,
            detail=f"the queue is in format {body.format}, this server reads {offline.FORMAT}",
        )
    try:
        return [offline.operation(o.model_dump()) for o in body.operations]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _queue_rows(ledger: Ledger, ids: list[int]) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    for start in range(0, len(ids), CHUNK):
        rows += queries.queue_rows(ledger, ids[start : start + CHUNK])
    return rows


def _candidates(ledger: Ledger, rows: dict[int, sqlite3.Row]) -> dict[int, list[int]]:
    """The legs each loose movement could be paired with: the server's own search,
    run once per movement the phone holds. It scans the ledger by amount for each, which
    is fine for a personal ledger and is the first thing to index if it ever is not."""
    found: dict[int, list[int]] = {}
    for row in rows.values():
        if row["status"] != "BOOK" or ledger.is_transfer(row["id"]):
            continue
        ids = [candidate["id"] for candidate in pair_candidates(ledger, row["id"])]
        if ids:
            found[row["id"]] = ids
    return found
