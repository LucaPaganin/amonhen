"""The plan (desiderata 5.16): goals, profile, tax years, the margin, fund against PAC."""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from amonhen.api.app import create_app
from amonhen.core.planning import TAX_KEYS, compare, complete_year, exit_rate, income_tax, parse_brackets
from amonhen.db import connect, initialize
from amonhen.ledger import Ledger
from amonhen.models import Account, IncomingTransaction
from amonhen.services.planning import margin
from tests.fixed_clock import FixedClock
from tests.test_amonhen_cli import MINIMAL_CONFIG

BRACKETS = "28000:23, 50000:35, :43"
TAX = {
    "irpef_brackets": BRACKETS,
    "regional_surtax": "0",
    "municipal_surtax": "0",
    "employee_social_rate": "10",
    "deduction_cap": "5300",
    "exit_rate": "15",
    "exit_rate_step": "0.30",
    "exit_rate_floor": "9",
    "exit_rate_free_years": "15",
    "fund_return_tax": "20",
    "etf_gain_tax": "26",
    "stamp_duty": "0",
}
PROFILE = {
    "gross_monthly": "3000",
    "months_paid": "14",
    "contribution_base": "40000",
    "own_rate": "1.2",
    "employer_rate": "1.5",
    "fund_joined": "2026-01-01",
}


def one(fund, pac="0", *, years=1, rate="0", participation=1, reachable=True, tax=TAX):
    return compare(Decimal(fund), Decimal(pac), PROFILE, tax, years, participation, Decimal(rate), reachable)


def test_the_tax_runs_on_the_brackets():
    brackets = parse_brackets(BRACKETS)
    assert income_tax(Decimal(20000), brackets, Decimal(0)) == Decimal("4600")
    # 37,800 down to 27,800 crosses into the first bracket: 9,800 at 35%, 200 at 23%.
    saved = income_tax(Decimal(37800), brackets, Decimal(0)) - income_tax(Decimal(27800), brackets, Decimal(0))
    assert saved == Decimal("3476")
    with pytest.raises(ValueError):
        parse_brackets("28000:23, 50000:35")  # the last bracket is open


def test_the_employer_pays_only_above_the_own_contractual_share():
    below = one("400")  # 1.2% of 40,000 is 480
    assert below.employer_lost and below.employer == 0
    above = one("3000")
    assert not above.employer_lost and above.employer == Decimal("600.00")


def test_the_cap_holds_the_employer_and_not_the_tfr():
    within = one("3000")
    assert within.deductible == Decimal("3000.00")
    assert within.cap_room == Decimal("1700.00")  # 5,300 − 600 − 3,000
    over = one("5000")
    assert over.deductible == Decimal("4700.00")
    assert over.cap_room == Decimal("-300.00")


def test_the_saving_is_the_marginal_tax_on_the_deduction():
    # 3,000 × 14 less 10% is 37,800, in the 35% bracket.
    assert one("3000").tax_saving == Decimal("1050.00")


def test_the_exit_rate_falls_after_fifteen_years_down_to_the_floor():
    assert exit_rate(TAX, 10) == Decimal("15")
    assert exit_rate(TAX, 20) == Decimal("13.50")
    assert exit_rate(TAX, 40) == Decimal("9")


def test_one_year_at_zero_return_shows_only_the_taxes():
    result = one("3000", "1000")
    # The fund: 3,000 own and 600 employer, all deducted, 15% at the exit.
    assert result.fund_net == Decimal("3060.00")
    # The PAC: 1,000 and the 1,050 saved, no gain to tax.
    assert result.pac_net == Decimal("2050.00")
    assert result.reachable == Decimal("5110.00")
    assert result.yearly == Decimal("4000.00")


def test_a_goal_that_needs_its_money_does_not_count_the_fund():
    result = one("3000", "1000", reachable=False)
    assert result.reachable == result.pac_net


def test_the_pac_pays_the_tax_on_the_gain_only():
    result = one("0", "1000", rate="10")
    # 1,000 grows to 1,100; 26% of the 100 gained.
    assert result.pac_net == Decimal("1074.00")


def test_a_missing_year_is_never_filled_from_another():
    full = dict.fromkeys(TAX_KEYS, "x")
    assert complete_year({2025: full, 2026: {"deduction_cap": "x"}}, 2026) == 2025
    assert complete_year({2027: full}, 2026) is None
    assert complete_year({}, 2026) is None


# -- the ledger --------------------------------------------------------------

def test_a_goal_holds_from_a_day_and_a_change_keeps_the_past(ledger):
    first = ledger.save_goal(None, "Casa", "50000", dt.date(2030, 6, 1), "alla_data", dt.date(2026, 1, 1))
    ledger.save_goal(first, "Casa", "60000", dt.date(2030, 6, 1), "alla_data", dt.date(2026, 6, 1))
    assert ledger.goals_at(dt.date(2026, 3, 1))[0]["amount"] == "50000.00"
    assert ledger.goals_at(dt.date(2026, 7, 1))[0]["amount"] == "60000.00"
    ledger.end_goal(first, dt.date(2026, 9, 1))
    assert ledger.goals_at(dt.date(2026, 9, 1)) == []
    assert ledger.goals_at(dt.date(2026, 7, 1))[0]["series"] == first


