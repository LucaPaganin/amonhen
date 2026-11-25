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
    Opening,
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


def opening_key(instrument_id: int) -> str:
    """Where an instrument's opening is kept, while the documents do not explain it yet."""
    return f"portfolio:opening:{instrument_id}"


# -- the opening ---------------------------------------------------------------------

def opening(ledger: Ledger, instrument) -> Opening | None:
    if instrument["kind"] not in ("etf", "fondo_pensione"):
        return None
    text = ledger.setting(opening_key(instrument["id"]))
    return None if text is None else Opening.from_text(text)


def open_position(ledger: Ledger, name: str, start: Opening) -> None:
    """Declare what an ETF or the fund held on a date, once.

    From that date the documents add what follows it; the ones dated up to it are already
    inside the opening, and are reconciled against it instead of being added.
    """
    instrument = ledger.instrument(name)
    if instrument is None or instrument["kind"] not in ("etf", "fondo_pensione"):
        raise ValueError(f"nessun ETF o fondo pensione di nome {name!r}")
    if opening(ledger, instrument) is not None:
        raise ValueError(f"{name} ha già un'apertura: va ritirata prima di dichiararne un'altra")
    ledger.set_setting(opening_key(instrument["id"]), start.to_text())
    # The price of that day is a price like any other: it stays when the opening retires.
    if ledger.price_at(instrument["id"], start.date) is None:
        ledger.set_price(instrument["id"], start.date, start.price, "apertura")


def retire_opening(ledger: Ledger, name: str) -> Opening:
    """Take the opening away: from now on the documents alone say what is held."""
    instrument = ledger.instrument(name)
    held = None if instrument is None else opening(ledger, instrument)
    if held is None:
        raise ValueError(f"{name} non ha un'apertura")
    with ledger.conn:
        ledger.conn.execute("DELETE FROM settings WHERE key = ?", (opening_key(instrument["id"]),))
    return held


def _after(rows: list[Contribution], start: Opening | None) -> list[Contribution]:
    """The fund's rows the opening does not contain: withheld (or paid straight) after its date."""
    if start is None:
        return rows
    return [r for r in rows if (r.withheld_on or r.invested_on) is not None
            and (r.withheld_on or r.invested_on) > start.date]


