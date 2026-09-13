"""Desiderata 5.9: an assistant that reads the numbers the backend computed.

The model is never asked for a figure. It is handed the figures the dashboard,
the metrics and the budgets are already made of, and it talks about them. Three
rules are enforced here instead of promised in a prompt, because a prompt is not
a guarantee:

* **Every number in the prose was sent.** The reading is checked token by token
  against the numbers of the packet, and refused whole if it cites anything
  else — a figure the model produced itself is exactly what this rule exists to
  catch, and a refusal is recorded rather than shown.
* **A proposal names something the request contained.** A merchant and a
  category that were in the packet, or a category without a budget and a
  positive amount. Anything outside that vocabulary is dropped and logged.
* **Nothing is written to the ledger.** A category proposal waits in the same
  table the classifier's proposals wait in, a budget proposal in its own, and a
  person accepts either one.

What is never sent: IBANs, account numbers, raw payloads, and counterparty names
that are not already the normalized merchant (they are scrubbed before the
packet leaves this module).
"""
import calendar
import datetime as dt
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from amonhen.ledger import Ledger
from amonhen.llm import LlmConfig, LlmOff, chat_json
from amonhen.merchants import merchant_name
from amonhen.metrics import (
    LedgerScope,
    compute_metrics,
    latest_balances,
    monthly_flows,
    spend_by_category,
)
from amonhen.models import format_decimal, parse_decimal
from amonhen.settings import UNCATEGORIZED
from amonhen.suggestions import categories, unseen_merchants
from amonhen.transfers import IBAN_SHAPE

log = logging.getLogger("amonhen.assistant")

# Calls are counted per day. The spec asks for a ceiling, and a loop that asks
# the same thing forever is the one way this feature can spend money on its own.
CALL_LIMIT = 20
PACKET_MERCHANTS = 20
PACKET_MONTHS = 12

SYSTEM_PROMPT = (
    "Sei l'assistente di una app di finanza personale italiana. Ricevi, come "
    "oggetto json, i numeri che la app ha già calcolato: le metriche di spesa, "
    "le serie mensili di entrate e uscite, le spese per categoria, i budget, la "
    "coda dei movimenti senza categoria e i merchant che nessuna regola copre.\n"
    "Scrivi una lettura in italiano di quei numeri: cosa spinge la spesa, quale "
    "categoria sta scivolando, se un budget regge, da dove cominciare nella "
    "coda. Puoi anche proporre qualcosa, e una persona lo confermerà.\n"
    "Vincoli: cita soltanto cifre che sono nel json, con le stesse unità; non "
    "sommare, non stimare, non arrotondare e non calcolare percentuali; non "
    "inventare movimenti, conti o identificativi che non ti sono stati dati.\n"
    "Rispondi con un oggetto json di questa forma:\n"
    '{"lettura": "il testo in italiano", "proposte": ['
    '{"tipo": "categoria", "merchant": "un merchant del json", "categoria": "una categoria del json"}, '
    '{"tipo": "budget", "categoria": "una categoria del json", "importo": "50.00"}]}\n'
    "Le proposte sono facoltative. Usa solo merchant e categorie presenti nel "
    "json, e proponi un budget solo per una categoria che non ne ha già uno."
)

__all__ = [
    "AssistantReading",
    "ask",
    "budget_proposals",
    "data_packet",
    "decide_budget_proposal",
    "readings",
    "state",
    "unsupported_numbers",
]


@dataclass(frozen=True)
class AssistantReading:
    """One reading, with the model that wrote it and what it was based on."""

    question: str
    answer: str
    model: str
    fingerprint: str
    created_at: str
    cached: bool
    proposals: tuple[dict, ...] = ()


# -- the packet -------------------------------------------------------------
#
# Built from the functions the screens already read, so the prose and the charts
# cannot be about two different ledgers.

_WORD = re.compile(r"\S+")
_DIGITS = re.compile(r"\d+")
_DATE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")


def _figure(value: Decimal | None) -> str | None:
    return None if value is None else format_decimal(value)


def _scrub(value: object) -> object:
    """Take out what 5.9 says never leaves the machine.

    An IBAN is one token, so a token that is only an IBAN becomes a marker
    wherever it appears — including inside a description the bank wrote.
    """
    if isinstance(value, str):
        return _WORD.sub(lambda match: "[iban]" if IBAN_SHAPE.match(match.group(0)) else match.group(0), value)
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _period_start(today: dt.date, months: int) -> dt.date:
    year, month = divmod(today.year * 12 + today.month - 1 - (months - 1), 12)
    return dt.date(year, month + 1, 1)


