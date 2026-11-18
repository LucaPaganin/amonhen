"""The portfolio's real sources (desiderata 5.16): the parser at the edge, Paperless, Borsa Italiana,
and the commands that declare and load. Every figure here is invented: no document enters this
repository, which is public."""
import datetime as dt
import json
from decimal import Decimal as D

import payslip_parser
import pytest
import responses

from amonhen import cli
from amonhen.adapters import payslips
from amonhen.adapters.borsa_italiana import PAGE, BorsaItalianaNav, read_page
from amonhen.adapters.paperless import PaperlessDocuments
from amonhen.db import connect, initialize
from amonhen.ledger import Ledger
from amonhen.ports.portfolio import NavUnavailable, SourceUnavailable
from tests.fixed_clock import FixedClock
from tests.memory_portfolio import MemoryNav, documents_from

d = dt.date


def a_payslip(pension=True):
    return payslip_parser.Payslip(
        layout="finto", employer="Datore", period=payslip_parser.Period(2026, 3), employee_id="0",
        gross_items_total=D("3000.00"), deductions_total=D("900.00"), social_contributions=D("275.70"),
        taxable_social=D("3000.00"), taxable_income=D("2724.30"), gross_tax=D("700.00"), net_tax=D("600.00"),
        net_pay=D("2100.00"),
        pension=payslip_parser.PensionFlows(D("36.00"), D("45.00"), D("207.00"), "Fondo") if pension else None,
        tfr=None, items=(),
    )


def a_statement():
    def op(day, employee, employer, tfr, nav, units):
        return payslip_parser.FundOperation(
            kind="contributo", operation_date=day, valuation_date=day, sub_fund="Azionario", employee=D(employee),
            employer=D(employer), tfr=D(tfr), other=D(0), fees=D(0), invested=D(employee) + D(employer) + D(tfr),
            nav=D(nav), units=D(units))
    switch = payslip_parser.FundOperation(
        kind="switch", operation_date=d(2025, 6, 1), valuation_date=d(2025, 6, 1), sub_fund="Azionario",
        employee=D(0), employer=D(0), tfr=D(0), other=D(0), fees=D("2.00"), invested=D(0), nav=D(10), units=D("-0.2"))
    return payslip_parser.PensionStatement(
        layout="finto", fund="Fondo", adhesion_type="collettiva", adhesion_date=d(2020, 1, 1), year=2025,
        sub_fund="Azionario", units_start=D(0), units_end=D("57.4"), nav_end=D(11), position_end=D("631.4"),
        paid_in_total=D(576), withdrawn_total=D(0), net_result=D("55.4"),
        operations=(op(d(2025, 4, 15), "72", "90", "126", "10", "28.8"), switch,
                    op(d(2025, 9, 15), "72", "90", "126", "10", "28.8")),
        non_deducted_contributions=D(0),
    )


# -- the parser, translated at the edge ---------------------------------------------

def test_a_payslip_becomes_a_withheld_contribution():
    read = payslips.read_document(5, "busta_paga", b"%PDF", parse=lambda _: a_payslip())
    assert read.error is None and read.layout == "finto"
    assert read.payslip == payslips.PayslipContribution("paperless:5", "2026-03", D("36.00"), D("45.00"), D("207.00"))


def test_a_payslip_without_pension_flows_withholds_nothing():
    read = payslips.read_document(5, "busta_paga", b"%PDF", parse=lambda _: a_payslip(pension=False))
    assert (read.payslip.own, read.payslip.employer, read.payslip.tfr) == (0, 0, 0)


def test_a_statement_keeps_its_contributions_and_drops_a_switch():
    read = payslips.read_document(9, "prospetto", b"%PDF", parse=lambda _: a_statement())
    ops = read.statement.operations
    assert [op.amount for op in ops] == [D(288), D(288)] and read.statement.units_end == D("57.4")
    assert ops[0].reference == "paperless:9:0" and ops[1].reference == "paperless:9:2"


def test_a_refusal_of_the_parser_is_an_error_and_never_a_guess():
    def refuse(_):
        raise payslip_parser.InvariantViolated("net_pay", D(1), D(2))
    read = payslips.read_document(5, "busta_paga", b"%PDF", parse=refuse)
    assert read.payslip is None and read.error.startswith("InvariantViolated: net_pay")


def test_a_document_of_the_other_kind_is_an_error():
    read = payslips.read_document(5, "prospetto", b"%PDF", parse=lambda _: a_payslip())
    assert read.statement is None and "tipo sbagliato" in read.error


