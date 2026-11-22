"""The portfolio (desiderata 5.16): the BTP, the fund's two states, the reconciliations, the returns."""
import datetime as dt
import json
import math
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from amonhen.api.app import create_app
from amonhen.core.portfolio import (
    BtpTerms,
    Contribution,
    Difference,
    Flow,
    Opening,
    StatementOperation,
    accrued,
    btp_value,
    coupons,
    fund_position,
    match_flows,
    match_statement,
    split_units,
)
from amonhen.core.returns import mwr, twr
from amonhen.db import connect, initialize
from amonhen.ledger import Ledger
from amonhen.metrics import compute_metrics
from amonhen.models import Account, IncomingTransaction
from amonhen.ports.portfolio import (
    BrokerPosition,
    BrokerTrade,
    PayslipContribution,
    PricePoint,
    SourceUnavailable,
)
from amonhen.services import portfolio as service
from tests.fixed_clock import FixedClock
from tests.memory_portfolio import MemoryBroker, MemoryDocuments, MemoryNav, documents_from
from tests.test_amonhen_cli import MINIMAL_CONFIG

d = dt.date
TERMS = BtpTerms(D(10000), d(2025, 1, 10), tuple(D(x) for x in ("4.10", "4.10", "4.10", "4.50", "4.50")),
                 D("12.5"), D("0.5"))


# -- the BTP -------------------------------------------------------------------

def test_a_btp_pays_twenty_net_coupons_and_the_bonus_once():
    flows = coupons(TERMS)
    cedole = [f for f in flows if f.kind == "cedola"]
    assert len(cedole) == 20 and cedole[0].date == d(2025, 4, 10)
    assert cedole[0].amount == D("89.69")    # 10,000 × 4.10% / 4 = 102.50, less 12.5%
    assert cedole[-1].amount == D("98.44")   # 10,000 × 4.50% / 4 = 112.50, less 12.5%
    assert [f for f in flows if f.kind == "premio"] == [Flow(d(2030, 1, 10), D("50.00"), "premio")]


def test_the_accrued_coupon_grows_inside_the_quarter_and_resets_when_it_is_paid():
    assert accrued(TERMS, d(2025, 2, 24)) == D("44.84375")   # 45 days of 90
    assert accrued(TERMS, d(2025, 4, 10)) == 0
    assert accrued(TERMS, d(2025, 1, 10)) == 0


def test_the_loyalty_bonus_counts_on_the_maturity_date_only():
    assert btp_value(TERMS, d(2025, 2, 24)) == D(10000) + D("44.84375")
    assert btp_value(TERMS, d(2030, 1, 9)) == D(10000) + accrued(TERMS, d(2030, 1, 9))   # no bonus yet
    assert btp_value(TERMS, d(2030, 1, 10)) == D(10050)
    assert btp_value(TERMS, d(2031, 1, 1)) == 0 and btp_value(TERMS, d(2024, 1, 1)) == 0


def test_btp_terms_say_what_is_missing():
    with pytest.raises(ValueError, match="rates"):
        BtpTerms.from_text(json.dumps({"nominal": "1", "start": "2025-01-01", "tax": "12.5", "bonus": "0"}))


# -- a pension contribution -------------------------------------------------------

def withheld(*totals):
    return [Contribution(i, D(t), d(2025, i + 1, 28), None) for i, t in enumerate(totals)]


def operation(day, amount, units, value="10", reference="x"):
    return StatementOperation(day, D(amount), D(value), D(units), reference)


def test_a_statement_batch_invests_the_consecutive_payslips_it_adds_up_to():
    matched, unmatched = match_statement(
        withheld("100", "100", "150"),
        [operation(d(2025, 4, 15), "200", "20"), operation(d(2025, 9, 10), "150", "12.5")],
    )
    assert [[c.id for c in rows] for _, rows in matched] == [[0, 1], [2]] and unmatched == []


