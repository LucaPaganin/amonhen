"""Accounts: the list, the virtual ones, adding and removing, balances, the opening, the trash."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException

from amonhen import queries
from amonhen.api.context import AppContext
from amonhen.api.payloads import (
    _account_payload,
    _amount,
    _day,
    _deleted_payload,
    _require_real_account,
    _require_transaction,
    _transaction,
)
from amonhen.api.schemas import (
    AccountFlagsRequest,
    AccountRequest,
    DeclarationRequest,
    ValuationRequest,
)
from amonhen.config import load_config, remove_account
from amonhen.merchants import deleting_rule
from amonhen.models import Account, format_decimal, parse_decimal


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    clock = ctx.clock
    config_path = ctx.config_path
    ledger_scope = ctx.ledger_scope

    @router.get("/api/accounts")
    def accounts() -> list[dict]:
        with ledger_scope() as ledger:
            return [_account_payload(ledger, row["id"], clock.today()) for row in queries.real_account_ids(ledger)]

    @router.get("/api/virtual-accounts")
    def virtual_accounts() -> list[dict]:
        """Where the money that is neither spending nor income went.

        A movement recorded as an own transfer, or as passing through, posts its
        other side to a virtual account: the house cheques sit on one, a
        mistaken payment and its return on another. Those accounts were nowhere
        on screen, so what had left the burn could not be found again. Each
        carries what it holds — the sum of its postings, positive when money
        went in — and how many movements put it there. `Transfer clearing` is
        left out: it is how a pair between two real accounts balances, it always
        nets to zero, and it is not a place money went.
        """
        with ledger_scope() as ledger:
            rows = queries.virtual_account_usage(ledger)
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "balance": format_decimal(queries.posted_on(ledger, row["id"])),
                    "movements": row["movements"],
                    "first_date": row["first_date"],
                    "last_date": row["last_date"],
                }
                for row in rows
            ]

    @router.post("/api/accounts", status_code=201)
    def create_account(body: AccountRequest) -> dict:
        """Add a real account by hand: the broker, or a bank that is not connected.

        A name already in the ledger is refused instead of reused — `ensure_account`
        would quietly hand back the existing account and the caller would believe
        it had created one.
        """
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="an account needs a name")
        opening = _amount(body.opening_balance)
        opening_date = _day(body.opening_date) if body.opening_date else None
        if opening is not None and opening_date is None:
            raise HTTPException(
                status_code=422, detail="an opening balance needs the date it refers to"
            )
        with ledger_scope() as ledger:
            if ledger.find_account(name=name) is not None:
                raise HTTPException(status_code=422, detail=f"{name!r} already exists")
            account_id = ledger.ensure_account(
                Account(
                    name=name,
                    type="real",
                    institution=body.institution,
                    currency=body.currency or "EUR",
                    opening_balance=opening,
                    opening_date=opening_date,
                )
            )
            return _account_payload(ledger, account_id, clock.today())

    @router.delete("/api/accounts/{account_id}")
    def delete_account(account_id: int) -> dict:
        """Delete a real account with its movements, and stop syncing it.

        A connected account is also taken out of `accounts.json`, or the next sync
        would create it again and import its history from the bank. Nothing is
        kept to restore: the snapshot is the way back.
        """
        with ledger_scope() as ledger:
            try:
                name = ledger.account(account_id)["name"]
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
            movements = ledger.delete_account(account_id)
        disconnected = False
        try:
            configured = load_config(config_path).accounts
        except (FileNotFoundError, ValueError, KeyError):
            configured = []
        for entry in configured:
            if entry.name == name:
                remove_account(config_path, entry.account_uid)
                disconnected = True
        return {"name": name, "movements": movements, "disconnected": disconnected}

    @router.put("/api/accounts/{account_id}/declaration")
    def declare_balance(account_id: int, body: DeclarationRequest) -> dict:
        """Record a balance a person read off the bank, and answer with the check.

        The source carries which of the bank's two figures it is
        (`manual:available`), exactly like a hand-typed declaration on the
        command line, so the assertion is made against the computed balance that
        means the same thing.
        """
        declared = _amount(body.balance)
        if declared is None:
            raise HTTPException(status_code=422, detail="a declaration needs an amount")
        with ledger_scope() as ledger:
            _require_real_account(ledger, account_id)
            ledger.record_declared_balance(
                account_id, _day(body.date), declared, f"manual:{body.kind}"
            )
            return _account_payload(ledger, account_id, clock.today())

    @router.post("/api/accounts/{account_id}/valuation")
    def record_valuation(account_id: int, body: ValuationRequest) -> dict:
        """Say what an investment account added by hand is worth, and book the return.

        The difference from the ledger's balance becomes a movement against
        `Investimenti` (`Ledger.record_valuation`), so the check agrees
        and what the market did is on the books instead of in the opening.
        """
        value = _amount(body.value)
        if value is None:
            raise HTTPException(status_code=422, detail="a valuation needs an amount")
        with ledger_scope() as ledger:
            _require_real_account(ledger, account_id)
            try:
                difference, _ = ledger.record_valuation(account_id, _day(body.date), value)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {"difference": format_decimal(difference), "account": _account_payload(ledger, account_id, clock.today())}

    @router.post("/api/accounts/{account_id}/opening/preview")
    def preview_opening(account_id: int, body: DeclarationRequest) -> dict:
        """What anchoring to this figure would move, and nothing written.

        An anchor makes the 5.4 check agree by construction: whatever the ledger
        is missing or holds twice goes into the opening and is never reported
        again. The app shows `change` before it asks for the write, so that a
        difference is folded away knowingly — the sum is the server's, like
        every other.
        """
        declared = _amount(body.balance)
        if declared is None:
            raise HTTPException(status_code=422, detail="an opening needs an amount")
        with ledger_scope() as ledger:
            _require_real_account(ledger, account_id)
            row = ledger.account(account_id)
            opening, opening_date = ledger.opening_from(
                account_id, _day(body.date), declared, body.kind
            )
            current = parse_decimal(row["opening_balance"]) if row["opening_balance"] else None
            return {
                "current_balance": format_decimal(current) if current is not None else None,
                "current_date": row["opening_date"],
                "opening_balance": format_decimal(opening),
                "opening_date": opening_date.isoformat(),
                "change": format_decimal(opening - (current or Decimal(0))),
            }

    @router.put("/api/accounts/{account_id}/opening")
    def set_opening(account_id: int, body: DeclarationRequest) -> dict:
        """Derive the opening balance from a declared figure: the `anchor` path.

        The declaration is recorded as well, tagged `anchor:<kind>`, so the
        check the derivation produces stays visible instead of vanishing with
        the request.
        """
        declared = _amount(body.balance)
        if declared is None:
            raise HTTPException(status_code=422, detail="an opening needs an amount")
        with ledger_scope() as ledger:
            _require_real_account(ledger, account_id)
            as_of = _day(body.date)
            ledger.anchor_opening(account_id, as_of, declared, body.kind)
            ledger.record_declared_balance(account_id, as_of, declared, f"anchor:{body.kind}")
            return _account_payload(ledger, account_id, clock.today())

    @router.get("/api/deleted")
    def deleted() -> list[dict]:
        """The movements a person deleted and has not brought back.

        Answered whole rather than per account: the Conti section asks once and
        groups them under the account each one belonged to, which is where the
        flag that would bring them all back also lives.
        """
        with ledger_scope() as ledger:
            return [_deleted_payload(row) for row in ledger.deleted_transactions()]

    @router.post("/api/deleted/{deleted_id}/restore")
    def restore_deleted(deleted_id: int) -> dict:
        """Put one deleted movement back, with the note it had when it went.

        Refused while a rule that deletes still matches it: the movement would be
        back in the trash at the next sync, and a restore that undoes itself is
        not one. The rule is named, so the person knows what to change.
        """
        with ledger_scope() as ledger:
            row = queries.deleted_movement(ledger, deleted_id)
            if row is not None:
                rule = deleting_rule(
                    ledger, row["description"], row["account_id"], parse_decimal(row["amount"])
                )
                if rule is not None:
                    raise HTTPException(
                        status_code=409,
                        detail=f"la regola «{rule.pattern}» lo cancellerebbe di nuovo: "
                        "togli o cambia la regola prima di ripristinarlo",
                    )
            try:
                transaction_id = ledger.restore_deleted(deleted_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return _transaction(_require_transaction(ledger, transaction_id), ledger)

    @router.patch("/api/accounts/{account_id}")
    def patch_account(account_id: int, body: AccountFlagsRequest) -> dict:
        """Flip an account's own flags, and answer with the account.

        `investment` marks the broker, whose cash is declared by hand;
        `reimport_deleted` decides whether a movement deleted here may
        come back at the next sync; `computed_balance` makes the net worth read
        the account's balance from its postings, for an account no bank declares
        one for; `unreported_funding` lets a transfer rule write the other half
        on a connected wallet that never reports its top-ups (PayPal paid with a
        card). They are decisions about the account, so they are written here
        rather than on a movement, and the answer is the account as every other
        endpoint reads it.
        """
        if (
            body.investment is None
            and body.reimport_deleted is None
            and body.computed_balance is None
            and body.unreported_funding is None
        ):
            raise HTTPException(status_code=422, detail="nothing to set")
        with ledger_scope() as ledger:
            try:
                if body.investment is not None:
                    ledger.set_investment(account_id, body.investment)
                if body.reimport_deleted is not None:
                    ledger.set_reimport_deleted(account_id, body.reimport_deleted)
                if body.computed_balance is not None:
                    ledger.set_computed_balance(account_id, body.computed_balance)
                if body.unreported_funding is not None:
                    ledger.set_unreported_funding(account_id, body.unreported_funding)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return _account_payload(ledger, account_id, clock.today())

    return router
