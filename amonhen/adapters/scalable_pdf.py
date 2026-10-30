"""Read Scalable Capital's monthly statements, which only exist as PDFs.

Scalable has no API and no CSV of its cash account: what it gives is two kinds of
document. The *estratto conto* of a cash account (*conto di regolamento*) lists
every booking of a month with the balance at both ends; the *estratto conto
titoli* says what the securities were worth on a quarter's last day. Together
they say what the broker held on that day, which is the one figure a hand-added
investment account cannot get from its own movements: the bank transfers in and
out are already in the ledger as the other half of a Fineco or Revolut movement,
and what the market did is in none of them.

So this module reads both, and answers two things: the valuations (cash of every
cash account plus the securities, on each date a securities statement covers),
and the money that crossed the broker's boundary — transfers, withdrawals, direct
debits — so the caller can check that each one is in the ledger. Trades, fees,
interest and dividends stay inside the broker: they move value between cash and
securities, or are the return the valuation captures.
"""
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal

from pypdf import PdfReader

_BOOKING = re.compile(r"^(\d\d\.\d\d\.\d{4}) (\d\d\.\d\d\.\d{4}) (.*?)\s*(?:([+-][\d,]+\.\d\d) EUR)?\s*$")
_AMOUNT = re.compile(r"^(.*?)\s*([+-][\d,]+\.\d\d) EUR\s*$")
_ACCOUNT = re.compile(r"Conto di regolamento (DE\d+)")
_PERIOD = re.compile(r"Periodo (\d\d\.\d\d\.\d{4}) - (\d\d\.\d\d\.\d{4})")
_BALANCE = re.compile(r"Saldo a \S+ ([\d,.-]+) EUR")
_HOLDINGS = re.compile(r"Estratto conto titoli al (\d\d\.\d\d\.\d{4})")
_HOLDINGS_TOTAL = re.compile(r"T\s?otale ([\d,.]+) EUR")
_FOOTER = ("Scalable", "Pagina", "Registrazione", "Luca", "Data ")

# What crosses the broker's boundary: the other half of each is a movement on an
# account the ledger tracks, or should be.
FLOW_PREFIXES = ("Bonifico", "Prelievo dal saldo di cassa", "Addebito diretto", "Nuovo deposito")


@dataclass(frozen=True)
class Booking:
    account: str
    booked: str
    value_date: str
    description: str
    detail: str
    amount: Decimal | None

    @property
    def crosses_boundary(self) -> bool:
        return self.description.startswith(FLOW_PREFIXES)


@dataclass(frozen=True)
class CashStatement:
    account: str
    start: str
    end: str
    opening: Decimal
    closing: Decimal
    bookings: tuple[Booking, ...]
    corrected: bool = False


@dataclass(frozen=True)
class HoldingsStatement:
    date: str
    value: Decimal


@dataclass
class Valuation:
    date: str
    securities: Decimal
    cash: dict[str, Decimal] = field(default_factory=dict)

    @property
    def value(self) -> Decimal:
        return self.securities + sum(self.cash.values(), Decimal(0))


@dataclass
class Reading:
    cash: list[CashStatement]
    holdings: list[HoldingsStatement]
    unreadable: list[str]


def read_statements(files: list[tuple[str, bytes]]) -> Reading:
    """Every statement among the files, each kept once; what is not one is named."""
    cash: dict[tuple[str, str], CashStatement] = {}
    holdings: dict[str, HoldingsStatement] = {}
    unreadable: list[str] = []
    for name, content in files:
        try:
            text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
        except Exception:  # noqa: BLE001 - a file that is not a PDF is reported, not raised
            unreadable.append(name)
            continue
        statement = parse_text(text, corrected="Correzione" in name)
        if isinstance(statement, CashStatement):
            key = (statement.account, statement.start)
            # The same month downloaded twice is one statement; a correction wins.
            if key not in cash or statement.corrected:
                cash[key] = statement
        elif isinstance(statement, HoldingsStatement):
            holdings[statement.date] = statement
        else:
            unreadable.append(name)
    return Reading(
        cash=sorted(cash.values(), key=lambda s: (s.start, s.account)),
        holdings=sorted(holdings.values(), key=lambda s: s.date),
        unreadable=unreadable,
    )


def parse_text(text: str, *, corrected: bool = False) -> CashStatement | HoldingsStatement | None:
    """One statement's text, as the PDF library extracts it."""
    held = _HOLDINGS.search(text)
    if held:
        total = _HOLDINGS_TOTAL.search(text)
        return HoldingsStatement(_iso(held[1]), _number(total[1])) if total else None
    account = _ACCOUNT.search(text)
    period = _PERIOD.search(text)
    balances = _BALANCE.findall(text)
    if not (account and period and len(balances) >= 2):
        return None
    suffix = account[1][-4:]
    bookings: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        match = _BOOKING.match(line)
        if match:
            current = {"booked": _iso(match[1]), "value": _iso(match[2]), "description": match[3].strip(),
                       "detail": "", "amount": match[4]}
            bookings.append(current)
            continue
        if current is None or current["amount"] is not None:
            continue
        # The amount of a trade sits on the line after the instrument's name.
        amount = _AMOUNT.match(line)
        if amount:
            current["detail"] = f"{current['detail']} {amount[1]}".strip()
            current["amount"] = amount[2]
        elif line and not line.startswith(_FOOTER):
            current["detail"] = f"{current['detail']} {line}".strip()
    return CashStatement(
        account=suffix,
        start=_iso(period[1]),
        end=_iso(period[2]),
        opening=_number(balances[0]),
        closing=_number(balances[1]),
        bookings=tuple(
            Booking(suffix, b["booked"], b["value"], b["description"], b["detail"],
                    _number(b["amount"]) if b["amount"] else None)
            for b in bookings
        ),
        corrected=corrected,
    )


def valuations(reading: Reading) -> tuple[list[Valuation], list[str]]:
    """What the broker held on each date a securities statement covers.

    The cash of an account on that day is the closing balance of its statement
    for the month ending then; an account whose first statement starts later did
    not exist yet and holds nothing. A month that is missing for an account that
    did exist makes that date unknowable, and the date is reported instead of
    being valued short — and with no cash statement at all, every date is: the
    securities alone are not what the broker holds, and valuing them as if they
    were books the whole cash balance as a loss.
    """
    if not reading.cash:
        return [], [
            f"{held.date}: nessun estratto conto di liquidità tra i file, solo i titoli"
            for held in reading.holdings
        ]
    first_month = {}
    for statement in reading.cash:
        first_month.setdefault(statement.account, statement.start)
    found, missing = [], []
    for held in reading.holdings:
        valuation = Valuation(held.date, held.value)
        for account, start in first_month.items():
            if start > held.date:
                continue
            closing = next((s for s in reading.cash if s.account == account and s.end == held.date), None)
            if closing is None:
                missing.append(f"{held.date}: manca l'estratto del conto …{account} che finisce quel giorno")
                break
            valuation.cash[account] = closing.closing
        else:
            found.append(valuation)
    return found, missing


def boundary_flows(reading: Reading) -> list[Booking]:
    """The bookings whose other half is outside the broker, by value date."""
    return sorted(
        (b for s in reading.cash for b in s.bookings if b.crosses_boundary and b.amount is not None),
        key=lambda b: (b.value_date, b.account),
    )


def _iso(day: str) -> str:
    return f"{day[6:]}-{day[3:5]}-{day[:2]}"


def _number(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))