def test_an_operation_no_payslips_add_up_to_is_reported_and_blocks_nothing():
    matched, unmatched = match_statement(
        withheld("100", "100", "150"),
        [operation(d(2025, 4, 15), "250", "25"), operation(d(2025, 5, 1), "100", "10")],
    )
    assert [op.amount for op in unmatched] == [D(250)]
    assert [[c.id for c in rows] for _, rows in matched] == [[0]]


def test_the_units_of_a_batch_split_in_proportion_and_add_up_exactly():
    op = operation(d(2025, 4, 15), "300", "10")
    parts = split_units(op, [D(100), D(100), D(100)])
    assert sum(parts) == D(10) and parts[0] == D("3.333333")


def test_withheld_is_always_invested_plus_in_transit():
    rows = [
        Contribution(1, D(100), d(2025, 1, 31), d(2025, 4, 15)),
        Contribution(2, D(100), d(2025, 2, 28), d(2025, 4, 15)),
        Contribution(3, D(150), d(2025, 3, 31), None),
        Contribution(4, D(80), None, d(2025, 6, 1)),   # paid straight to the fund
    ]
    for day in (d(2025, 1, 15), d(2025, 2, 28), d(2025, 4, 1), d(2025, 4, 15), d(2025, 12, 31)):
        position = fund_position(rows, day)
        assert position.withheld == position.invested + position.in_transit
    assert fund_position(rows, d(2025, 4, 1)).in_transit == D(350)
    after = fund_position(rows, d(2025, 12, 31))
    assert (after.withheld, after.invested, after.in_transit) == (D(350), D(200), D(150))


# -- reconciliations ----------------------------------------------------------------

def test_a_difference_is_two_figures_and_their_gap():
    gap = Difference("x", D(100), D("97.5"), "€")
    assert (gap.expected, gap.actual, gap.difference) == (D(100), D("97.5"), D("-2.5"))


def test_a_coupon_pairs_with_the_nearest_credit_in_the_window():
    expected = [Flow(d(2025, 4, 10), D("89.69"), "cedola"), Flow(d(2025, 7, 10), D("89.69"), "cedola")]
    matches = match_flows(expected, [(d(2025, 4, 12), D("89.69")), (d(2025, 6, 1), D(500))])
    assert [m.actual for m in matches] == [D("89.69"), None]


# -- TWR and MWR, on flows whose result is known --------------------------------------

def test_twr_chains_the_growth_between_flows():
    # 100 grows to 120, 100 more goes in, the 220 grows to 242: 1.2 × 1.1.
    assert twr([(D(100), D(120)), (D(220), D(242))]) == D("0.32")
    assert twr([]) is None


def test_mwr_of_a_single_year_is_the_plain_return():
    assert mwr([(d(2025, 1, 1), D(-100)), (d(2026, 1, 1), D(110))]) == pytest.approx(0.10, abs=1e-6)


def test_mwr_depends_on_when_the_money_went_in():
    rate = mwr([(d(2025, 1, 1), D(-100)), (d(2026, 1, 1), D(-100)), (d(2027, 1, 1), D(242))])
    assert rate == pytest.approx((-100 + math.sqrt(106800)) / 200 - 1, abs=1e-6)
    # The same flows with the second payment a year later give a different rate.
    later = mwr([(d(2025, 1, 1), D(-100)), (d(2027, 1, 1), D(-100)), (d(2027, 1, 1), D(242))])
    assert later != pytest.approx(rate, abs=1e-3)


def test_mwr_needs_money_in_and_money_out():
    assert mwr([(d(2025, 1, 1), D(-100))]) is None
    assert mwr([(d(2025, 1, 1), D(100)), (d(2026, 1, 1), D(100))]) is None


# -- the use cases, on a ledger and fake sources ----------------------------------------

def etf(ledger, name="MSCI World"):
    return ledger.add_instrument(name, "etf", source="broker", isin="IE00TEST")


def fund(ledger):
    return ledger.add_instrument("Fondo", "fondo_pensione", source="prospetto", fund_class="C",
                                 terms=json.dumps({"nav_page": "TESTC"}))