def _trades_after(ledger: Ledger, instrument_id: int, start: Opening | None):
    """An ETF's trades the opening does not contain: those dated after it."""
    trades = ledger.trades(instrument_id)
    return trades if start is None else [t for t in trades if t["date"] > start.date.isoformat()]


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
    start = opening(ledger, funds[0])
    if start is not None:
        dates = [day for day in dates if day > start.date.isoformat()] + [start.date.isoformat()]
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
    start = opening(ledger, instrument)
    if start is not None and day < start.date:
        # Before the opening nothing is known for certain: the documents may be missing some.
        return Holding(ZERO, ZERO, ZERO)
    base_units, base_paid = (ZERO, ZERO) if start is None else (start.units, start.paid)
    if kind == "etf":
        trades = [t for t in _trades_after(ledger, instrument_id, start) if t["date"] <= day.isoformat()]
        units = base_units + sum((parse_decimal(t["units"]) for t in trades), ZERO)
        paid = base_paid + sum((parse_decimal(t["amount"]) + parse_decimal(t["fees"]) for t in trades), ZERO)
        quoted = _price(ledger, instrument_id, day, exact)
    else:  # fondo_pensione
        every = _contribution_rows(ledger, instrument_id)
        rows = _after(every, start)
        position = fund_position(rows, day)
        units_by_id = {row["id"]: parse_decimal(row["units"]) for row in ledger.contributions(instrument_id) if row["units"]}
        # A row invested after the opening was not among its units, even when it was withheld before.
        units = base_units + sum((units_by_id[r.id] for r in every if r.invested_on is not None and r.invested_on <= day
                                  and (r.withheld_on is None or r.withheld_on <= day)
                                  and (start is None or r.invested_on > start.date)), ZERO)
        direct = sum((r.total for r in rows if r.withheld_on is None and r.invested_on is not None
                      and r.invested_on <= day), ZERO)
        paid = base_paid + position.withheld + direct
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
        start = opening(ledger, instrument)
        if start is not None:
            days.append(start.date)
        elif instrument["kind"] == "btp":
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

    def opening_row(name: str, start: Opening, explained: Decimal) -> None:
        add(Difference(f"Apertura di {name} contro i documenti", start.units, explained, "quote"),
            "i documenti spiegano tutta l'apertura: si può ritirare" if explained == start.units
            else f"documenti fino al {start.date.isoformat()}: la differenza è quanto ancora non spiegano")

    etfs = [row for row in ledger.instruments() if row["kind"] == "etf"]
    if etfs:
        # With an opening on every ETF the ledger's transfers are compared from the day after
        # it: before then they may predate the ledger's history, and the opening holds the rest.
        starts = [opening(ledger, row) for row in etfs]
        since = (min(s.date for s in starts) + dt.timedelta(days=1)) if all(starts) else dt.date(1970, 1, 1)
        sent = ledger.invested_between(since, today)
        bought = sum((parse_decimal(t["amount"]) + parse_decimal(t["fees"])
                      for row, start in zip(etfs, starts)
                      for t in _trades_after(ledger, row["id"], start) if t["date"] >= since.isoformat()), ZERO)
        add(Difference("PAC: soldi mandati a Investimenti contro acquisti del broker", sent, bought, "€"),
            None if not all(starts) else f"dal {since.isoformat()}, dopo l'apertura")
        for row in etfs:
            start = opening(ledger, row)
            if start is not None:
                opening_row(row["name"], start, sum(
                    (parse_decimal(t["units"]) for t in ledger.trades(row["id"]) if t["date"] <= start.date.isoformat()),
                    ZERO))
            reported = ledger.setting(reported_key(row["id"]))
            ours = (ZERO if start is None else start.units) + sum(
                (parse_decimal(t["units"]) for t in _trades_after(ledger, row["id"], start)), ZERO)
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
            # Coupons paid before the account's history (another bank held the BTP) are not looked for.
            since = dt.date.fromisoformat(data["credits_from"]) if data.get("credits_from") else terms.start
            expected = [f for f in expected if f.date >= since]
            credits = ledger.credits_between(data["account"], since, today, data["credit_text"])
            if data.get("withholding_text"):
                # A bank that credits the gross coupon and debits the tax apart: net them by day.
                withheld: dict[dt.date, Decimal] = {}
                for day, amount in ledger.debits_between(data["account"], since, today, data["withholding_text"]):
                    withheld[day] = withheld.get(day, ZERO) + amount
                credits = [(day, amount + withheld.pop(day, ZERO)) for day, amount in credits]
            matches = match_flows(expected, credits)
            late = [m.date.isoformat() for m in matches if m.actual is None]
            add(
                Difference(f"Cedole di {row['name']} contro gli accrediti",
                           sum((m.expected for m in matches), ZERO), sum((m.actual or ZERO for m in matches), ZERO), "€"),
                None if not late else "senza accredito: " + ", ".join(late),
            )
    fund_rows = [row for row in ledger.instruments() if row["kind"] == "fondo_pensione"]
    for fund in fund_rows:
        start = opening(ledger, fund)
        every = _contribution_rows(ledger, fund["id"])
        position = fund_position(_after(every, start), today)
        add(Difference("Trattenuto contro investito", position.withheld, position.invested, "€"),
            "la differenza è in transito" if start is None
            else f"dopo l'apertura del {start.date.isoformat()}; la differenza è in transito")
        units_by_id = {r["id"]: parse_decimal(r["units"]) for r in ledger.contributions(fund["id"]) if r["units"]}
        if start is not None:
            opening_row(fund["name"], start, sum(
                (units_by_id[r.id] for r in every if r.id in units_by_id and r.invested_on <= start.date), ZERO))
        reported = ledger.setting(reported_key(fund["id"]))
        units = (ZERO if start is None else start.units) + sum(
            (units_by_id[r.id] for r in every if r.id in units_by_id
             and (start is None or r.invested_on > start.date)), ZERO)
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
    start = opening(ledger, instrument)
    # The returns start from the opening: its value that day is the first money in.
    units, last = (ZERO, None) if start is None else (start.units, start.price)
    if start is not None and start.date <= today:
        flows.append((start.date, -start.value))
    if kind == "etf":
        for t in _trades_after(ledger, instrument_id, start):
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
        invested = sorted(
            (r for r in ledger.contributions(instrument_id)
             if r["units"] and (start is None or r["value_date"] > start.date.isoformat())),
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
        for row in _after(_contribution_rows(ledger, instrument_id), start):
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
        start = opening(ledger, instrument)
        note = None if start is None else f"rendimenti dall'apertura del {start.date.isoformat()}"
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
        position = fund_position(_after(_contribution_rows(ledger, fund[0]["id"]), opening(ledger, fund[0])), today)
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
    openings = [start.date for row in ledger.instruments() for start in [opening(ledger, row)] if start is not None]
    # The month an opening enters in would count as a return what grew before it: it is skipped.
    first = month_of(max(openings)) if openings else ""
    periods = []
    for (_, before, paid_before), (month, after, paid_after) in zip(chain, chain[1:]):
        if month <= first:
            continue
        periods.append((before, after - (paid_after - paid_before)))
    return twr(periods)