def test_the_real_parser_refuses_bytes_that_are_not_a_pdf():
    assert payslips.read_document(5, "busta_paga", b"not a pdf").error.startswith("NotAPdf")


# -- Paperless --------------------------------------------------------------------

BASE = "http://paperless.test"


def paperless(**kwargs):
    return PaperlessDocuments(BASE, "secret", {"busta_paga": "Busta paga", "prospetto": "Prospetto"}, **kwargs)


@responses.activate
def test_new_documents_are_listed_by_type_after_the_cursor_across_pages():
    responses.get(f"{BASE}/api/document_types/", json={"results": [{"id": 3, "name": "Busta paga"}]})
    responses.get(f"{BASE}/api/documents/", json={"results": [{"id": 1, "modified": "2026-11-01T10:00:00+01:00"}],
                                                  "next": f"{BASE}/api/documents/?page=2"})
    responses.get(f"{BASE}/api/documents/?page=2", json={"results": [{"id": 2, "modified": "2026-11-02T10:00:00+01:00"}],
                                                         "next": None})
    found = paperless().list_new("busta_paga", "2026-10-31T00:00:00+01:00")
    assert found == [(1, "2026-11-01T10:00:00+01:00"), (2, "2026-11-02T10:00:00+01:00")]
    asked = responses.calls[1].request
    assert "document_type__id=3" in asked.url and "modified__gt=2026-10-31" in asked.url
    assert asked.headers["Authorization"] == "Token secret"


@responses.activate
def test_the_original_is_downloaded_not_the_archived_copy():
    responses.get(f"{BASE}/api/documents/1/download/", body=b"%PDF-original")
    seen = []
    read = paperless(parse=lambda pdf: seen.append(pdf) or a_payslip()).read("busta_paga", 1)
    assert "original=true" in responses.calls[0].request.url and seen == [b"%PDF-original"]
    assert read.payslip.reference == "paperless:1"


@responses.activate
def test_the_outcome_goes_back_as_a_tag_and_custom_fields_created_on_first_use():
    responses.get(f"{BASE}/api/documents/1/", json={"tags": [4, 8], "custom_fields": [{"field": 2, "value": "x"}]})
    responses.get(f"{BASE}/api/tags/?name__iexact=amonhen%3Aerrore", json={"results": [{"id": 8}]})
    responses.get(f"{BASE}/api/tags/?name__iexact=amonhen%3Aimportato", json={"results": []})
    responses.post(f"{BASE}/api/tags/", json={"id": 9})
    responses.get(f"{BASE}/api/custom_fields/?name__iexact=amonhen_periodo", json={"results": [{"id": 5}]})
    responses.get(f"{BASE}/api/custom_fields/?name__iexact=amonhen_proprio", json={"results": []})
    responses.post(f"{BASE}/api/custom_fields/", json={"id": 6})
    responses.patch(f"{BASE}/api/documents/1/", json={})
    paperless().report(1, "importato", {"amonhen_periodo": "2026-03", "amonhen_proprio": "36.00"})
    created = [json.loads(c.request.body) for c in responses.calls if c.request.method == "POST"]
    assert created == [{"name": "amonhen:importato"}, {"name": "amonhen_proprio", "data_type": "string"}]
    patch = json.loads(responses.calls[-1].request.body)
    # The old error tag goes, the other tags stay, and the fields already there are kept.
    assert patch["tags"] == [4, 9]
    assert patch["custom_fields"] == [{"field": 2, "value": "x"}, {"field": 5, "value": "2026-03"},
                                      {"field": 6, "value": "36.00"}]


@responses.activate
def test_a_missing_type_or_a_failing_api_is_unavailable():
    responses.get(f"{BASE}/api/document_types/", json={"results": []})
    with pytest.raises(SourceUnavailable, match="tipo di documento"):
        paperless().list_new("busta_paga", None)
    responses.get(f"{BASE}/api/documents/1/download/", status=500, body="boom")
    with pytest.raises(SourceUnavailable, match="500"):
        paperless().read("busta_paga", 1)


# -- Borsa Italiana ----------------------------------------------------------------

def page(value="12,345", day="30/10/26", klass="C"):
    """The shape of the class's page, with invented figures."""
    return f"""<html><head><script>var x = "Ultima";</script></head><body>
    <table><tr><th>Ultima</th><th>Precedente</th><th>Valuta</th><th>Data</th><th>Variazione</th></tr>
    <tr><td>{value}</td><td>12,000</td><td>EUR</td><td>{day}</td><td>+0,10</td></tr></table>
    <table><tr><td>Isin</td><td>N.D.</td></tr><tr><td>Classe</td><td>{klass}</td></tr></table></body></html>"""


