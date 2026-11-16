"""Fund against PAC (desiderata 5.16): the arithmetic, on values a person wrote.

Pure: the profile and the tax year arrive as the texts they are stored as, the
horizon as whole years. Nothing here knows a database or what day it is.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from amonhen.models import format_decimal, parse_decimal

# What the ledger cannot see, each with how it is written. The base of the
# contribution is its own fact: payslips compute it on a contractual base that
# did not rise when the gross did (July 2026), so it is never derived from the gross.
PROFILE_KEYS: dict[str, tuple[str, str]] = {
    "gross_monthly": ("Lordo mensile", "euro"),
    "months_paid": ("Mensilità", "number"),
    "contribution_base": ("Base annua del versamento al fondo", "euro"),
    "own_rate": ("Percentuale propria", "percent"),
    "employer_rate": ("Percentuale del datore", "percent"),
    "fund_joined": ("Adesione al fondo", "date"),
}

# One tax year. Values are data a person writes in January with their source,
# never code: none of them has a default.
TAX_KEYS: dict[str, tuple[str, str]] = {
    "irpef_brackets": ("Scaglioni IRPEF", "brackets"),
    "regional_surtax": ("Addizionale regionale", "percent"),
    "municipal_surtax": ("Addizionale comunale", "percent"),
    "employee_social_rate": ("Contributi a carico del dipendente", "percent"),
    "deduction_cap": ("Tetto di deducibilità", "euro"),
    "exit_rate": ("Aliquota sulle prestazioni", "percent"),
    "exit_rate_step": ("Riduzione per anno oltre la soglia", "percent"),
    "exit_rate_floor": ("Aliquota minima sulle prestazioni", "percent"),
    "exit_rate_free_years": ("Anni di adesione prima della riduzione", "number"),
    "fund_return_tax": ("Imposta sui rendimenti del fondo", "percent"),
    "etf_gain_tax": ("Imposta sui guadagni degli ETF", "percent"),
    "stamp_duty": ("Bollo annuo sul deposito titoli", "percent"),
}

# How reachable a goal's money must stay: a buffer is spent any day, a purchase on
# its date, retirement can wait behind a lock.
LIQUIDITY = ("liquida", "alla_data", "vincolabile")

CENT = Decimal("0.01")


def checked(kind: str, text: str) -> str:
    """The value as it is stored, or ValueError saying what is wrong with it."""
    text = text.strip()
    if kind == "date":
        return dt.date.fromisoformat(text).isoformat()
    if kind == "brackets":
        brackets = parse_brackets(text)
        return ", ".join(f"{'' if limit is None else limit}:{rate}" for limit, rate in brackets)
    value = parse_decimal(text)
    if not value.is_finite() or value < 0 or (kind == "percent" and value > 100):
        raise ValueError(f"{text}: fuori dall'intervallo")
    # A rate keeps the digits it was written with (an addizionale of 1.233%).
    return format_decimal(value) if kind == "euro" else str(value)


def parse_brackets(text: str) -> list[tuple[Decimal | None, Decimal]]:
    """``"28000:23, 50000:35, :43"``: up to each limit its rate, the last one open."""
    brackets: list[tuple[Decimal | None, Decimal]] = []
    for part in text.split(","):
        limit, sep, rate = part.partition(":")
        if not sep:
            raise ValueError(f"scaglione senza aliquota: {part.strip()!r}")
        brackets.append((parse_decimal(limit) if limit.strip() else None, parse_decimal(rate)))
    limits = [limit for limit, _ in brackets[:-1]]
    if not brackets or brackets[-1][0] is not None or None in limits:
        raise ValueError("solo l'ultimo scaglione è aperto, e c'è")
    if limits != sorted(limits) or len(set(limits)) != len(limits):
        raise ValueError("i limiti degli scaglioni salgono")
    return brackets


def income_tax(income: Decimal, brackets: list[tuple[Decimal | None, Decimal]], surtax: Decimal) -> Decimal:
    """IRPEF on the brackets plus the surtaxes as a flat rate; the deductions from tax are left out."""
    tax, floor = Decimal(0), Decimal(0)
    for limit, rate in brackets:
        top = income if limit is None else min(income, limit)
        if top > floor:
            tax += (top - floor) * rate / 100
        if limit is None or income <= limit:
            break
        floor = limit
    return tax + max(income, Decimal(0)) * surtax / 100


def exit_rate(tax: dict[str, str], participation_years: int) -> Decimal:
    """The rate on the fund's benefit: lower by a step each year past the threshold, down to the floor."""
    extra = max(0, participation_years - int(parse_decimal(tax["exit_rate_free_years"])))
    lowered = parse_decimal(tax["exit_rate"]) - parse_decimal(tax["exit_rate_step"]) * extra
    return max(parse_decimal(tax["exit_rate_floor"]), lowered)