def trade(day, units, price, ref, isin="IE00TEST"):
    return BrokerTrade(isin, day, D(units), D(price), D(units) * D(price), D(0), ref)


def test_the_broker_is_read_once_and_an_unknown_isin_is_named(ledger):
    instrument = etf(ledger)
    broker = MemoryBroker(
        trades_=[trade(d(2025, 1, 1), "10", "10", "a"), trade(d(2025, 7, 1), "10", "12", "b"),
                 trade(d(2025, 7, 1), "1", "1", "c", isin="XX00OTHER")],
        positions_=[BrokerPosition("IE00TEST", D(20))],
        prices={"IE00TEST": [PricePoint("IE00TEST", d(2025, 12, 31), D("13.2"))]},
    )
    first = service.sync_broker(ledger, broker)
    again = service.sync_broker(ledger, broker)
    assert (first.trades, first.prices, first.unknown) == (2, 1, ["XX00OTHER"])
    assert again.trades == 0 and len(ledger.trades(instrument)) == 2
    broker.down = True
    with pytest.raises(SourceUnavailable):
        service.sync_broker(ledger, broker)


def payslips():
    return [PayslipContribution(f"bp-{m}", f"2025-{m:02d}", D(a), D(b), D(c))
            for m, (a, b, c) in enumerate([("50", "30", "20"), ("50", "30", "20"), ("80", "40", "30")], 1)]


def test_payslips_are_withheld_and_a_statement_invests_them_in_order(ledger):
    fund(ledger)
    docs = documents_from(payslips(), [operation(d(2025, 4, 15), "200", "20"), operation(d(2025, 9, 10), "999", "1")],
                          units=D(20))
    first = service.read_documents(ledger, docs)
    again = service.read_documents(ledger, docs)
    assert (first.imported, first.invested, first.failed) == (4, 2, [])
    assert first.unmatched == [{"date": "2025-09-10", "amount": "999.00", "reference": "x"}]
    # The write-back moved every stamp past the cursor: listed again, read never again.
    assert (again.imported, again.skipped) == (0, 4) and docs.reads == [100, 101, 102, 199]
    rows = ledger.contributions(1)
    assert [r["state"] for r in rows] == ["investito", "investito", "trattenuto"]
    assert D(rows[0]["units"]) + D(rows[1]["units"]) == D(20)


def test_the_outcome_goes_back_with_the_key_figures(ledger):
    fund(ledger)
    docs = documents_from(payslips()[:1], [operation(d(2025, 4, 15), "100", "10")], units=D(10))
    service.read_documents(ledger, docs)
    slip, statement = docs.reports
    assert slip == (100, "importato", {"amonhen_periodo": "2025-01", "amonhen_proprio": "50.00",
                                       "amonhen_datore": "30.00", "amonhen_tfr": "20.00"})
    assert statement[1] == "importato" and statement[2]["amonhen_quote_fine"] == "10"
    assert ledger.document(199)["outcome"] == "importato"


def test_a_document_that_does_not_read_is_marked_and_writes_nothing(ledger):
    from amonhen.ports.portfolio import FetchedDocument

    fund(ledger)
    docs = MemoryDocuments()
    docs.add(FetchedDocument(7, "busta_paga", error="InvariantViolated: net_pay: 1 != 2 (difference -1)"), "2026-01-01")
    result = service.read_documents(ledger, docs)
    assert result.failed == [{"id": 7, "kind": "busta_paga", "error": "InvariantViolated: net_pay: 1 != 2 (difference -1)"}]
    assert ledger.contributions(1) == [] and docs.reports[0][1] == "errore"
    assert ledger.document(7)["outcome"] == "errore"
    # Fixed the template: the failed one is read again on request, and only then.
    docs.documents[7] = ("busta_paga", "2026-01-01", FetchedDocument(7, "busta_paga", payslip=payslips()[0]))
    assert service.read_documents(ledger, docs).imported == 0
    assert service.read_documents(ledger, docs, retry_failed=True).imported == 1
    assert ledger.document(7)["outcome"] == "importato"


