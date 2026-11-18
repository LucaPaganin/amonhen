"""The portfolio (desiderata 5.16): read the sources, take the month-end snapshot, answer what is held.

The order of the steps lives here and nothing else does: the arithmetic is in
`core.portfolio` and `core.returns`, the SQL in `ledger.portfolio`, the sources behind
`ports.portfolio`. A reconciliation reports two figures and their gap and corrects
nothing (docs/investments.md); the portfolio never writes a posting, so spending, the
months of runway and the 5.4 check cannot see it.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from decimal import Decimal

from amonhen.core.portfolio import (
    Contribution,
    Difference,
    BtpTerms,
    accrued,
    btp_value,
    coupons,
    fund_position,
    match_flows,
    match_statement,
    month_end,
    month_of,
    split_units,
    add_months,
)
from amonhen.core.returns import mwr, twr
from amonhen.ledger import Ledger
from amonhen.models import format_decimal, parse_decimal
from amonhen.ports.portfolio import (
    DOCUMENT_KINDS,
    FAILED,
    IMPORTED,
    BrokerSource,
    DocumentSource,
    FetchedDocument,
    NavSource,
    NavUnavailable,
    SourceError,
)

ZERO = Decimal(0)


def reported_key(instrument_id: int) -> str:
    """Where what a source reported about an instrument is kept, for the reconciliations."""
    return f"portfolio:reported_units:{instrument_id}"


# -- reading the sources -----------------------------------------------------------

@dataclass
class BrokerRead:
    trades: int = 0
    prices: int = 0
    unknown: list[str] = field(default_factory=list)  # ISINs no instrument has


def sync_broker(ledger: Ledger, broker: BrokerSource, since: dt.date | None = None) -> BrokerRead:
    """Trades, month-end closes and the reported positions of every ETF the broker covers."""
    by_isin = {row["isin"]: row for row in ledger.instruments() if row["kind"] == "etf" and row["isin"]}
    result = BrokerRead()
    for trade in broker.trades(since):
        row = by_isin.get(trade.isin)
        if row is None:
            if trade.isin not in result.unknown:
                result.unknown.append(trade.isin)
            continue
        written = ledger.record_trade(
            row["id"], trade.date, trade.units, trade.price, trade.amount, trade.fees, row["source"], trade.reference
        )
        result.trades += written
    for isin, row in by_isin.items():
        for point in broker.month_end_prices(isin):
            ledger.set_price(row["id"], point.date, point.value, row["source"])
            result.prices += 1
    for position in broker.positions():
        if position.isin in by_isin:
            ledger.set_setting(reported_key(by_isin[position.isin]["id"]), str(position.units))
    return result


@dataclass
class DocumentsRead:
    imported: int = 0
    failed: list[dict] = field(default_factory=list)      # {"id", "kind", "error"}
    skipped: int = 0                                      # already read, never read again
    invested: int = 0                                     # contributions a statement invested
    unmatched: list[dict] = field(default_factory=list)   # operations no payslips explain
    unreported: list[int] = field(default_factory=list)   # read here, but the write-back failed


def _fund(ledger: Ledger):
    rows = [row for row in ledger.instruments() if row["kind"] == "fondo_pensione"]
    if len(rows) != 1:
        raise ValueError("serve esattamente un fondo pensione fra gli strumenti")
    return rows[0]


def _contribution_rows(ledger: Ledger, fund_id: int) -> list[Contribution]:
    rows = []
    for row in ledger.contributions(fund_id):
        total = parse_decimal(row["own"]) + parse_decimal(row["employer"]) + parse_decimal(row["tfr"])
        withheld_on = month_end(row["period"]) if row["payslip"] is not None else None
        invested_on = dt.date.fromisoformat(row["value_date"]) if row["value_date"] else None
        if withheld_on is not None and invested_on is not None:
            # The money cannot have been invested before it was withheld.
            invested_on = max(invested_on, withheld_on)
        rows.append(Contribution(row["id"], total, withheld_on, invested_on))
    return rows


def cursor_key(kind: str) -> str:
    """Where the modification stamp of the last document listed of a kind is kept."""
    return f"paperless:modified_after:{kind}"


def read_documents(ledger: Ledger, documents: DocumentSource, *, retry_failed: bool = False) -> DocumentsRead:
    """Payslips first, then statements: every new document read once, applied, recorded,
    and its outcome written back to the source.

    A payslip's contribution is born withheld; a statement invests the payslips its
    operations add up to, in order. A document already recorded is skipped even when the
    write-back moved its modification date past the cursor — the reason `documents`
    exists. ``retry_failed`` reads the failed ones again, after a template was fixed.
    """
    fund = _fund(ledger)
    result = DocumentsRead()
    for kind in DOCUMENT_KINDS:
        listed = documents.list_new(kind, ledger.setting(cursor_key(kind)))
        ids = [source_id for source_id, _ in listed if ledger.document(source_id) is None]
        result.skipped += len(listed) - len(ids)
        if retry_failed:
            ids = ledger.failed_documents(kind) + [i for i in ids if i not in ledger.failed_documents(kind)]
        for source_id in ids:
            fetched = documents.read(kind, source_id)
            figures = _apply(ledger, fund, fetched, result)
            outcome = FAILED if fetched.error is not None else IMPORTED
            ledger.record_document(source_id, kind, outcome, fetched.layout, fetched.error)
            if outcome == IMPORTED:
                result.imported += 1
            else:
                result.failed.append({"id": source_id, "kind": kind, "error": fetched.error})
            try:
                documents.report(source_id, outcome, figures)
            except SourceError:
                result.unreported.append(source_id)
        if listed:
            ledger.set_setting(cursor_key(kind), max(stamp for _, stamp in listed))
    return result


def _apply(ledger: Ledger, fund, fetched: FetchedDocument, result: DocumentsRead) -> dict[str, str]:
    """Write what a document says, and return the figures that go back to the source."""
    if fetched.error is not None:
        return {"amonhen_errore": fetched.error[:500]}
    if fetched.payslip is not None:
        slip = fetched.payslip
        if slip.own + slip.employer + slip.tfr > 0:
            ledger.withhold(fund["id"], slip.period, slip.own, slip.employer, slip.tfr, slip.reference)
        return {"amonhen_periodo": slip.period, "amonhen_proprio": format_decimal(slip.own),
                "amonhen_datore": format_decimal(slip.employer), "amonhen_tfr": format_decimal(slip.tfr)}
    statement = fetched.statement
    waiting = [row for row in _contribution_rows(ledger, fund["id"])
               if row.withheld_on is not None and row.invested_on is None]
    matched, unmatched = match_statement(waiting, list(statement.operations))
    for operation, rows in matched:
        for row, units in zip(rows, split_units(operation, [row.total for row in rows])):
            ledger.invest(row.id, operation.date, operation.unit_value, units)
            result.invested += 1
    result.unmatched += [
        {"date": op.date.isoformat(), "amount": format_decimal(op.amount), "reference": op.reference}
        for op in unmatched
    ]
    ledger.set_setting(reported_key(fund["id"]), str(statement.units_end))
    return {"amonhen_anno": str(statement.year), "amonhen_quote_fine": str(statement.units_end),
            "amonhen_operazioni": str(len(statement.operations)),
            "amonhen_non_abbinate": str(len(unmatched))}


def fetch_nav(ledger: Ledger, nav: NavSource, month: str) -> bool:
    """The fund's unit value for a month from its class's public page; False when it cannot be read.

    Nothing is written then, and the month waits for a person to give the value
    (`set_nav`): another month's is never reused.
    """
    fund = _fund(ledger)
    page = json.loads(fund["terms"] or "{}").get("nav_page")
    if not page:
        return False
    try:
        value = nav.unit_value(page, fund["class"] or "", month)
    except NavUnavailable:
        return False
    ledger.set_price(fund["id"], month_end(month), value, "pagina pubblica")
    return True


def set_nav(ledger: Ledger, month: str, value: Decimal) -> None:
    """The unit value a person read for a month the page did not give."""
    ledger.set_price(_fund(ledger)["id"], month_end(month), value, "a mano")


def nav_missing(ledger: Ledger, today: dt.date) -> list[str]:
    """The complete months, since the fund first held units, that still have no unit value."""
    funds = [row for row in ledger.instruments() if row["kind"] == "fondo_pensione"]
    if not funds:
        return []
    dates = [row["value_date"] for row in ledger.contributions(funds[0]["id"]) if row["value_date"]]
    if not dates:
        return []
    month, missing = min(dates)[:7], []
    while month_end(month) < today.replace(day=1):
        if ledger.price_at(funds[0]["id"], month_end(month)) is None:
            missing.append(month)
        month = month_of(add_months(month_end(month), 1))
    return missing


# -- what is held on a date ---------------------------------------------------------

@dataclass(frozen=True)
class Holding:
    units: Decimal
    value: Decimal | None  # None: the instrument is held and its price is missing
    paid: Decimal          # paid in, net of what came back (a coupon lowers it)
    price: Decimal | None = None
    price_date: dt.date | None = None


def _price(ledger: Ledger, instrument_id: int, day: dt.date, exact: bool):
    row = ledger.price_at(instrument_id, day) if exact else ledger.latest_price(instrument_id, day)
    return None if row is None else (parse_decimal(row["value"]), dt.date.fromisoformat(row["date"]))


def holding(ledger: Ledger, instrument, day: dt.date, *, exact: bool = False) -> Holding:
    """What an instrument was worth on ``day``.

    A month-end snapshot asks for the price of exactly that day (``exact``), so a missing one
    is said; a reading of today takes the latest price up to today.
    """
    kind, instrument_id = instrument["kind"], instrument["id"]
    if kind == "btp":
        terms = BtpTerms.from_text(instrument["terms"])
        if day < terms.start:
            return Holding(ZERO, ZERO, ZERO)
        received = sum((flow.amount for flow in coupons(terms) if flow.date <= day), ZERO)
        return Holding(Decimal(1), btp_value(terms, day), terms.nominal - received)
    if kind == "immobile":
        quoted = _price(ledger, instrument_id, day, exact)
        share = parse_decimal(instrument["ownership"])
        if quoted is None:
            return Holding(share, None, ZERO)
        return Holding(share, quoted[0] * share, ZERO, quoted[0], quoted[1])
    if kind == "etf":
        trades = [t for t in ledger.trades(instrument_id) if t["date"] <= day.isoformat()]
        units = sum((parse_decimal(t["units"]) for t in trades), ZERO)
        paid = sum((parse_decimal(t["amount"]) + parse_decimal(t["fees"]) for t in trades), ZERO)
        quoted = _price(ledger, instrument_id, day, exact)
    else:  # fondo_pensione
        rows = _contribution_rows(ledger, instrument_id)
        position = fund_position(rows, day)
        units_by_id = {row["id"]: parse_decimal(row["units"]) for row in ledger.contributions(instrument_id) if row["units"]}
        units = sum((units_by_id[r.id] for r in rows if r.invested_on is not None and r.invested_on <= day
                     and (r.withheld_on is None or r.withheld_on <= day)), ZERO)
        direct = sum((r.total for r in rows if r.withheld_on is None and r.invested_on is not None
                      and r.invested_on <= day), ZERO)
        paid = position.withheld + direct
        quoted = _price(ledger, instrument_id, day, exact)
        if quoted is None:
            return Holding(units, None if units > 0 else position.in_transit, paid)
        return Holding(units, units * quoted[0] + position.in_transit, paid, quoted[0], quoted[1])
    if quoted is None:
        return Holding(units, None if units > 0 else ZERO, paid)
    return Holding(units, units * quoted[0], paid, quoted[0], quoted[1])


# -- the month-end snapshot ---------------------------------------------------------

@dataclass
class Snapshot:
    month: str
    written: int = 0
    missing: list[str] = field(default_factory=list)  # "Name: price of the month end"


def take_snapshot(ledger: Ledger, month: str) -> Snapshot:
    """Units, value and paid-in of every instrument at the month's end.

    An instrument held without a price that day is not written and is named: a month
    never borrows another's price.
    """
    end, result = month_end(month), Snapshot(month)
    for instrument in ledger.instruments():
        held = holding(ledger, instrument, end, exact=True)
        if held.value is None:
            result.missing.append(f"{instrument['name']}: manca il prezzo del {end.isoformat()}")
            continue
        if held.units == 0 and held.paid == 0 and held.value == 0:
            continue
        ledger.save_snapshot(month, instrument["id"], held.units, held.value, held.paid)
        result.written += 1
    return result


def _first_event(ledger: Ledger) -> dt.date | None:
    days = []
    for instrument in ledger.instruments():
        if instrument["kind"] == "btp":
            days.append(BtpTerms.from_text(instrument["terms"]).start)
        elif instrument["kind"] == "etf":
            days += [dt.date.fromisoformat(t["date"]) for t in ledger.trades(instrument["id"])]
        elif instrument["kind"] == "fondo_pensione":
            days += [month_end(row["period"]) for row in ledger.contributions(instrument["id"])]
    return min(days, default=None)


def snapshot_through(ledger: Ledger, today: dt.date) -> list[Snapshot]:
    """A snapshot for every complete month from the first thing held to the month before ``today``."""
    first = _first_event(ledger)
    if first is None:
        return []
    results, month = [], month_of(first)
    while month_end(month) < today.replace(day=1):
        results.append(take_snapshot(ledger, month))
        month = month_of(add_months(month_end(month), 1))
    return results


# -- reconciliations ------------------------------------------------------------------

def reconciliations(ledger: Ledger, today: dt.date) -> list[dict]:
    """Four pairs of figures and their gap; none of them is ever absorbed into anything."""
    out: list[dict] = []

    def add(difference: Difference, note: str | None = None) -> None:
        out.append({
            "label": difference.label,
            "expected": format_decimal(difference.expected) if difference.unit == "€" else str(difference.expected),
            "actual": format_decimal(difference.actual) if difference.unit == "€" else str(difference.actual),
            "difference": format_decimal(difference.difference) if difference.unit == "€" else str(difference.difference),
            "unit": difference.unit,
            "note": note,
        })

    etfs = [row for row in ledger.instruments() if row["kind"] == "etf"]
    if etfs:
        sent = ledger.invested_between(dt.date(1970, 1, 1), today)
        bought = sum((ledger.trades_total(row["id"]) for row in etfs), ZERO)
        add(Difference("PAC: soldi mandati a Investimenti contro acquisti del broker", sent, bought, "€"))
        for row in etfs:
            reported = ledger.setting(reported_key(row["id"]))
            ours = sum((parse_decimal(t["units"]) for t in ledger.trades(row["id"])), ZERO)
            if reported is None:
                out.append({"label": f"Quote di {row['name']} contro la posizione del broker", "expected": str(ours),
                            "actual": None, "difference": None, "unit": "quote",
                            "note": "il broker non ha ancora riportato la posizione"})
            else:
                add(Difference(f"Quote di {row['name']} contro la posizione del broker", ours,
                               parse_decimal(reported), "quote"))
    for row in ledger.instruments():
        if row["kind"] == "btp":
            terms = BtpTerms.from_text(row["terms"])
            data = _terms_data(row)
            expected = [f for f in coupons(terms) if f.date <= today and f.kind == "cedola"]
            if not (data.get("account") and data.get("credit_text")):
                continue
            credits = ledger.credits_between(data["account"], terms.start, today, data["credit_text"])
            matches = match_flows(expected, credits)
            late = [m.date.isoformat() for m in matches if m.actual is None]
            add(
                Difference(f"Cedole di {row['name']} contro gli accrediti",
                           sum((m.expected for m in matches), ZERO), sum((m.actual or ZERO for m in matches), ZERO), "€"),
                None if not late else "senza accredito: " + ", ".join(late),
            )
    fund_rows = [row for row in ledger.instruments() if row["kind"] == "fondo_pensione"]
    for fund in fund_rows:
        rows = _contribution_rows(ledger, fund["id"])
        position = fund_position(rows, today)
        add(Difference("Trattenuto contro investito", position.withheld, position.invested, "€"),
            "la differenza è in transito")
        reported = ledger.setting(reported_key(fund["id"]))
        units = sum((parse_decimal(r["units"]) for r in ledger.contributions(fund["id"]) if r["units"]), ZERO)
        if reported is None:
            out.append({"label": "Quote del fondo contro il prospetto", "expected": str(units), "actual": None,
                        "difference": None, "unit": "quote", "note": "nessun prospetto letto"})
        else:
            add(Difference("Quote del fondo contro il prospetto", units, parse_decimal(reported), "quote"))
    return out


def _terms_data(instrument) -> dict:
    return json.loads(instrument["terms"])


# -- what the screen reads ------------------------------------------------------------

def _pct(rate) -> str | None:
    return None if rate is None else f"{Decimal(str(rate)) * 100:.2f}"


def _flows_and_chain(ledger: Ledger, instrument, today: dt.date):
    """An instrument's dated flows (money in negative), its chained periods, and its value today."""
    held = holding(ledger, instrument, today)
    kind, instrument_id = instrument["kind"], instrument["id"]
    flows: list[tuple[dt.date, Decimal]] = []
    periods: list[tuple[Decimal, Decimal]] = []
    if kind == "etf":
        units, last = ZERO, None
        for t in ledger.trades(instrument_id):
            price = parse_decimal(t["price"])
            if units > 0 and last is not None:
                periods.append((units * last, units * price))
            units += parse_decimal(t["units"])
            last = price
            flows.append((dt.date.fromisoformat(t["date"]),
                          -(parse_decimal(t["amount"]) + parse_decimal(t["fees"]))))
        if held.price is not None and units > 0 and last is not None:
            periods.append((units * last, units * held.price))
    elif kind == "fondo_pensione":
        units, last = ZERO, None
        invested = sorted(
            (r for r in ledger.contributions(instrument_id) if r["units"]),
            key=lambda r: r["value_date"],
        )
        for r in invested:
            price = parse_decimal(r["unit_value"])
            if units > 0 and last is not None:
                periods.append((units * last, units * price))
            units += parse_decimal(r["units"])
            last = price
        if held.price is not None and units > 0 and last is not None:
            periods.append((units * last, units * held.price))
        for row in _contribution_rows(ledger, instrument_id):
            moment = row.withheld_on or row.invested_on
            if moment is not None and moment <= today:
                flows.append((moment, -row.total))
    elif kind == "btp":
        terms = BtpTerms.from_text(instrument["terms"])
        if today >= terms.start:
            flows.append((terms.start, -terms.nominal))
            flows += [(f.date, f.amount) for f in coupons(terms) if f.date <= today]
    return held, flows, periods


