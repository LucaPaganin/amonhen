"""Categories, tags and rules."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from amonhen import queries
from amonhen.api.context import AppContext
from amonhen.api.payloads import (
    _category_payload,
    _rule_fields,
    _rule_payload,
    _rule_target,
    _tag_payload,
)
from amonhen.api.schemas import (
    CategoryFlagsRequest,
    CategoryNameRequest,
    RuleRemoveRequest,
    RuleRequest,
)
from amonhen.merchants import RuleBook, categorize, preview, rule_usage


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    ledger_scope = ctx.ledger_scope

    @router.get("/api/categories")
    def categories() -> list[dict]:
        with ledger_scope() as ledger:
            rows = queries.category_rows(ledger)
            return [_category_payload(row) for row in rows]

    @router.get("/api/tags")
    def tags() -> list[dict]:
        with ledger_scope() as ledger:
            return [_tag_payload(row) for row in ledger.tags()]

    @router.post("/api/tags", status_code=201)
    def add_tag(body: CategoryNameRequest) -> dict:
        with ledger_scope() as ledger:
            try:
                return {"id": ledger.tag(body.name), "name": " ".join(body.name.split())}
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.patch("/api/tags/{tag_id}")
    def patch_tag(tag_id: int, body: CategoryFlagsRequest) -> dict:
        """The two flags of a tag: the same request as a category's."""
        if body.episodic is None and body.essential is None:
            raise HTTPException(status_code=422, detail="set episodic and/or essential")
        with ledger_scope() as ledger:
            try:
                if body.episodic is not None:
                    ledger.set_tag_flag(tag_id, "episodic", body.episodic)
                if body.essential is not None:
                    ledger.set_tag_flag(tag_id, "essential", body.essential)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"id": tag_id}

    @router.delete("/api/tags/{tag_id}")
    def delete_tag(tag_id: int) -> dict:
        with ledger_scope() as ledger:
            try:
                ledger.delete_tag(tag_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"id": tag_id}

    @router.get("/api/rules")
    def rules() -> list[dict]:
        with ledger_scope() as ledger:
            rules = RuleBook(ledger.conn).rules()
            usage = rule_usage(ledger, rules)
            return [_rule_payload(ledger, rule, usage.get(rule.id or 0, 0)) for rule in rules]
    # -- writes ------------------------------------------------------------

    @router.post("/api/categories", status_code=201)
    def add_category(body: CategoryNameRequest) -> dict:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="a category needs a name")
        with ledger_scope() as ledger:
            account_id = ledger.category(name)
            return {"id": account_id, "name": name}

    @router.patch("/api/categories/{account_id}")
    def patch_category(account_id: int, body: CategoryFlagsRequest) -> dict:
        if all(
            value is None
            for value in (
                body.name, body.episodic, body.essential, body.income, body.contribution,
                body.description,
            )
        ):
            raise HTTPException(
                status_code=422, detail="set a name, a flag or the description of the category"
            )
        with ledger_scope() as ledger:
            try:
                if body.name is not None:
                    ledger.rename_category(account_id, body.name)
                if body.episodic is not None:
                    ledger.set_category_flag(account_id, "episodic", body.episodic)
                if body.essential is not None:
                    ledger.set_category_flag(account_id, "essential", body.essential)
                if body.income is not None:
                    ledger.set_category_flag(account_id, "income", body.income)
                if body.contribution is not None:
                    ledger.set_category_flag(account_id, "contribution", body.contribution)
                if body.description is not None:
                    ledger.set_category_description(account_id, body.description)
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=404 if isinstance(exc, KeyError) else 422,
                                    detail=str(exc)) from exc
            return _category_payload(ledger.account(account_id))

    @router.post("/api/rules", status_code=201)
    def save_rule(body: RuleRequest) -> dict:
        """Write a rule and apply it now — a deleting one moves its movements to
        the trash, which is why the app asks `/api/rules/preview` first."""
        pattern = body.pattern.strip()
        if not pattern:
            raise HTTPException(status_code=422, detail="a rule needs a text to look for")
        with ledger_scope() as ledger:
            book = RuleBook(ledger.conn)
            try:
                count = book.set_rule(pattern, _rule_target(body), ledger, **_rule_fields(body))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
            saved = book.checked(pattern, _rule_target(body), ledger, **_rule_fields(body))
            stored = next(
                rule
                for rule in book.rules()
                if (rule.key, rule.account_id, rule.amount_min, rule.amount_max)
                == (saved.key, saved.account_id, saved.amount_min, saved.amount_max)
            )
            return _rule_payload(ledger, stored, count)

    @router.post("/api/rules/preview")
    def preview_rule(body: RuleRequest) -> dict:
        """What a rule would take if it were written now, writing nothing."""
        pattern = body.pattern.strip()
        if not pattern:
            raise HTTPException(status_code=422, detail="a rule needs a text to look for")
        with ledger_scope() as ledger:
            fields = _rule_fields(body)
            # A category named here is not created by a preview: only the text
            # and the conditions decide which movements a rule would take.
            rule = RuleBook(ledger.conn).checked(
                pattern, None, ledger, **{**fields, "action": "delete"}
            )
            found = preview(ledger, rule)
            return {
                "count": found["count"],
                "items": [
                    {
                        "id": row["id"],
                        "date": row["date"],
                        "amount": row["amount"],
                        "description": row["description"],
                        "account": row["account"],
                    }
                    for row in found["items"]
                ],
            }

    @router.post("/api/rules/remove")
    def remove_rule(body: RuleRemoveRequest) -> dict:
        with ledger_scope() as ledger:
            book = RuleBook(ledger.conn)
            if body.id is not None:
                try:
                    rule = book.rule(body.id)
                except KeyError as exc:
                    raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
                held = book.remove(body.id, ledger)
                return {"id": body.id, "pattern": rule.pattern, "held": held}
            pattern = (body.pattern or "").strip()
            held = book.remove_rule(pattern, ledger)
        if held is None:
            raise HTTPException(status_code=404, detail=f"no rule for {pattern!r}")
        return {"id": None, "pattern": pattern, "held": held}

    @router.post("/api/categorize")
    def run_categorize() -> dict:
        with ledger_scope() as ledger:
            return {"applied": categorize(ledger, RuleBook(ledger.conn))}

    return router