def test_a_source_that_does_not_answer_stops_before_anything_is_written(ledger):
    fund(ledger)
    docs = documents_from(payslips())
    docs.down = True
    with pytest.raises(SourceUnavailable):
        service.read_documents(ledger, docs)
    assert ledger.contributions(1) == []


def test_an_unreadable_nav_writes_nothing_and_is_never_borrowed(ledger):
    fund(ledger)
    nav = MemoryNav({"2025-10": D("11")})
    assert service.fetch_nav(ledger, nav, "2025-10") is True
    assert service.fetch_nav(ledger, nav, "2025-11") is False
    assert ledger.price_at(1, d(2025, 11, 30)) is None
    assert ledger.price_at(1, d(2025, 10, 31))["value"] == "11"
    assert ledger.price_at(1, d(2025, 10, 31))["source"] == "pagina pubblica"


def test_a_fund_without_a_page_asks_for_every_value_by_hand(ledger):
    ledger.add_instrument("Fondo", "fondo_pensione", source="prospetto", fund_class="C")
    assert service.fetch_nav(ledger, MemoryNav({"2025-10": D("11")}), "2025-10") is False


def test_the_months_without_a_unit_value_are_listed_and_written_by_hand(ledger):
    _, fund_id = seeded(ledger)
    missing = service.nav_missing(ledger, d(2025, 8, 10))
    assert missing == ["2025-04", "2025-05", "2025-06", "2025-07"]
    service.set_nav(ledger, "2025-05", D("10.4"))
    assert service.nav_missing(ledger, d(2025, 8, 10)) == ["2025-04", "2025-06", "2025-07"]
    assert ledger.price_at(fund_id, d(2025, 5, 31))["source"] == "a mano"


def seeded(ledger):
    """An ETF, the fund and a BTP, with the months written by hand."""
    instrument = etf(ledger)
    service.sync_broker(ledger, MemoryBroker(
        trades_=[trade(d(2025, 1, 1), "10", "10", "a"), trade(d(2025, 7, 1), "10", "12", "b")],
        positions_=[BrokerPosition("IE00TEST", D(20))],
        prices={"IE00TEST": [PricePoint("IE00TEST", d(2025, m, day), D(p))
                             for m, day, p in ((1, 31, "10"), (6, 30, "12"), (12, 31, "13.2"))]},
    ))
    fund_id = fund(ledger)
    service.read_documents(ledger, documents_from(payslips(), [operation(d(2025, 4, 15), "200", "20")], units=D(20)))
    return instrument, fund_id


def test_a_month_end_without_a_price_is_named_and_not_written(ledger):
    seeded(ledger)
    june = service.take_snapshot(ledger, "2025-06")
    # The ETF has its June close; the fund holds units and has no unit value for the month.
    assert june.missing == ["Fondo: manca il prezzo del 2025-06-30"] and june.written == 1
    assert [r["instrument_id"] for r in ledger.snapshots()] == [1]


def test_the_snapshot_values_each_instrument_its_own_way(ledger):
    etf_id, fund_id = seeded(ledger)
    btp = ledger.add_instrument("BTP Valore", "btp", source="calcolato", terms=json.dumps({
        "nominal": "10000", "start": "2025-01-10", "rates": ["4.10"] * 3 + ["4.50"] * 2, "tax": "12.5", "bonus": "0.5"}))
    ledger.set_price(fund_id, d(2025, 6, 30), D("11"), "pagina")
    ledger.set_price(etf_id, d(2025, 6, 30), D("12"), "broker")
    snapshot = service.take_snapshot(ledger, "2025-06")
    assert snapshot.missing == [] and snapshot.written == 3
    rows = {r["instrument_id"]: r for r in ledger.snapshots()}
    assert rows[etf_id]["value"] == "120.00" and rows[etf_id]["paid"] == "100.00"
    # 20 units at 11, plus the payslip of March still in transit, valued at cost.
    assert rows[fund_id]["value"] == "370.00" and rows[fund_id]["paid"] == "350.00"
    # Nominal plus the quarter's accrued coupon, and the nominal less the coupons already paid.
    assert D(rows[btp]["value"]) == (D(10000) + accrued(TERMS, d(2025, 6, 30))).quantize(D("0.01"))
    assert rows[btp]["paid"] == "9910.31"   # one coupon had been paid by 30 June


