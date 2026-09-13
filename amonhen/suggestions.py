"""Optional LLM proposals for merchants nobody has seen before.

Desiderata 5.5 step 4 and section 8: the model is only ever asked for a
discrete label for a merchant no rule covers, never for a number, never in the
synchronous sync path, and its answer lands in `merchant_suggestions` as a
proposal a human accepts or dismisses. Nothing here writes a category.
"""
import logging

from amonhen.ledger import Ledger
from amonhen.llm import LlmConfig, LlmOff, chat_json
from amonhen.merchants import RuleBook, matching_rule, merchant_name
from amonhen.settings import UNCATEGORIZED

log = logging.getLogger("amonhen.suggestions")

# Requests are made with temperature 0 and a JSON response format. The endpoint
# is any OpenAI-compatible chat completion gateway; ../../README documents the
# AMONHEN_LLM_* variables.
# DeepSeek and OpenAI both refuse `response_format: json_object` unless the word
# "json" appears in the prompt, and both answer better with the shape spelled
# out. The vocabulary stays closed either way: the answer is checked against the
# merchants that were asked about and the categories that exist.
SYSTEM_PROMPT = (
    "Classifichi movimenti bancari italiani. Ricevi un elenco di merchant e un "
    "elenco chiuso di categorie. Rispondi soltanto con un oggetto json che mappa "
    "ogni merchant a una categoria dell'elenco, nella forma "
    '{"nome merchant": "nome categoria"}, usando la stringa vuota quando non sei '
    "sicuro. Non inventare categorie."
)


def categories(ledger: Ledger) -> list[str]:
    return [
        row["name"]
        for row in ledger.conn.execute(
            "SELECT name FROM accounts WHERE type = 'category' AND name != ? ORDER BY name",
            (UNCATEGORIZED,),
        )
    ]


def unseen_merchants(ledger: Ledger, limit: int = 20) -> list[str]:
    """Settled uncategorized outflows whose merchant no rule or proposal covers."""
    rows = ledger.conn.execute(
        """SELECT t.description FROM transactions t
           WHERE t.status = 'BOOK' AND CAST(t.amount AS REAL) < 0
             AND EXISTS (
                 SELECT 1 FROM postings p JOIN accounts a ON a.id = p.account_id
                 WHERE p.transaction_id = t.id AND a.type = 'category' AND a.name = ?
             )
             AND NOT EXISTS (
                 SELECT 1 FROM postings p JOIN accounts a ON a.id = p.account_id
                 WHERE p.transaction_id = t.id AND a.type = 'virtual'
             )""",
        (UNCATEGORIZED,),
    ).fetchall()

    merchants: list[str] = []
    rules = RuleBook(ledger.conn).rules()
    for row in rows:
        merchant = merchant_name(row["description"])
        if not merchant or merchant in merchants:
            continue
        # A rule decides on the description, and the merchant name is a piece of
        # it: a rule that holds this name would have categorized the movement.
        if matching_rule(merchant, rules) is not None:
            continue
        pending = ledger.conn.execute(
            "SELECT 1 FROM merchant_suggestions WHERE merchant = ? AND decision = 'pending'",
            (merchant,),
        ).fetchone()
        if pending is not None:
            continue
        merchants.append(merchant)
        if len(merchants) >= limit:
            break
    return merchants


def propose_for_unseen(ledger: Ledger, config: LlmConfig, *, limit: int = 20) -> int:
    """Ask the model about unseen merchants and record its answers as proposals."""
    if not config.configured:
        raise LlmOff(
            "no LLM configured: set AMONHEN_LLM_URL and AMONHEN_LLM_MODEL to enable "
            "proposals for unseen merchants"
        )
    merchants = unseen_merchants(ledger, limit)
    available = categories(ledger)
    if not merchants or not available:
        return 0

    answers = _ask_model(config, merchants, available)
    recorded = 0
    for merchant, category in answers.items():
        if merchant not in merchants or category not in available:
            log.warning("ignoring proposal for %r -> %r", merchant, category)
            continue
        ledger.record_suggestion(merchant, category, "llm")
        recorded += 1
    return recorded


def _ask_model(config: LlmConfig, merchants: list[str], available: list[str]) -> dict[str, str]:
    parsed = chat_json(config, SYSTEM_PROMPT, {"categorie": available, "merchant": merchants})
    proposals = parsed.get("proposte", parsed)
    if not isinstance(proposals, dict):
        raise ValueError("the model did not return a merchant -> category object")
    return {
        str(merchant): str(category)
        for merchant, category in proposals.items()
        if isinstance(category, str)
    }
