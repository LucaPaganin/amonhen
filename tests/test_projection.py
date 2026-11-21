"""Projections by scenario (desiderata 5.16): the arithmetic, the scenarios, Coast FI."""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from amonhen.api.app import create_app
from amonhen.core.projection import checked_rate, coast_fi, monthly_rate, needed_monthly, project, value_at
from amonhen.db import connect, initialize
from amonhen.models import Account, IncomingTransaction
from amonhen.services.projection import observed_monthly
from tests.fixed_clock import FixedClock
from tests.test_amonhen_cli import MINIMAL_CONFIG

D = Decimal


def stepped(start, monthly, annual, months):
    """The equation itself, month by month: what the closed form must agree with."""
    rate = monthly_rate(D(annual))
    value = D(start)
    for _ in range(months):
        value = value * (1 + rate) + D(monthly)
    return value


@pytest.mark.parametrize("annual", ["0", "4", "-2", "7.5"])
def test_the_closed_form_is_the_equation(annual):
    assert abs(value_at(D(1000), D(200), D(annual), 120) - stepped(1000, 200, annual, 120)) < D("0.0001")


def test_twelve_months_compound_to_the_yearly_return():
    assert abs(D(1000) * (1 + monthly_rate(D(5))) ** 12 - D(1050)) < D("0.0001")


def test_the_needed_monthly_reaches_the_goal_exactly():
    for annual in ("0", "3", "-1"):
        pay = needed_monthly(D(100000), D(5000), D(annual), 180)
        assert abs(value_at(D(5000), pay, D(annual), 180) - 100000) < D("0.0001")


def test_nothing_is_needed_when_the_start_alone_gets_there():
    assert needed_monthly(D(1000), D(5000), D(4), 24) == 0


def test_coast_fi_grows_to_the_goal_without_a_payment():
    capital = coast_fi(D(400000), D(4), 240)
    assert abs(value_at(capital, D(0), D(4), 240) - 400000) < D("0.0001")


def test_a_projection_says_whether_it_reaches_and_what_is_missing():
    short = project(D(10000), D(0), D(100), D(0), D(2), 60)
    assert short.value == D("6000.00") and not short.reaches
    assert short.shortfall == D("4000.00") and short.needed_monthly == D("166.67")
    assert short.goal_nominal == (D(10000) * D("1.02") ** 5).quantize(D("0.01"))
    assert project(D(10000), D(0), D(200), D(0), D(0), 60).reaches
    with pytest.raises(ValueError):
        project(D(1), D(0), D(0), D(0), D(0), 0)


def test_a_rate_is_a_yearly_percent():
    assert checked_rate(" -1.5 ") == "-1.5"
    for bad in ("-100", "101", "x"):
        with pytest.raises((ValueError, ArithmeticError)):
            checked_rate(bad)


# -- the ledger --------------------------------------------------------------

def paid(ledger, account, investments, day, amount):
    ledger.record(IncomingTransaction(
        account_id=account, date=day, amount=D(amount), description=f"PAC {day}",
        status="BOOK", source="psd2", balancing_account_id=investments,
    ))


def test_the_observed_pace_is_what_went_into_investments(ledger):
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    investments = ledger.ensure_account(Account(name="Investimenti", type="virtual"))
    ledger.record(IncomingTransaction(
        account_id=bank, date=dt.date(2025, 1, 2), amount=D("5"), description="x",
        status="BOOK", source="psd2", balancing_account_id=ledger.category("Altro"),
    ))
    for month in range(1, 13):
        paid(ledger, bank, investments, dt.date(2025, month, 15), "-300")
    paid(ledger, bank, investments, dt.date(2025, 6, 20), "100")  # a withdrawal nets out
    paid(ledger, bank, investments, dt.date(2026, 1, 3), "-999")  # the month in progress is out
    # 12 payments of 300 less a withdrawal of 100, over 12 months.
    assert observed_monthly(ledger, dt.date(2026, 1, 15)) == {"months": 12, "monthly": "291.67"}