def test_the_net_worth_of_a_month_end_is_cash_plus_the_portfolio(ledger):
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    ledger.record(IncomingTransaction(account_id=bank, date=d(2025, 3, 3), amount=D("500"), description="x",
                                      status="BOOK", source="psd2", balancing_account_id=ledger.category("Stipendio")))
    etf_id, _ = seeded(ledger)
    ledger.set_price(etf_id, d(2025, 6, 30), D("12"), "broker")
    ledger.set_price(2, d(2025, 6, 30), D("11"), "pagina")
    service.take_snapshot(ledger, "2025-06")
    point = service.overview(ledger, d(2026, 1, 15))["series"][0]
    assert (point["liquidity"], point["portfolio"], point["total"]) == ("500.00", "490.00", "990.00")


def test_the_portfolio_moves_nothing_the_ledger_measures(ledger):
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    ledger.record(IncomingTransaction(account_id=bank, date=d(2025, 11, 3), amount=D("-80"), description="spesa",
                                      status="BOOK", source="psd2", balancing_account_id=ledger.category("Spesa")))
    today = d(2026, 1, 15)
    before = (ledger.conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0],
              ledger.spend_between(d(2025, 1, 1), today), compute_metrics(ledger, today).liquidity)
    seeded(ledger)
    service.snapshot_through(ledger, today)
    service.overview(ledger, today)
    ledger.validate()   # the double-entry check of section 5.4 still holds, and nothing was added to it
    after = (ledger.conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0],
             ledger.spend_between(d(2025, 1, 1), today), compute_metrics(ledger, today).liquidity)
    assert before == after


def test_a_reconciliation_shows_both_figures_and_corrects_neither(ledger):
    seeded(ledger)
    ledger.set_setting(service.reported_key(1), "19")   # the broker says 19, the trades say 20
    rows = {r["label"]: r for r in service.reconciliations(ledger, d(2026, 1, 15))}
    units = rows["Quote di MSCI World contro la posizione del broker"]
    assert (units["expected"], units["actual"], units["difference"]) == ("20", "19", "-1")
    assert ledger.setting(service.reported_key(1)) == "19"                       # nothing was absorbed
    assert sum(D(t["units"]) for t in ledger.trades(1)) == 20
    paid = rows["Trattenuto contro investito"]
    assert (paid["expected"], paid["actual"], paid["note"]) == ("350.00", "200.00", "la differenza è in transito")
    fund_units = rows["Quote del fondo contro il prospetto"]
    assert fund_units["difference"] == "0.000000"


def test_the_etf_returns_follow_from_the_trade_prices(ledger):
    seeded(ledger)
    result = service.overview(ledger, d(2026, 1, 15))
    position = next(p for p in result["positions"] if p["name"] == "MSCI World")
    # 10 units 10 → 12, then 20 units 12 → 13.2: 1.2 × 1.1.
    assert position["twr"] == "32.00" and position["value"] == "264.00"
    rate = D(position["mwr"]) / 100
    npv = sum(float(a) * (1 + float(rate)) ** -((day - d(2025, 1, 1)).days / 365)
              for day, a in [(d(2025, 1, 1), -100), (d(2025, 7, 1), -120), (d(2026, 1, 15), 264)])
    assert abs(npv) < 0.01