def test_the_base_of_the_contribution_is_its_own_fact(ledger):
    ledger.set_profile_fact("gross_monthly", "3000", dt.date(2025, 1, 1))
    ledger.set_profile_fact("contribution_base", "40000", dt.date(2025, 1, 1))
    ledger.set_profile_fact("gross_monthly", "3300", dt.date(2026, 7, 1))
    later = ledger.profile_at(dt.date(2026, 8, 1))
    assert later["gross_monthly"]["value"] == "3300.00"
    assert later["contribution_base"]["value"] == "40000.00"
    assert ledger.profile_at(dt.date(2026, 6, 1))["gross_monthly"]["value"] == "3000.00"
    with pytest.raises(ValueError):
        ledger.set_profile_fact("salary", "1", dt.date(2026, 1, 1))


def test_a_tax_parameter_carries_its_source(ledger):
    with pytest.raises(ValueError):
        ledger.set_tax_parameter(2026, "deduction_cap", "5300", " ")
    ledger.set_tax_parameter(2026, "deduction_cap", "5300", "Legge di bilancio 2026")
    assert ledger.tax_parameters()[2026]["deduction_cap"]["source"] == "Legge di bilancio 2026"


def spend(ledger, account, day, amount, category):
    ledger.record(IncomingTransaction(
        account_id=account, date=day, amount=Decimal(amount), description=category,
        status="BOOK", source="psd2", balancing_account_id=ledger.category(category),
    ))


def test_the_margin_is_read_on_the_twelve_complete_months(ledger):
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    for month in range(1, 13):
        spend(ledger, bank, dt.date(2025, month, 27), "2000", "Stipendio")
        spend(ledger, bank, dt.date(2025, month, 10), "-1500", "Spesa")
    # Two extra monthly payments: the year counts them, the ordinary month does not.
    spend(ledger, bank, dt.date(2025, 7, 28), "2000", "Stipendio")
    spend(ledger, bank, dt.date(2025, 12, 28), "2000", "Stipendio")
    ledger.conn.execute("UPDATE accounts SET income = 1 WHERE name = 'Stipendio'")
    spend(ledger, bank, dt.date(2026, 1, 5), "-999", "Spesa")  # the month in progress is out

    reading = margin(ledger, dt.date(2026, 1, 15))
    assert reading["months"] == 12 and not reading["partial"]
    assert reading["total"] == "10000.00"
    assert reading["ordinary_monthly"] == "500.00"


# -- the API -----------------------------------------------------------------

@pytest.fixture
def api(tmp_path):
    db_path = tmp_path / "plan.db"
    conn = connect(db_path)
    initialize(conn)
    conn.close()
    client = TestClient(create_app(
        db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG,
        clock=FixedClock(dt.date(2026, 11, 16)),
    ))
    yield client
    client.close()


def test_the_comparison_says_the_year_it_used_and_the_one_missing(api):
    plan = api.put("/api/plan/goals", json={
        "name": "Pensione", "amount": "500000", "target_date": "2056-01-01",
        "liquidity": "vincolabile", "valid_from": "2026-11-01",
    }).json()
    series = plan["goals"][0]["series"]
    for key, value in PROFILE.items():
        assert api.put(f"/api/plan/profile/{key}", json={"value": value, "valid_from": "2026-01-01"}).status_code == 200

    asked = {"series": series, "return_rate": "4",
             "allocations": [{"fund": "5300", "pac": "0"}, {"fund": "500", "pac": "4800"}]}
    refused = api.post("/api/plan/compare", json=asked)
    assert refused.status_code == 422 and "parametri fiscali" in refused.json()["detail"]

    for key, value in TAX.items():
        api.put(f"/api/plan/tax/2025/{key}", json={"value": value, "source": "fonte 2025"})
    plan = api.get("/api/plan").json()
    assert plan["tax"]["used_year"] == 2025
    assert "deduction_cap" in plan["tax"]["current_missing"]

    result = api.post("/api/plan/compare", json=asked).json()
    assert result["tax_year"] == 2025 and result["tax_missing_year"] == 2026
    assert result["years"] == 29
    first, second = result["allocations"]
    assert first["cap_room"] == "-600.00" and second["employer_lost"] is False
    assert first["yearly"] == second["yearly"] == "5300.00"


def test_an_unknown_goal_is_not_found(api):
    response = api.post("/api/plan/compare", json={
        "series": 9, "return_rate": "4", "allocations": [{"fund": "1", "pac": "1"}] * 2,
    })
    assert response.status_code == 404