def test_the_page_gives_the_last_value_its_date_and_its_class():
    assert read_page(page()) == (D("12.345"), d(2026, 10, 30), "C")
    assert read_page(page(value="1.234,5"))[0] == D("1234.5")
    with pytest.raises(ValueError):
        read_page("<html>altro</html>")


@responses.activate
def test_only_the_right_class_and_month_are_taken():
    responses.get(PAGE.format(page="TESTC"), body=page())
    nav = BorsaItalianaNav()
    assert nav.unit_value("TESTC", "c", "2026-10") == D("12.345")
    for fund_class, month, why in (("A", "2026-10", "classe C"), ("C", "2026-09", "2026-10-30")):
        with pytest.raises(NavUnavailable, match=why):
            nav.unit_value("TESTC", fund_class, month)
    responses.get(PAGE.format(page="GONE"), status=404)
    with pytest.raises(NavUnavailable):
        nav.unit_value("GONE", "C", "2026-10")


# -- the commands ------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    path = tmp_path / "ledger.db"
    conn = connect(path)
    initialize(conn)
    conn.close()
    return path


def run(db, *args, day=d(2026, 11, 18)):
    return cli.main(["--db", str(db), *args], clock=FixedClock(day))


def test_a_btp_is_declared_from_isin_nominal_and_purchase_date(db, capsys):
    assert run(db, "instrument-add", "BTP Valore", "--kind", "btp", "--source", "calcolato",
               "--isin", "IT0000000000", "--nominal", "10000") == 2
    assert "--start" in capsys.readouterr().err
    assert run(db, "instrument-add", "BTP Valore", "--kind", "btp", "--source", "calcolato", "--isin", "IT0000000000",
               "--nominal", "10000", "--start", "2025-01-10", "--rates", "4.10,4.10,4.10,4.50,4.50",
               "--tax", "12.5", "--bonus", "0.5", "--account", "Fineco", "--credit-text", "cedola") == 0
    terms = json.loads(Ledger(connect(db)).instrument("BTP Valore")["terms"])
    assert terms["rates"] == ["4.10"] * 3 + ["4.50"] * 2 and terms["account"] == "Fineco"
    assert run(db, "instrument-add", "BTP Valore", "--kind", "btp", "--source", "x", "--nominal", "1",
               "--start", "2025-01-10", "--rates", "1", "--tax", "0") == 2   # the name is taken


def test_the_price_history_loads_once(db, tmp_path, capsys):
    run(db, "instrument-add", "MSCI World", "--kind", "etf", "--source", "broker", "--isin", "IE00TEST")
    closes = tmp_path / "closes.csv"
    closes.write_text("date,close\n2024-11-29,9.50\n2024-12-31,9.80\n")
    assert run(db, "prices-load", "MSCI World", str(closes)) == 0
    assert run(db, "prices-load", "MSCI World", str(closes)) == 2
    assert "already loaded" in capsys.readouterr().err
    ledger = Ledger(connect(db))
    assert ledger.price_at(1, d(2024, 12, 31))["source"] == "storico"


def test_portfolio_sync_reads_documents_the_unit_value_and_snapshots(db, monkeypatch, capsys):
    from amonhen import composition
    from amonhen.core.portfolio import StatementOperation

    run(db, "instrument-add", "Fondo", "--kind", "fondo_pensione", "--source", "prospetto",
        "--class", "C", "--nav-page", "TESTC")
    slip = payslips.contribution(1, a_payslip())
    docs = documents_from([slip], [StatementOperation(d(2026, 4, 15), D(288), D(10), D("28.8"), "op")], D("28.8"))
    monkeypatch.setattr(composition, "document_source", lambda: docs)
    monkeypatch.setattr(composition, "nav_source", lambda: MemoryNav({"2026-10": D("11")}))
    assert run(db, "portfolio-sync") == 0
    out = capsys.readouterr().out
    assert "2 letti" in out and "1 contributi investiti" in out and "valore quota di 2026-10: letto" in out
    # April to September have no unit value: named, not borrowed from October.
    assert "2026-09 Fondo: manca il prezzo del 2026-09-30" in out


def test_portfolio_sync_without_paperless_says_so(db, monkeypatch, capsys):
    from amonhen import composition

    monkeypatch.setattr(composition, "document_source", lambda: None)
    assert run(db, "portfolio-sync") == 0
    assert "Paperless non configurato" in capsys.readouterr().out