def test_the_whole_portfolio_chains_the_months_with_each_months_payments_taken_out(ledger):
    etf_id = etf(ledger)
    ledger.record_trade(etf_id, d(2025, 1, 1), D(10), D(10), D(100), D(0), "broker", "a")
    ledger.record_trade(etf_id, d(2025, 7, 1), D(10), D(12), D(120), D(0), "broker", "b")
    ledger.set_price(etf_id, d(2025, 6, 30), D(12), "broker")
    ledger.set_price(etf_id, d(2025, 12, 31), D("13.2"), "broker")
    service.take_snapshot(ledger, "2025-06")
    service.take_snapshot(ledger, "2025-12")
    total = service.overview(ledger, d(2026, 1, 15))["total"]
    # June: 120 paid 100. December: 264 paid 220, of which 120 went in during the period,
    # so the 144 that grew from 120 is a return of 20%.
    assert total["twr"] == "20.00" and total["mwr"] is not None


def test_the_fund_shows_what_is_still_in_transit(ledger):
    _, fund_id = seeded(ledger)
    ledger.set_price(fund_id, d(2025, 12, 31), D("12"), "pagina")
    result = service.overview(ledger, d(2026, 1, 15))
    assert result["fund"] == {"withheld": "350.00", "invested": "200.00", "in_transit": "150.00"}
    position = next(p for p in result["positions"] if p["name"] == "Fondo")
    assert position["value"] == "390.00" and position["price"] == "12"   # 20 × 12 + 150


def test_a_missing_price_is_said_on_the_screen_too(ledger):
    etf(ledger)
    ledger.record_trade(1, d(2025, 1, 1), D(10), D(10), D(100), D(0), "broker", "a")
    result = service.overview(ledger, d(2026, 1, 15))
    assert result["missing"] == ["MSCI World: manca il prezzo"]
    assert result["positions"][0]["value"] is None


def test_the_house_counts_in_the_net_worth_and_not_in_the_returns(ledger):
    house = ledger.add_instrument("Casa", "immobile", source="manuale", ownership="0.5")
    ledger.set_price(house, d(2025, 12, 31), D(200000), "manuale")
    assert service.take_snapshot(ledger, "2025-12").written == 1
    row = ledger.snapshots()[0]
    assert (row["value"], row["paid"]) == ("100000.00", "0.00")
    position = service.overview(ledger, d(2026, 1, 15))["positions"][0]
    assert position["twr"] is None and position["mwr"] is None and position["paid"] is None


# -- the opening: declared once, explained by the documents, then retired --------------

OPENING = Opening(d(2025, 6, 30), D(20), D(12), D(220))


def test_an_etf_opening_counts_only_the_trades_after_it(ledger):
    etf_id = etf(ledger)
    ledger.record_trade(etf_id, d(2025, 1, 1), D(10), D(10), D(100), D(0), "broker", "a")   # inside the opening
    ledger.record_trade(etf_id, d(2025, 9, 1), D(5), D("12.5"), D("62.5"), D(0), "broker", "c")
    ledger.set_price(etf_id, d(2025, 12, 31), D(13), "broker")
    service.open_position(ledger, "MSCI World", OPENING)
    held = service.holding(ledger, ledger.instrument("MSCI World"), d(2025, 12, 31), exact=True)
    assert (held.units, held.paid, held.value) == (D(25), D("282.5"), D(325))
    # Before the opening nothing is known for certain, so nothing is held.
    assert service.holding(ledger, ledger.instrument("MSCI World"), d(2025, 3, 31)).units == 0
    with pytest.raises(ValueError, match="già un'apertura"):
        service.open_position(ledger, "MSCI World", OPENING)


def test_the_documents_before_the_opening_reconcile_against_it_and_then_it_retires(ledger):
    etf_id = etf(ledger)
    ledger.record_trade(etf_id, d(2025, 1, 1), D(10), D(10), D(100), D(0), "broker", "a")
    service.open_position(ledger, "MSCI World", OPENING)
    row = {r["label"]: r for r in service.reconciliations(ledger, d(2026, 1, 15))}["Apertura di MSCI World contro i documenti"]
    assert (row["expected"], row["actual"], row["difference"]) == ("20", "10", "-10")
    ledger.record_trade(etf_id, d(2025, 6, 2), D(10), D(12), D(120), D(0), "broker", "b")   # the missing contract
    row = {r["label"]: r for r in service.reconciliations(ledger, d(2026, 1, 15))}["Apertura di MSCI World contro i documenti"]
    assert row["difference"] == "0" and "si può ritirare" in row["note"]
    service.retire_opening(ledger, "MSCI World")
    held = service.holding(ledger, ledger.instrument("MSCI World"), d(2025, 12, 31))
    assert (held.units, held.paid) == (D(20), D(220))   # the documents alone, the same position