def _queue_counts(ledger: Ledger) -> dict:
    """What waits for a decision, without the rows: the packet carries counts."""
    without_category = ledger.conn.execute(
        """SELECT COUNT(DISTINCT t.id) AS n
           FROM transactions t
           JOIN postings p ON p.transaction_id = t.id
           JOIN accounts a ON a.id = p.account_id
           WHERE a.name = ? AND t.status = 'BOOK' AND CAST(t.amount AS REAL) < 0""",
        (UNCATEGORIZED,),
    ).fetchone()["n"]
    proposed = ledger.conn.execute(
        "SELECT COUNT(*) AS n FROM merchant_suggestions WHERE decision = 'pending'"
    ).fetchone()["n"]
    return {"senza_categoria": without_category, "con_proposta": proposed}


def _context_figures(ledger: Ledger, context: dict | None, today: dt.date) -> dict:
    """The computed figures a contextual entry point hands over.

    A row of the ledger enters as numbers and a normalized merchant — never as
    the payload the bank sent, and never with its counterparty printed.
    """
    kind = str((context or {}).get("kind", "") or "cruscotto")
    identifier = (context or {}).get("id")
    if kind == "budget" and identifier is not None:
        for status in ledger.budget_status(*_month_of(today)):
            if status["id"] == identifier:
                return {
                    "tipo": "budget",
                    "categoria": status["category"],
                    "budget": status["budget"],
                    "speso": status["spent"],
                    "rimasto": status["remaining"],
                }
        return {"tipo": "budget", "categoria": None}
    if kind == "movimento" and identifier is not None:
        row = ledger.conn.execute(
            "SELECT date, amount, description FROM transactions WHERE id = ?", (identifier,)
        ).fetchone()
        if row is None:
            return {"tipo": "movimento", "trovato": False}
        return {
            "tipo": "movimento",
            "data": row["date"],
            "importo": row["amount"],
            "merchant": merchant_name(row["description"]),
            "categoria": ledger.category_of(identifier),
        }
    return {"tipo": "cruscotto"}


def _month_of(day: dt.date) -> tuple[dt.date, dt.date]:
    """The first and last day of the month a day falls in."""
    last = calendar.monthrange(day.year, day.month)[1]
    return dt.date(day.year, day.month, 1), dt.date(day.year, day.month, last)


def data_packet(
    ledger: Ledger,
    today: dt.date,
    *,
    scope: LedgerScope = LedgerScope(),
    context: dict | None = None,
    months: int = PACKET_MONTHS,
) -> dict:
    """Everything the model may talk about, and nothing else."""
    start = _period_start(today, months)
    metrics = compute_metrics(ledger, today, scope=scope)
    packet = {
        "oggi": today.isoformat(),
        "periodo": {"dal": start.isoformat(), "al": today.isoformat()},
        "metriche": {
            "mesi_di_storico": metrics.months_of_history,
            "parziale": metrics.partial,
            "burn_ricorrente": _figure(metrics.recurring_burn),
            "accantonamento_episodico": _figure(metrics.episodic_accrual),
            "burn_atteso": _figure(metrics.expected_burn),
            "runway_mesi": _figure(metrics.runway_months),
            "liquidita": _figure(metrics.liquidity),
            "quota_incomprimibile": _figure(metrics.essential_monthly),
            "quota_discrezionale": _figure(metrics.discretionary_monthly),
            "flusso_di_risparmio": _figure(metrics.savings_flow),
        },
        "flussi_mensili": [
            {
                "mese": flow.month,
                "entrate": _figure(flow.income),
                "uscite": _figure(flow.expenses),
                "parziale": flow.partial,
            }
            for flow in monthly_flows(ledger, start, today, scope)
        ],
        "spese_per_categoria": [
            {"categoria": item.category, "importo": _figure(item.amount)}
            for item in spend_by_category(ledger, start, today, scope)
        ],
        "budget": ledger.budget_status(*_month_of(today)),
        "saldi": [
            {"conto": balance.account, "saldo": _figure(balance.balance)}
            for balance in latest_balances(ledger, scope)
        ],
        "coda": _queue_counts(ledger),
        "merchant_senza_categoria": unseen_merchants(ledger, PACKET_MERCHANTS),
        "categorie": categories(ledger),
        "contesto": _context_figures(ledger, context, today),
    }
    return _scrub(packet)


