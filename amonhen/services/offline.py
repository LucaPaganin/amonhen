"""Desiderata 5.18: what was done on the phone without a network, decided against the ledger.

An operation is one thing a person did offline, with the value the phone saw when it
downloaded (its *base*). The server never trusts that the ledger is still as it was:
each operation is compared with what the ledger holds now, and the comparison is the
whole conflict test — no version column exists for it.

`preview` and `commit` run the same loop. The preview applies what can be applied
inside a transaction it then rolls back, so what it says is what the commit does,
operation by operation, down to an operation that depends on an earlier one.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation

from amonhen import queries
from amonhen.db import LedgerConnection
from amonhen.ledger import Ledger
from amonhen.models import format_decimal, parse_decimal

# The shape of an operation, which the phone and the server must agree on. It moves
# on purpose and by itself, apart from `API_VERSION`: a server that does not know a
# format refuses the queue and leaves it on the phone.
FORMAT = 1

KINDS = ("category", "splits", "tag_add", "tag_remove", "note", "delete", "pair", "review")

APPLICABLE = "applicabile"
ALREADY = "gia_cosi"
CONFLICT = "conflitto"
GONE = "sparita"
INVALID = "non_valida"

# What a person may answer to a conflict.
KEEP_MINE = "mine"
KEEP_SERVER = "server"


@dataclass(frozen=True)
class Operation:
    id: str
    kind: str
    transaction_id: int
    value: dict
    base: dict


@dataclass(frozen=True)
class Resolution:
    """The answer to a conflict. `seen` is the token of the server's value the person
    looked at, so an answer to one value is never applied to another."""

    choice: str
    seen: str | None = None


@dataclass(frozen=True)
class Outcome:
    id: str
    state: str
    message: str | None = None
    # The server's value, for a conflict, and the token that names it.
    current: object = None
    token: str | None = None
    # Written to the ledger (a preview writes nothing, and says what a commit would).
    applied: bool = False
    # A conflict the person settled in the server's favour: nothing to write, and the
    # operation leaves the queue.
    dropped: bool = False


@dataclass(frozen=True)
class _Verdict:
    state: str
    message: str | None = None
    current: object = None


class _Rollback(Exception):
    """Ends a preview: everything it applied is taken back."""


def operation(raw: dict) -> Operation:
    """An operation from its JSON, or the reason it is malformed."""
    kind = raw.get("kind")
    if kind not in KINDS:
        raise ValueError(f"unknown operation kind {kind!r}")
    op = Operation(
        id=str(raw["id"]),
        kind=kind,
        transaction_id=int(raw["transaction_id"]),
        value=dict(raw.get("value") or {}),
        base=dict(raw.get("base") or {}),
    )
    _check_shape(op)
    return op


def preview(ledger: Ledger, operations: Sequence[Operation]) -> list[Outcome]:
    """What a commit of these operations would do, written nowhere."""
    conn = ledger.conn
    if not isinstance(conn, LedgerConnection):
        raise TypeError("a preview needs a connection that can hold back its commits")
    outcomes: list[Outcome] = []
    try:
        with conn.deferred_commits():
            outcomes = _run(ledger, operations, {})
            raise _Rollback
    except _Rollback:
        pass
    # "Applicable" is what it would do: nothing was written.
    return [replace(outcome, applied=False) for outcome in outcomes]


def commit(
    ledger: Ledger, operations: Sequence[Operation], resolutions: dict[str, Resolution]
) -> list[Outcome]:
    """Apply what can be applied, in one transaction, and say what happened to each.

    An operation whose base changed since the preview is a conflict again and is not
    written; a conflict is written only when the person answered it, and answered the
    value the server still holds.
    """
    conn = ledger.conn
    if not isinstance(conn, LedgerConnection):
        raise TypeError("a commit needs a connection that can hold back its commits")
    with conn.deferred_commits():
        return _run(ledger, operations, resolutions)


def token(current: object) -> str:
    """A name for the server's value, so that an answer cannot outlive it."""
    return hashlib.sha1(json.dumps(current, sort_keys=True).encode()).hexdigest()[:16]


def _run(
    ledger: Ledger, operations: Sequence[Operation], resolutions: dict[str, Resolution]
) -> list[Outcome]:
    conn = ledger.conn
    # An explicit transaction: a SAVEPOINT opened outside one would commit when released.
    if not conn.in_transaction:
        conn.execute("BEGIN")
    return [_one(ledger, op, resolutions.get(op.id)) for op in operations]


def _one(ledger: Ledger, op: Operation, resolution: Resolution | None) -> Outcome:
    verdict = _INSPECT[op.kind](ledger, op)
    if verdict.state == CONFLICT:
        return _conflict(ledger, op, verdict, resolution)
    if verdict.state != APPLICABLE:
        return Outcome(op.id, verdict.state, verdict.message)
    return _apply(ledger, op)