def overview(ledger: Ledger, today: dt.date) -> dict:
    """The portfolio as the screen reads it: positions, the fund in transit, reconciliations, the series."""
    positions, all_flows, final_value, missing = [], [], ZERO, []
    for instrument in ledger.instruments():
        held, flows, periods = _flows_and_chain(ledger, instrument, today)
        note = None
        value = held.value
        if value is None:
            note = "manca il prezzo"
            missing.append(f"{instrument['name']}: manca il prezzo")
        returns_apply = instrument["kind"] != "immobile"
        rate = None
        if returns_apply and value is not None and flows:
            rate = mwr([*flows, (today, value)])
            all_flows += flows
            final_value += value
        elif value is not None and instrument["kind"] == "immobile":
            pass
        positions.append({
            "name": instrument["name"],
            "kind": instrument["kind"],
            "units": str(held.units),
            "price": None if held.price is None else str(held.price),
            "price_date": None if held.price_date is None else held.price_date.isoformat(),
            "value": None if value is None else format_decimal(value),
            "paid": format_decimal(held.paid) if returns_apply else None,
            "twr": _pct(twr(periods)) if instrument["kind"] in ("etf", "fondo_pensione") else None,
            "mwr": _pct(rate),
            "note": note,
        })
    snapshots = _series(ledger, today)
    fund = [row for row in ledger.instruments() if row["kind"] == "fondo_pensione"]
    transit = None
    if fund:
        position = fund_position(_contribution_rows(ledger, fund[0]["id"]), today)
        transit = {"withheld": format_decimal(position.withheld), "invested": format_decimal(position.invested),
                   "in_transit": format_decimal(position.in_transit)}
    return {
        "today": today.isoformat(),
        "positions": positions,
        "total": {
            "value": format_decimal(sum((parse_decimal(p["value"]) for p in positions if p["value"] is not None), ZERO)),
            "mwr": _pct(mwr([*all_flows, (today, final_value)])) if all_flows else None,
            "twr": _pct(_total_twr(ledger, snapshots, today)),
        },
        "fund": transit,
        "reconciliations": reconciliations(ledger, today),
        "series": snapshots["points"],
        "missing": missing,
        "nav_missing": nav_missing(ledger, today),
    }