def _fingerprint(packet: dict) -> str:
    """The data a reading is about, hashed.

    The merchants still to propose and the count of proposals already waiting are
    left out: those change because the assistant answered, not because the ledger
    did. Hashing them would make the same question about the same figures reach
    the model a second time, which is the cost the spec asks not to pay.
    """
    figures = {key: value for key, value in packet.items() if key != "merchant_senza_categoria"}
    figures["coda"] = {
        key: value for key, value in packet["coda"].items() if key != "con_proposta"
    }
    canonical = json.dumps(figures, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# -- the numbers rule -------------------------------------------------------


def allowed_numbers(packet: dict) -> set[str]:
    """Every figure the packet contains, in either spelling.

    Two forms per token: its digits with the separators removed ("1.234,56" and
    "1234.56" become the same string) and its plain digit runs, so a year or a
    month inside an ISO date is a number the model may repeat.
    """
    text = json.dumps(packet, ensure_ascii=False)
    allowed = set(_DIGITS.findall(text))
    for token in _WORD.findall(text):
        digits = re.sub(r"\D", "", token)
        if digits:
            allowed.add(digits)
    return allowed


def unsupported_numbers(text: str, allowed: set[str]) -> list[str]:
    """The figures in the prose that no computed figure accounts for.

    Italian dates are folded to the ISO the packet uses first, because a day
    written 30/06/2026 is the same day as 2026-06-30 and not a made-up number.
    """
    folded = _DATE.sub(
        lambda match: f"{match.group(3)}-{match.group(2).zfill(2)}-{match.group(1).zfill(2)}", text
    )
    missing = []
    for token in _WORD.findall(folded):
        digits = re.sub(r"\D", "", token)
        if digits and digits not in allowed:
            missing.append(token)
    return missing


# -- proposing and deciding -------------------------------------------------

PROPOSAL_KINDS = ("budget", "categoria")


def _budget_proposal_is_new(ledger: Ledger, category: str) -> bool:
    row = ledger.conn.execute(
        """SELECT b.amount AS amount FROM accounts a
           LEFT JOIN budgets b ON b.category_id = a.id
           WHERE a.type = 'category' AND a.name = ?""",
        (category,),
    ).fetchone()
    return row is not None and not row["amount"]


def _record_proposals(ledger: Ledger, raw: object, packet: dict) -> tuple[list[dict], list[str]]:
    """Keep the proposals the request supports; drop the rest with a log line."""
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], ["le proposte non sono una lista"]
    merchants = set(packet["merchant_senza_categoria"])
    available = set(packet["categorie"])
    accepted: list[dict] = []
    rejected: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            rejected.append(f"proposta non leggibile: {entry!r}")
            continue
        kind = str(entry.get("tipo", "categoria"))
        if kind not in PROPOSAL_KINDS:
            rejected.append(f"tipo di proposta sconosciuto: {kind!r}")
            continue
        category = str(entry.get("categoria", ""))
        if category not in available:
            rejected.append(f"categoria non nota: {category!r}")
            continue
        if kind == "categoria":
            merchant = str(entry.get("merchant", ""))
            if merchant not in merchants:
                rejected.append(f"merchant non nella domanda: {merchant!r}")
                continue
            ledger.record_suggestion(merchant, category, "llm")
            accepted.append({"kind": "categoria", "merchant": merchant, "category": category})
            continue
        if not _budget_proposal_is_new(ledger, category):
            rejected.append(f"budget già presente per {category!r}")
            continue
        try:
            amount = parse_decimal(str(entry.get("importo", "")))
        except (InvalidOperation, ValueError):
            rejected.append(f"importo non leggibile per {category!r}")
            continue
        if amount <= 0:
            rejected.append(f"importo non positivo per {category!r}")
            continue
        ledger.record_budget_proposal(category, format_decimal(amount), "llm")
        accepted.append({"kind": "budget", "category": category, "amount": format_decimal(amount)})
    return accepted, rejected


