"""Projections by scenario (desiderata 5.16): every goal under the three scenarios, and Coast FI.

The answer is a dict ready for JSON, money as text. It says whether a goal is reached at
the pace written, never what to do about it (section 3).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from amonhen.core.projection import SCENARIOS, coast_fi, project
from amonhen.ledger import Ledger
from amonhen.metrics import complete_months
from amonhen.models import format_decimal, parse_decimal


def scenarios_payload(ledger: Ledger) -> list[dict]:
    written = ledger.scenarios()
    return [
        {
            "name": name,
            "real_return": written[name]["real_return"] if name in written else None,
            "inflation": written[name]["inflation"] if name in written else None,
        }
        for name in SCENARIOS
    ]


def observed_monthly(ledger: Ledger, today: dt.date) -> dict:
    """What went into investments each month, on average over the 12 complete months."""
    months = complete_months(ledger, today, 12)
    if not months:
        return {"months": 0, "monthly": None}
    total = ledger.invested_between(months[0][1], months[-1][2])
    return {"months": len(months), "monthly": format_decimal(total / len(months))}


def projection(ledger: Ledger, today: dt.date, start: str, monthly: str | None, scenario: str) -> dict:
    """Each goal of today under the three scenarios, and Coast FI in ``scenario``."""
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario sconosciuto: {scenario}")
    written = ledger.scenarios()
    missing = [name for name in SCENARIOS if name not in written]
    if missing:
        raise ValueError("mancano gli scenari: " + ", ".join(missing))
    capital = parse_decimal(start)
    if not capital.is_finite() or capital < 0:
        raise ValueError("il capitale di partenza non è negativo")
    pace = observed_monthly(ledger, today)["monthly"] if monthly is None else monthly
    payment = parse_decimal(pace if pace is not None else "0")
    if not payment.is_finite():
        raise ValueError("il versamento mensile è una cifra")

    goals = []
    for row in ledger.goals_at(today):
        target = dt.date.fromisoformat(row["target_date"])
        months = (target.year - today.year) * 12 + target.month - today.month
        amount = parse_decimal(row["amount"])
        entry = {
            "goal": {key: row[key] for key in ("series", "name", "amount", "target_date", "liquidity", "valid_from")},
            "months": months,
            "projections": [],
            "coast": None,
        }
        if months < 1:
            entry["note"] = "la data è già passata"
            goals.append(entry)
            continue
        for name in SCENARIOS:
            rate, inflation = parse_decimal(written[name]["real_return"]), parse_decimal(written[name]["inflation"])
            result = project(amount, capital, payment, rate, inflation, months)
            entry["projections"].append({
                "scenario": name,
                "real_return": written[name]["real_return"],
                "inflation": written[name]["inflation"],
                **{key: format_decimal(getattr(result, key)) for key in
                   ("value", "shortfall", "needed_monthly", "goal_nominal")},
                "reaches": result.reaches,
            })
        # Coast FI is for the goal that may stay locked: what is left free once it is passed.
        if row["liquidity"] == "vincolabile":
            needed = coast_fi(amount, parse_decimal(written[scenario]["real_return"]), months)
            entry["coast"] = {
                "scenario": scenario,
                "capital": format_decimal(needed),
                "reached": capital >= needed,
            }
        goals.append(entry)
    return {
        "today": today.isoformat(),
        "start": format_decimal(capital),
        "monthly": format_decimal(payment),
        "monthly_observed": monthly is None,
        "scenario": scenario,
        "goals": goals,
    }