def _series(ledger: Ledger, today: dt.date) -> dict:
    """The month-end net worth: cash and portfolio, from the snapshots written."""
    by_month: dict[str, list] = {}
    for row in ledger.snapshots():
        by_month.setdefault(row["month"], []).append(row)
    instruments = {row["id"]: row for row in ledger.instruments()}
    points, chain = [], []
    for month, rows in sorted(by_month.items()):
        end = month_end(month)
        value = sum((parse_decimal(r["value"]) for r in rows), ZERO)
        liquidity = ledger.liquidity_on(end)
        counted = [r for r in rows if instruments[r["instrument_id"]]["kind"] != "immobile"]
        chain.append((month,
                      sum((parse_decimal(r["value"]) for r in counted), ZERO),
                      sum((parse_decimal(r["paid"]) for r in counted), ZERO)))
        points.append({
            "month": month,
            "liquidity": format_decimal(liquidity),
            "portfolio": format_decimal(value),
            "total": format_decimal(liquidity + value),
            "instruments": len(rows),
        })
    return {"points": points, "chain": chain}


def _total_twr(ledger: Ledger, series: dict, today: dt.date) -> Decimal | None:
    """The whole portfolio's TWR over the month ends, with each month's flows taken at its end.

    The exact flow dates of the trades are used per instrument; across instruments only the
    month-end values exist, so a month's net payments are subtracted from its end value.
    """
    chain = series["chain"]
    periods = []
    for (_, before, paid_before), (_, after, paid_after) in zip(chain, chain[1:]):
        periods.append((before, after - (paid_after - paid_before)))
    return twr(periods)