def _record(
    ledger: Ledger,
    question: str,
    answer: str,
    model: str,
    fingerprint: str,
    refused: str | None = None,
) -> None:
    ledger.record_reading(question, answer, model, fingerprint, refused)


def _charge_call(ledger: Ledger, today: dt.date) -> int:
    """Count this call, refusing it when the day's ceiling is already spent."""
    key = f"assistant_calls:{today.isoformat()}"
    used = int(ledger.setting(key, "0") or 0)
    if used >= CALL_LIMIT:
        raise RuntimeError(
            f"the assistant has already answered {CALL_LIMIT} times today: ask again tomorrow"
        )
    ledger.set_setting(key, str(used + 1))
    return used + 1


# -- the reading ------------------------------------------------------------


def ask(
    ledger: Ledger,
    llm: LlmConfig,
    question: str = "",
    *,
    context: dict | None = None,
    today: dt.date | None = None,
    scope: LedgerScope = LedgerScope(),
) -> AssistantReading:
    """Answer a question about this ledger, or hand back the same answer again.

    The question and the fingerprint of the data are the key: asking the same
    thing about the same numbers does not reach the model twice.
    """
    if not llm.configured:
        raise LlmOff(
            "no LLM configured: set AMONHEN_LLM_URL and AMONHEN_LLM_MODEL to enable the assistant"
        )
    day = today or dt.date.today()
    packet = data_packet(ledger, day, scope=scope, context=context)
    fingerprint = _fingerprint(packet)
    asked = (question or "").strip()

    stored = ledger.reading(asked, fingerprint)
    if stored is not None:
        return AssistantReading(
            question=asked,
            answer=stored["answer"],
            model=stored["model"],
            fingerprint=fingerprint,
            created_at=stored["created_at"],
            cached=True,
        )

    _charge_call(ledger, day)
    reply = chat_json(llm, SYSTEM_PROMPT, {"domanda": asked, "dati": packet})

    text = reply.get("lettura")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("il modello non ha scritto nessuna lettura")
    invented = unsupported_numbers(text, allowed_numbers(packet))
    if invented:
        reason = "cifre non calcolate: " + ", ".join(dict.fromkeys(invented))
        _record(ledger, asked, "", llm.model, fingerprint, refused=reason)
        log.warning("refused a reading that cited %s", reason)
        raise ValueError(f"citava {reason}")

    accepted, rejected = _record_proposals(ledger, reply.get("proposte"), packet)
    for line in rejected:
        log.warning("dropped a proposal: %s", line)
    _record(ledger, asked, text.strip(), llm.model, fingerprint)
    return AssistantReading(
        question=asked,
        answer=text.strip(),
        model=llm.model,
        fingerprint=fingerprint,
        created_at=dt.datetime.now().replace(microsecond=0).isoformat(sep=" "),
        cached=False,
        proposals=tuple(accepted),
    )


def state(ledger: Ledger, llm: LlmConfig, today: dt.date | None = None) -> dict:
    """What the section needs before it is asked anything."""
    day = today or dt.date.today()
    return {
        "configured": llm.configured,
        "model": llm.model or None,
        "calls_today": int(ledger.setting(f"assistant_calls:{day.isoformat()}", "0") or 0),
        "call_limit": CALL_LIMIT,
        "budget_proposals": ledger.budget_proposals("pending"),
    }


def budget_proposals(ledger: Ledger) -> list[dict]:
    return ledger.budget_proposals("pending")


def readings(ledger: Ledger, limit: int = 10) -> list[dict]:
    """The readings kept, newest first: what was asked, what came back, on what."""
    return ledger.readings(limit)


def decide_budget_proposal(ledger: Ledger, category: str, decision: str) -> dict:
    """Apply or drop a budget the assistant proposed. Nothing else changes."""
    if decision not in ("accept", "dismiss"):
        raise ValueError(f"unknown decision {decision!r}")
    if decision == "accept":
        proposal = ledger.budget_proposal(category)
        if proposal is None or proposal["decision"] != "pending":
            raise KeyError(f"no budget proposal for {category!r}")
        row = ledger.find_account(name=category)
        if row is None or row["type"] != "category":
            raise KeyError(f"{category!r} is not a category")
        ledger.set_budget(row["id"], parse_decimal(proposal["amount"]))
    ledger.decide_budget_proposal(category, "accepted" if decision == "accept" else "dismissed")
    return {"category": category, "decision": decision}