def test_a_valuation_is_not_a_payment(ledger):
    broker = ledger.ensure_account(Account(name="Broker", type="real"))
    ledger.conn.execute("UPDATE accounts SET investment = 1 WHERE id = ?", (broker,))
    ledger.record_valuation(broker, dt.date(2025, 3, 31), D("1000"))
    ledger.record(IncomingTransaction(
        account_id=broker, date=dt.date(2025, 2, 1), amount=D("1"), description="x",
        status="BOOK", source="psd2", balancing_account_id=ledger.category("Altro"),
    ))
    assert ledger.invested_between(dt.date(2025, 1, 1), dt.date(2025, 12, 31)) == 0


def test_a_scenario_is_written_by_hand_and_a_wrong_one_is_refused(ledger):
    ledger.set_scenario("centrale", "3", "2")
    assert ledger.scenarios()["centrale"]["real_return"] == "3"
    with pytest.raises(ValueError):
        ledger.set_scenario("ottimo", "3", "2")
    with pytest.raises((ValueError, ArithmeticError)):
        ledger.set_scenario("prudente", "abc", "2")
    ledger.delete_scenario("centrale")
    assert ledger.scenarios() == {}


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


def goal(api, name, amount, target, liquidity):
    api.put("/api/plan/goals", json={"name": name, "amount": amount, "target_date": target,
                                      "liquidity": liquidity, "valid_from": "2026-11-01"})


def ask(api, **body):
    return api.post("/api/plan/projection", json={"scenario": "centrale", **body})


def test_a_missing_scenario_is_said_and_nothing_is_computed(api):
    goal(api, "Casa", "60000", "2031-06-01", "alla_data")
    api.put("/api/plan/scenarios/centrale", json={"real_return": "3", "inflation": "2"})
    refused = ask(api, start="1000", monthly="500")
    assert refused.status_code == 422 and "prudente, favorevole" in refused.json()["detail"]
    scenarios = api.get("/api/plan").json()["scenarios"]
    assert [(s["name"], s["real_return"]) for s in scenarios] == [
        ("prudente", None), ("centrale", "3"), ("favorevole", None)]


def test_every_goal_runs_under_three_scenarios_and_only_the_locked_one_has_coast_fi(api):
    goal(api, "Casa", "60000", "2031-06-01", "alla_data")
    goal(api, "Pensione", "400000", "2056-01-01", "vincolabile")
    goal(api, "Vecchio", "1000", "2026-01-01", "liquida")
    for name, ret, infl in (("prudente", "0", "3"), ("centrale", "3", "2"), ("favorevole", "5", "2")):
        api.put(f"/api/plan/scenarios/{name}", json={"real_return": ret, "inflation": infl})
    result = ask(api, start="20000", monthly="600").json()
    assert result["monthly_observed"] is False and result["scenario"] == "centrale"
    casa, pensione, vecchio = (next(g for g in result["goals"] if g["goal"]["name"] == n)
                               for n in ("Casa", "Pensione", "Vecchio"))
    assert [p["scenario"] for p in casa["projections"]] == ["prudente", "centrale", "favorevole"]
    assert casa["months"] == 55 and casa["coast"] is None
    # With no return, 20,000 and 55 payments of 600 make 53,000: short of 60,000 by 7,000.
    prudente = casa["projections"][0]
    assert prudente["value"] == "53000.00" and prudente["shortfall"] == "7000.00" and not prudente["reaches"]
    assert prudente["needed_monthly"] == "727.27"
    values = [D(p["value"]) for p in casa["projections"]]
    assert values == sorted(values) and values[0] < values[2]
    assert pensione["coast"]["scenario"] == "centrale" and not pensione["coast"]["reached"]
    assert vecchio["projections"] == [] and vecchio["note"] == "la data è già passata"


def test_the_pace_defaults_to_the_observed_one(api):
    goal(api, "Casa", "60000", "2031-06-01", "alla_data")
    for name in ("prudente", "centrale", "favorevole"):
        api.put(f"/api/plan/scenarios/{name}", json={"real_return": "1", "inflation": "2"})
    result = ask(api).json()
    assert result["monthly_observed"] is True and result["monthly"] == "0.00"
    assert ask(api, start="-1").status_code == 422
    assert ask(api, scenario="ottimo").status_code == 422