@dataclass(frozen=True)
class AllocationResult:
    """One allocation, a year of it repeated for ``years`` years at one return."""

    fund: Decimal            # own money into the fund, a year
    pac: Decimal             # money into the PAC, a year
    employer: Decimal        # the employer's contribution it earns
    employer_lost: bool      # own money below the contractual share: no employer contribution
    deductible: Decimal      # the part of ``fund`` under the cap
    cap_room: Decimal        # what is left under the cap; negative is over it
    tax_saving: Decimal      # a year, invested in the PAC beside ``pac``
    exit_rate: Decimal
    fund_net: Decimal        # at the horizon, after the exit tax
    pac_net: Decimal         # at the horizon, after the stamp duty and the tax on the gain
    fund_reachable: bool     # whether the goal can count on the fund before retirement
    reachable: Decimal       # what the goal can count on at its date

    @property
    def yearly(self) -> Decimal:
        return self.fund + self.pac


def compare(
    fund: Decimal,
    pac: Decimal,
    profile: dict[str, str],
    tax: dict[str, str],
    years: int,
    participation_years: int,
    return_rate: Decimal,
    fund_reachable: bool,
) -> AllocationResult:
    """What one allocation leads to: every step of the fund against the PAC.

    Contributions go in at the start of each year. The fund's returns are taxed
    every year; at the exit only the deducted part and the employer's are taxed
    again, because the rest was paid from taxed income. The PAC pays the stamp
    duty every year and the tax on the gain when sold, at the horizon. The tax
    saved by the deduction goes into the PAC the same year (shortcut: it really
    arrives with the next year's return; upgrade when the projections take months).
    """
    if fund < 0 or pac < 0:
        raise ValueError("una ripartizione non ha importi negativi")
    base = parse_decimal(profile["contribution_base"])
    contractual = base * parse_decimal(profile["own_rate"]) / 100
    employer_lost = fund < contractual
    employer = Decimal(0) if employer_lost else base * parse_decimal(profile["employer_rate"]) / 100
    cap = parse_decimal(tax["deduction_cap"])
    deductible = max(Decimal(0), min(fund, cap - employer))

    gross = parse_decimal(profile["gross_monthly"]) * parse_decimal(profile["months_paid"])
    taxable = gross * (1 - parse_decimal(tax["employee_social_rate"]) / 100)
    brackets = parse_brackets(tax["irpef_brackets"])
    surtax = parse_decimal(tax["regional_surtax"]) + parse_decimal(tax["municipal_surtax"])
    saving = income_tax(taxable, brackets, surtax) - income_tax(taxable - deductible, brackets, surtax)

    rate = return_rate / 100
    fund_growth = 1 + rate * (1 - parse_decimal(tax["fund_return_tax"]) / 100)
    stamp = parse_decimal(tax["stamp_duty"]) / 100
    fund_value = pac_value = pac_cost = Decimal(0)
    for _ in range(years):
        fund_value = (fund_value + fund + employer) * fund_growth
        pac_value = (pac_value + pac + saving) * (1 + rate) * (1 - stamp)
        pac_cost += pac + saving
    leaving = exit_rate(tax, participation_years)
    fund_net = fund_value - (deductible + employer) * years * leaving / 100
    gain = max(Decimal(0), pac_value - pac_cost)
    pac_net = pac_value - gain * parse_decimal(tax["etf_gain_tax"]) / 100

    def cents(value: Decimal) -> Decimal:
        return value.quantize(CENT)

    return AllocationResult(
        fund=cents(fund),
        pac=cents(pac),
        employer=cents(employer),
        employer_lost=employer_lost,
        deductible=cents(deductible),
        cap_room=cents(cap - employer - fund),
        tax_saving=cents(saving),
        exit_rate=leaving,
        fund_net=cents(fund_net),
        pac_net=cents(pac_net),
        fund_reachable=fund_reachable,
        reachable=cents(pac_net + (fund_net if fund_reachable else 0)),
    )


def complete_year(parameters: dict[int, dict], year: int) -> int | None:
    """The latest year up to ``year`` with every parameter written; a gap is never filled from another year."""
    usable = [y for y, values in parameters.items() if y <= year and set(TAX_KEYS) <= set(values)]
    return max(usable, default=None)