def _conflict(
    ledger: Ledger, op: Operation, verdict: _Verdict, resolution: Resolution | None
) -> Outcome:
    named = token(verdict.current)
    if resolution is None:
        return Outcome(op.id, CONFLICT, verdict.message, verdict.current, named)
    if resolution.choice == KEEP_SERVER:
        return Outcome(op.id, CONFLICT, verdict.message, verdict.current, named, dropped=True)
    if resolution.seen != named:
        message = "il server è cambiato ancora dopo l'anteprima"
        return Outcome(op.id, CONFLICT, message, verdict.current, named)
    return _apply(ledger, op)


def _apply(ledger: Ledger, op: Operation) -> Outcome:
    """Write one operation inside its own savepoint, so a refusal leaves no trace."""
    conn = ledger.conn
    conn.execute("SAVEPOINT operation")
    try:
        _WRITE[op.kind](ledger, op)
    except (ValueError, KeyError) as exc:
        conn.execute("ROLLBACK TO operation")
        conn.execute("RELEASE operation")
        return Outcome(op.id, INVALID, str(exc).strip("'"))
    conn.execute("RELEASE operation")
    return Outcome(op.id, APPLICABLE, applied=True)


# -- what each kind compares ---------------------------------------------------------------


def _inspect_splits(ledger: Ledger, op: Operation) -> _Verdict:
    row = queries.transaction(ledger, op.transaction_id)
    if row is None:
        return _Verdict(GONE, "il movimento non c'è più")
    if ledger.is_transfer(op.transaction_id):
        return _Verdict(INVALID, "il movimento è diventato una gamba di giroconto")
    wanted = _wanted_splits(op, parse_decimal(row["amount"]))
    unknown = {name for name, _ in wanted} - {r["name"] for r in queries.category_rows(ledger)}
    if unknown:
        return _Verdict(INVALID, f"la categoria {', '.join(sorted(unknown))} non esiste più")
    current = _current_splits(ledger, op.transaction_id)
    if _canonical(current) == _canonical(wanted):
        return _Verdict(ALREADY)
    if _canonical(current) == _canonical(_pairs(op.base["splits"])):
        return _Verdict(APPLICABLE)
    return _Verdict(CONFLICT, "la categoria è cambiata sul server", _splits_json(current))


def _inspect_tag(ledger: Ledger, op: Operation) -> _Verdict:
    if queries.transaction(ledger, op.transaction_id) is None:
        return _Verdict(GONE, "il movimento non c'è più")
    name = " ".join(op.value["tag"].split())
    has = name in ledger.tags_of(op.transaction_id)
    if op.kind == "tag_remove":
        return _Verdict(ALREADY) if not has else _Verdict(APPLICABLE)
    if has:
        return _Verdict(ALREADY)
    if ledger.conn.execute("SELECT 1 FROM tags WHERE name = ?", (name,)).fetchone() is None:
        return _Verdict(INVALID, f"il tag {name} non esiste più")
    return _Verdict(APPLICABLE)


def _inspect_note(ledger: Ledger, op: Operation) -> _Verdict:
    row = queries.transaction(ledger, op.transaction_id)
    if row is None:
        return _Verdict(GONE, "il movimento non c'è più")
    current, wanted, base = _note(row["notes"]), _note(op.value["notes"]), _note(op.base["notes"])
    if current == wanted:
        return _Verdict(ALREADY)
    if current == base:
        return _Verdict(APPLICABLE)
    return _Verdict(CONFLICT, "la nota è cambiata sul server", current)


def _inspect_delete(ledger: Ledger, op: Operation) -> _Verdict:
    row = queries.transaction(ledger, op.transaction_id)
    if row is None:
        return _Verdict(GONE, "il movimento non c'è più")
    current = {key: row[key] for key in _DELETE_BASE}
    if current == {key: op.base[key] for key in _DELETE_BASE}:
        return _Verdict(APPLICABLE)
    return _Verdict(CONFLICT, "il movimento è cambiato sul server", current)


def _inspect_pair(ledger: Ledger, op: Operation) -> _Verdict:
    other = op.value["other_id"]
    for leg in (op.transaction_id, other):
        if queries.transaction(ledger, leg) is None:
            return _Verdict(GONE, f"il movimento {leg} non c'è più")
    paired = ledger.transfer_of(op.transaction_id)
    if paired and paired["kind"] == "pair" and paired["leg_id"] == other:
        return _Verdict(ALREADY if paired["state"] == "confirmed" else APPLICABLE)
    return _Verdict(APPLICABLE)


