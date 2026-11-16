"""The plan (desiderata 5.16): goals, profile, tax years, the margin, and fund against PAC.

The answers are dicts ready for JSON, money as text, as `budgets.budget_month` does.
The system shows what two allocations lead to; it never proposes one (section 3).
"""
from __future__ import annotations

import datetime as dt
import statistics
from decimal import Decimal

from amonhen.core.planning import LIQUIDITY, PROFILE_KEYS, TAX_KEYS, AllocationResult, compare, complete_year
from amonhen.ledger import Ledger
from amonhen.metrics import _first_month_with_data, _month_bounds, _month_index, _month_key, period_summary
from amonhen.models import format_decimal, parse_decimal


def overview(ledger: Ledger, today: dt.date) -> dict:
    profile = ledger.profile_at(today)
    years = ledger.tax_parameters()
    return {
        "today": today.isoformat(),
        "goals": [_goal(row) for row in ledger.goals_at(today)],
        "liquidity_kinds": list(LIQUIDITY),
        "profile": [
            {
                "key": key,
                "label": label,
                "kind": kind,
                "value": profile[key]["value"] if key in profile else None,
                "valid_from": profile[key]["valid_from"] if key in profile else None,
            }
            for key, (label, kind) in PROFILE_KEYS.items()
        ],
        "tax": _tax(years, today.year),
        "margin": margin(ledger, today),
    }


def margin(ledger: Ledger, today: dt.date) -> dict:
    """What is left of income after spending over the 12 complete months, and in an ordinary month.

    The year counts the extra monthly payments and the quarterly income once each;
    the ordinary month is the median of the twelve, which those few months do not move,
    because money that arrives three times a year cannot be paid in every month.
    """
    last = _month_index(today) - 1
    earliest = _first_month_with_data(ledger)
    first = last - 11 if earliest is None else max(earliest, last - 11)
    months = []
    for index in range(first, last + 1):
        start, end = _month_bounds(index)
        reading = period_summary(ledger, start, end)
        months.append({"month": _month_key(index), "income": reading.income, "margin": reading.balance})
    margins = [month["margin"] for month in months]
    total = sum(margins, Decimal(0))
    return {
        "months": len(months),
        "partial": len(months) < 12,
        "total": format_decimal(total),
        # A short ledger still says what a year would be at its pace, and `partial` says so.
        "yearly": format_decimal(total / len(months) * 12) if months else None,
        "ordinary_monthly": format_decimal(statistics.median(margins)) if margins else None,
        "series": [
            {"month": m["month"], "income": format_decimal(m["income"]), "margin": format_decimal(m["margin"])}
            for m in months
        ],
    }


def comparison(
    ledger: Ledger,
    today: dt.date,
    series: int,
    return_rate: str,
    allocations: list[tuple[str, str]],
) -> dict:
    """Two allocations side by side, for one goal, with the tax year they used."""
    goal = next((row for row in ledger.goals_at(today) if row["series"] == series), None)
    if goal is None:
        raise LookupError(f"nessun obiettivo {series} oggi")
    profile = {key: row["value"] for key, row in ledger.profile_at(today).items()}
    missing = [PROFILE_KEYS[key][0] for key in PROFILE_KEYS if key not in profile]
    if missing:
        raise ValueError("mancano nel profilo: " + ", ".join(missing))
    years = ledger.tax_parameters()
    used = complete_year(years, today.year)
    if used is None:
        raise ValueError("nessun anno ha tutti i parametri fiscali: il confronto non si calcola")
    tax = {key: row["value"] for key, row in years[used].items()}

    target = dt.date.fromisoformat(goal["target_date"])
    horizon = (target.year - today.year) * 12 + target.month - today.month
    if horizon < 12:
        raise ValueError("l'obiettivo è a meno di un anno: un confronto anno per anno non ha senso")
    rate = parse_decimal(return_rate)
    if not rate.is_finite() or not Decimal(-100) < rate <= 100:
        raise ValueError("il rendimento è una percentuale annua")
    joined = dt.date.fromisoformat(profile["fund_joined"])
    results = [
        compare(
            parse_decimal(fund),
            parse_decimal(pac),
            profile,
            tax,
            years=horizon // 12,
            participation_years=target.year - joined.year,
            return_rate=rate,
            fund_reachable=goal["liquidity"] == "vincolabile",
        )
        for fund, pac in allocations
    ]
    yearly_margin = margin(ledger, today)["yearly"]
    return {
        "goal": _goal(goal),
        "years": horizon // 12,
        "return_rate": str(rate),
        "tax_year": used,
        "tax_missing_year": None if used == today.year else today.year,
        "margin_yearly": yearly_margin,
        "allocations": [_allocation(result) for result in results],
    }


def _goal(row) -> dict:
    return {
        "series": row["series"],
        "name": row["name"],
        "amount": row["amount"],
        "target_date": row["target_date"],
        "liquidity": row["liquidity"],
        "valid_from": row["valid_from"],
    }


def _tax(years: dict, current: int) -> dict:
    used = complete_year(years, current)
    written = years.get(current, {})
    return {
        "current_year": current,
        "used_year": used,
        # What the current year still lacks; empty when it is complete.
        "current_missing": [key for key in TAX_KEYS if key not in written],
        "keys": [{"key": key, "label": label, "kind": kind} for key, (label, kind) in TAX_KEYS.items()],
        "years": [
            {
                "year": year,
                "complete": set(TAX_KEYS) <= set(values),
                "values": [
                    {"key": key, "value": row["value"], "source": row["source"]} for key, row in values.items()
                ],
            }
            for year, values in sorted(years.items(), reverse=True)
        ],
    }


def _allocation(result: AllocationResult) -> dict:
    money = (
        "fund", "pac", "employer", "deductible", "cap_room", "tax_saving",
        "fund_net", "pac_net", "reachable", "yearly",
    )
    payload = {name: format_decimal(getattr(result, name)) for name in money}
    payload.update(
        employer_lost=result.employer_lost,
        exit_rate=str(result.exit_rate),
        fund_reachable=result.fund_reachable,
    )
    return payload