def test_with_an_opening_the_pac_compares_only_what_was_sent_and_bought_after_it(ledger):
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    investments = ledger.ensure_account(Account(name="Investimenti", type="virtual"))
    for day in (d(2025, 3, 1), d(2025, 8, 1)):   # one transfer inside the opening, one after it
        ledger.record(IncomingTransaction(account_id=bank, date=day, amount=D("-62.5"), description="pac",
                                          status="BOOK", source="psd2", balancing_account_id=investments))
    etf_id = etf(ledger)
    ledger.record_trade(etf_id, d(2025, 8, 2), D(5), D("12.5"), D("62.5"), D(0), "broker", "c")
    service.open_position(ledger, "MSCI World", OPENING)
    row = service.reconciliations(ledger, d(2026, 1, 15))[0]
    assert (row["expected"], row["actual"], row["difference"]) == ("62.50", "62.50", "0.00")
    assert row["note"] == "dal 2025-07-01, dopo l'apertura"


def test_the_returns_start_from_the_value_of_the_opening(ledger):
    etf_id = etf(ledger)
    ledger.record_trade(etf_id, d(2025, 1, 1), D(20), D(5), D(100), D(0), "broker", "a")   # an old, cheap trade
    ledger.set_price(etf_id, d(2025, 12, 31), D("13.2"), "broker")
    service.open_position(ledger, "MSCI World", OPENING)
    position = service.overview(ledger, d(2026, 1, 15))["positions"][0]
    # 20 units from 12 to 13.2: what grew before the opening is not a return of these months.
    assert position["twr"] == "10.00" and position["paid"] == "220.00"
    assert position["note"] == "rendimenti dall'apertura del 2025-06-30"
    rate = float(D(position["mwr"]) / 100)
    npv = -240 + 264 * (1 + rate) ** -((d(2026, 1, 15) - d(2025, 6, 30)).days / 365)
    assert abs(npv) < 0.01


def test_a_fund_opening_contains_the_payslips_up_to_its_date(ledger):
    fund_id = fund(ledger)
    # January invested before the opening, February withheld before it and invested after.
    service.read_documents(ledger, documents_from(payslips(), [
        operation(d(2025, 2, 20), "100", "10", reference="gen"), operation(d(2025, 4, 15), "100", "10", reference="feb")],
        units=D(20)))
    service.open_position(ledger, "Fondo", Opening(d(2025, 2, 28), D(10), D(10), D(100)))
    ledger.set_price(fund_id, d(2025, 12, 31), D(12), "pagina")
    held = service.holding(ledger, ledger.instrument("Fondo"), d(2025, 12, 31), exact=True)
    # February's units came after the opening and add to it; only March's money is new and in transit.
    assert (held.units, held.paid, held.value) == (D(20), D(250), D(390))
    rows = {r["label"]: r for r in service.reconciliations(ledger, d(2026, 1, 15))}
    assert rows["Apertura di Fondo contro i documenti"]["difference"] == "0"
    assert (rows["Trattenuto contro investito"]["expected"], rows["Trattenuto contro investito"]["actual"]) == ("150.00", "0.00")
    assert rows["Quote del fondo contro il prospetto"]["difference"] == "0"
    # The opening's unit value is the price of its day, so its month asks for nothing.
    assert ledger.price_at(fund_id, d(2025, 2, 28))["source"] == "apertura"
    assert service.nav_missing(ledger, d(2025, 6, 15))[0] == "2025-03"