def _inspect_review(ledger: Ledger, op: Operation) -> _Verdict:
    other = op.value["other_id"]
    for leg in (op.transaction_id, other):
        if queries.transaction(ledger, leg) is None:
            return _Verdict(GONE, f"il movimento {leg} non c'è più")
    row = ledger.conn.execute(
        """SELECT confirmed_by_human FROM transfer_links
           WHERE (leg_a = ? AND leg_b = ?) OR (leg_a = ? AND leg_b = ?)""",
        (op.transaction_id, other, other, op.transaction_id),
    ).fetchone()
    if row is None:
        return _Verdict(GONE, "l'abbinamento non c'è più")
    current = row["confirmed_by_human"]
    if current == (1 if op.value["decision"] == "confirm" else -1):
        return _Verdict(ALREADY)
    if current == op.base["state"]:
        return _Verdict(APPLICABLE)
    return _Verdict(CONFLICT, "l'abbinamento è stato deciso altrimenti sul server", {"state": current})


_INSPECT: dict[str, Callable[[Ledger, Operation], _Verdict]] = {
    "category": _inspect_splits,
    "splits": _inspect_splits,
    "tag_add": _inspect_tag,
    "tag_remove": _inspect_tag,
    "note": _inspect_note,
    "delete": _inspect_delete,
    "pair": _inspect_pair,
    "review": _inspect_review,
}

# -- what each kind writes ------------------------------------------------------------------
#
# The ledger's own writes, the ones the online screens call: a tombstone, the transfer
# guards and the double-entry check are theirs and are not repeated here.


def _write_splits(ledger: Ledger, op: Operation) -> None:
    if op.kind == "category":
        ledger.set_category(op.transaction_id, ledger.category(op.value["category"]))
        return
    wanted = _pairs(op.value["splits"])
    ledger.set_splits(
        op.transaction_id, [(ledger.category(name), amount) for name, amount in wanted]
    )


def _write_tag(ledger: Ledger, op: Operation) -> None:
    if op.kind == "tag_add":
        ledger.add_tag(op.transaction_id, op.value["tag"])
    else:
        ledger.remove_tag(op.transaction_id, " ".join(op.value["tag"].split()))


def _write_note(ledger: Ledger, op: Operation) -> None:
    ledger.set_notes(op.transaction_id, op.value["notes"])


def _write_delete(ledger: Ledger, op: Operation) -> None:
    ledger.delete_transaction(op.transaction_id)


def _write_pair(ledger: Ledger, op: Operation) -> None:
    ledger.mark_transfer_pair(op.transaction_id, op.value["other_id"])


def _write_review(ledger: Ledger, op: Operation) -> None:
    ledger.set_transfer_review(op.transaction_id, op.value["other_id"], op.value["decision"])


_WRITE: dict[str, Callable[[Ledger, Operation], None]] = {
    "category": _write_splits,
    "splits": _write_splits,
    "tag_add": _write_tag,
    "tag_remove": _write_tag,
    "note": _write_note,
    "delete": _write_delete,
    "pair": _write_pair,
    "review": _write_review,
}

# -- values -------------------------------------------------------------------------------------

# What identifies a movement as the bank declared it: a promotion from pending to booked
# rewrites these, and a deletion decided on the old values is no longer the same decision.
_DELETE_BASE = ("date", "amount", "description", "status")


def _wanted_splits(op: Operation, amount: Decimal) -> list[tuple[str, Decimal]]:
    if op.kind == "category":
        return [(op.value["category"], -amount)]
    return _pairs(op.value["splits"])


def _current_splits(ledger: Ledger, transaction_id: int) -> list[tuple[str, Decimal]]:
    return [(row["name"], parse_decimal(row["amount"])) for row in ledger.splits(transaction_id)]


def _pairs(splits: list[dict]) -> list[tuple[str, Decimal]]:
    return [(item["category"], parse_decimal(item["amount"])) for item in splits]


def _canonical(splits: list[tuple[str, Decimal]]) -> list[tuple[str, Decimal]]:
    return sorted(splits)


def _splits_json(splits: list[tuple[str, Decimal]]) -> list[dict]:
    return [{"category": name, "amount": format_decimal(amount)} for name, amount in splits]


def _note(text: str | None) -> str | None:
    return (text or "").strip() or None


def _check_shape(op: Operation) -> None:
    """A malformed operation is the phone's bug, not a state of the ledger: it refuses
    the whole request instead of becoming an outcome."""
    try:
        if op.kind in ("category", "splits"):
            if "splits" not in op.base:
                raise ValueError("the operation has no base")
            if op.kind == "category":
                str(op.value["category"])
            else:
                _pairs(op.value["splits"])
            _pairs(op.base["splits"])
        elif op.kind in ("tag_add", "tag_remove"):
            str(op.value["tag"])
        elif op.kind == "note":
            op.value["notes"], op.base["notes"]
        elif op.kind == "delete":
            for key in _DELETE_BASE:
                op.base[key]
        elif op.kind == "pair":
            int(op.value["other_id"])
        else:
            int(op.value["other_id"])
            int(op.base["state"])
            if op.value["decision"] not in ("confirm", "reject"):
                raise ValueError("unknown decision")
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError(f"operation {op.id} ({op.kind}) is malformed: {exc!r}") from exc
