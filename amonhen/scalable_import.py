"""What Scalable's statements say about a hand-added investment account.

The reading is `adapters.scalable_pdf`; this is the comparison with the ledger.
Two answers, the same for the preview and the write: the valuations the
statements support, each with the difference it would book against the ledger's
balance, and the money that crossed the broker's boundary with no movement in the
ledger to match it — a transfer from a bank that is not connected, or one the
import has not reached yet. The write records the valuations and nothing else:
a missing transfer is the other bank's movement to import, not something to make
up from the broker's side.
"""
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from amonhen.adapters.scalable_pdf import Booking, Reading, boundary_flows, valuations
from amonhen.ledger import VALUATION_PREFIX, Ledger
from amonhen.models import parse_decimal

FLOW_WINDOW_DAYS = 3


@dataclass(frozen=True)
class PlannedValuation:
    date: str
    value: Decimal
    securities: Decimal
    cash: dict[str, Decimal]
    balance: Decimal

    @property
    def difference(self) -> Decimal:
        return self.value - self.balance


@dataclass(frozen=True)
class Plan:
    valuations: list[PlannedValuation]
    unvalued: list[str]
    unmatched: list[Booking]
    internal: list[Booking]
    before_opening: int


def plan(ledger: Ledger, account_id: int, reading: Reading) -> Plan:
    """The valuations to write and the flows the ledger is missing, unwritten.

    Each difference is the one the write would book: the ledger's balance on the
    date, without a valuation already there on a date being valued again, plus
    the differences of the earlier dates in the same batch.
    """
    account = ledger.account(account_id)
    opening = account["opening_date"]
    found, unvalued = valuations(reading)
    found = [v for v in found if opening is None or v.date > opening]

    existing = {
        row["date"]: parse_decimal(row["amount"])
        for row in ledger.conn.execute(
            "SELECT date, amount FROM transactions WHERE account_id = ? AND content_hash LIKE ?",
            (account_id, f"{VALUATION_PREFIX}%"),
        )
    }
    planned: list[PlannedValuation] = []
    for valuation in found:
        replaced = sum((amount for day, amount in existing.items()
                        if day <= valuation.date and day in {v.date for v in found}), Decimal(0))
        earlier = sum((p.difference for p in planned), Decimal(0))
        balance = ledger.balance(account_id, dt.date.fromisoformat(valuation.date)) - replaced + earlier
        planned.append(PlannedValuation(valuation.date, valuation.value, valuation.securities,
                                        dict(valuation.cash), balance))

    flows = boundary_flows(reading)
    internal = _internal(flows)
    candidates = [f for f in flows if f not in internal]
    before = [f for f in candidates if opening is not None and f.value_date <= opening]
    unmatched = _unmatched(ledger, account_id, [f for f in candidates if f not in before])
    return Plan(planned, unvalued, unmatched, internal, len(before))


def apply(ledger: Ledger, account_id: int, planned: list[PlannedValuation]) -> list[tuple[str, Decimal]]:
    """Write the valuations in date order; each one sees the ones before it."""
    return [
        (item.date, ledger.record_valuation(account_id, dt.date.fromisoformat(item.date), item.value)[0])
        for item in sorted(planned, key=lambda p: p.date)
    ]


def _internal(flows: list[Booking]) -> list[Booking]:
    """Money moved between two of the broker's own cash accounts.

    It never left the broker, so the ledger has no movement for it: an inflow on
    one account matched by an equal outflow on another a few days apart. When
    only one side's statement is at hand the pair cannot be seen, and the
    remaining side is reported with the rest.
    """
    paired: list[Booking] = []
    for inflow in (f for f in flows if f.amount > 0):
        for outflow in flows:
            if (outflow not in paired and outflow.account != inflow.account
                    and outflow.amount == -inflow.amount
                    and abs(_days(outflow.value_date, inflow.value_date)) <= FLOW_WINDOW_DAYS):
                paired += [inflow, outflow]
                break
    return paired


def _unmatched(ledger: Ledger, account_id: int, flows: list[Booking]) -> list[Booking]:
    """The flows with no movement of the same amount on the account, days apart at most."""
    rows = [
        (row["id"], row["date"], parse_decimal(row["amount"]))
        for row in ledger.conn.execute(
            "SELECT id, date, amount FROM transactions WHERE account_id = ? AND content_hash NOT LIKE ?",
            (account_id, f"{VALUATION_PREFIX}%"),
        )
    ]
    used: set[int] = set()
    missing: list[Booking] = []
    for flow in flows:
        match = next(
            (row_id for row_id, day, amount in sorted(rows, key=lambda r: abs(_days(r[1], flow.value_date)))
             if row_id not in used and amount == flow.amount
             and abs(_days(day, flow.value_date)) <= FLOW_WINDOW_DAYS),
            None,
        )
        if match is None:
            missing.append(flow)
        else:
            used.add(match)
    return missing


def _days(first: str, second: str) -> int:
    return (dt.date.fromisoformat(second) - dt.date.fromisoformat(first)).days