def test_a_coupon_credited_gross_is_netted_by_its_tax_and_only_looked_for_since_the_account(ledger):
    bank = ledger.ensure_account(Account(name="Fineco", type="real"))
    for amount, text in (("102.50", "Ced.su 10.000 BTP"), ("-12.81", "Rit.ced.su 10.000 BTP")):
        ledger.record(IncomingTransaction(account_id=bank, date=d(2025, 10, 10), amount=D(amount), description=text,
                                          status="BOOK", source="psd2", balancing_account_id=ledger.category("Cedole")))
    ledger.add_instrument("BTP Valore", "btp", source="calcolato", terms=json.dumps({
        "nominal": "10000", "start": "2023-10-10", "rates": ["4.10"] * 3 + ["4.50"] * 2, "tax": "12.5",
        "bonus": "0.5", "account": "Fineco", "credit_text": "Ced.su", "credits_from": "2025-09-01",
        "withholding_text": "Rit.ced"}))
    row = service.reconciliations(ledger, d(2025, 11, 1))[0]
    assert (row["expected"], row["actual"], row["difference"], row["note"]) == ("89.69", "89.69", "0.00", None)


def test_the_opening_is_declared_and_retired_from_the_command_line(tmp_path, capsys):
    from tests.test_amonhen_cli import run

    db = tmp_path / "cli.db"
    assert run(db, "instrument-add", "MSCI World", "--kind", "etf", "--source", "broker") == 0
    assert run(db, "position-open", "MSCI World", "--date", "2025-06-30", "--units", "20") == 2
    args = ("position-open", "MSCI World", "--date", "2025-06-30", "--units", "20", "--price", "12", "--paid", "220")
    assert run(db, *args) == 0 and run(db, *args) == 2
    assert run(db, "position-open", "MSCI World", "--retire") == 0
    assert run(db, "position-open", "MSCI World", "--retire") == 2
    assert "ritirata" in capsys.readouterr().out


# -- the API ---------------------------------------------------------------------------

@pytest.fixture
def api(tmp_path):
    db_path = tmp_path / "portfolio.db"
    conn = connect(db_path)
    initialize(conn)
    conn.close()
    client = TestClient(create_app(db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG,
                                   clock=FixedClock(d(2026, 1, 15))))
    yield client, db_path
    client.close()


def test_an_empty_portfolio_answers_and_has_nothing_to_show(api):
    client, _ = api
    body = client.get("/api/portfolio").json()
    assert body["positions"] == [] and body["series"] == [] and body["fund"] is None
    assert body["total"] == {"value": "0.00", "mwr": None, "twr": None}


def test_the_api_reads_what_the_use_cases_wrote(api):
    client, db_path = api
    ledger = Ledger(connect(db_path))
    seeded(ledger)
    service.snapshot_through(ledger, d(2026, 1, 15))
    ledger.conn.close()
    body = client.get("/api/portfolio").json()
    assert {p["name"] for p in body["positions"]} == {"MSCI World", "Fondo"}
    assert body["fund"]["in_transit"] == "150.00"
    assert client.post("/api/portfolio", json={}).status_code == 405


def test_a_missing_unit_value_is_written_by_hand_through_the_api(api):
    client, db_path = api
    ledger = Ledger(connect(db_path))
    seeded(ledger)
    ledger.conn.close()
    body = client.get("/api/portfolio").json()
    assert body["nav_missing"][:2] == ["2025-04", "2025-05"]
    after = client.post("/api/portfolio/nav", json={"month": "2025-04", "value": "10.2"}).json()
    assert "2025-04" not in after["nav_missing"]
    assert client.post("/api/portfolio/nav", json={"month": "aprile", "value": "10"}).status_code == 422
    assert client.post("/api/portfolio/nav", json={"month": "2025-05", "value": "0"}).status_code == 422
    wrong = client.post("/api/portfolio/nav", json={"month": "2025-05", "value": "abc"})
    assert wrong.status_code == 422 and wrong.json()["detail"] == "'abc' non è un numero"
