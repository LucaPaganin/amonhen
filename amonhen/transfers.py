"""Pair the two legs of an internal transfer so it never counts as spending.

Candidates are equal-and-opposite amounts on two different real accounts at
most ``MAX_GAP_DAYS`` apart. What corroborates a pair is the IBAN each bank
printed on its own leg: the two legs must each name the *other* account, and a
leg naming any other account refuses the pair. When an account carries no IBAN
to compare against, the pair falls back to counting who named a counterparty at
all — all the evidence there is, and marked as such. Among ambiguous candidates
the pairing is the exact maximum-weight bipartite matching of desiderata 5.3,
not a greedy closest-date pick: the weight says how much evidence a pair
carries, so one locally best pair can never strand a better overall set. Every
link records its confidence and method and stays reviewable by hand.
"""
import datetime as dt
import re
import sqlite3
from collections.abc import Iterable
from decimal import Decimal
from typing import TYPE_CHECKING

from amonhen.ledger import Ledger

if TYPE_CHECKING:
    from amonhen.config import Passthrough
from amonhen.matching import max_weight_matching
from amonhen.models import format_decimal, parse_decimal

MAX_GAP_DAYS = 2
CORROBORATED = "high"
AMOUNT_ONLY = "medium"
# Evidence weights: a pair whose two legs each name the other's account outranks
# one where a single leg identifies its counterpart, which in turn outranks a
# bare amount-and-date coincidence; each extra day of distance costs 10. With a
# gap of at most MAX_GAP_DAYS every candidate stays positive.
BOTH_NAMED_WEIGHT = 100
ONE_SIDED_WEIGHT = 80
NEITHER_NAMED_WEIGHT = 50
DAY_PENALTY = 10
# An account identifier is evidence only when it is an IBAN. A bank that
# identifies an account some other way must not be read as naming a third
# account, or every pair against it would look contradicted.
IBAN_SHAPE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


def link_transfers(ledger: Ledger, since: dt.date | None = None) -> int:
    """Link the maximum-weight set of candidate pairs and return the count."""
    rows = _candidates(ledger.conn, since)
    pairs = _best_pairs(rows)
    for leg_a, leg_b in pairs:
        _, confidence, method = _score(leg_a, leg_b)
        ledger.link_transfer_pair(leg_a["id"], leg_b["id"], confidence, method)
    return len(pairs)


def pair_candidates(ledger: Ledger, transaction_id: int) -> list[sqlite3.Row]:
    """The legs a person could pair this one with, best evidence first.

    The same rules the matcher applies to the whole ledger — equal and opposite
    amounts, two different real accounts, a couple of days apart at most, neither
    leg spoken for — run against one leg chosen by hand, so a manual link can
    only make a pair the matcher itself would have accepted. A leg with no
    candidate left is a fact worth showing: it means the other half is missing.
    """
    chosen = ledger.conn.execute(
        """SELECT t.*, a.iban AS account_iban FROM transactions t
           JOIN accounts a ON a.id = t.account_id WHERE t.id = ?""",
        (transaction_id,),
    ).fetchone()
    if chosen is None:
        return []
    rows = ledger.conn.execute(
        """SELECT t.*, a.iban AS account_iban FROM transactions t
           JOIN accounts a ON a.id = t.account_id
           WHERE a.type = 'real' AND t.status = 'BOOK' AND t.amount = ?
             AND t.id <> ? AND t.account_id <> ?
             AND ABS(julianday(t.date) - julianday(?)) <= ?
             AND NOT EXISTS (
                 SELECT 1 FROM transfer_links l WHERE l.leg_a = t.id OR l.leg_b = t.id
             )
             AND NOT EXISTS (
                 SELECT 1 FROM postings p JOIN accounts v ON v.id = p.account_id
                 WHERE p.transaction_id = t.id AND v.type = 'virtual'
             )
           ORDER BY t.date, t.id""",
        (
            format_decimal(-parse_decimal(chosen["amount"])),
            chosen["id"],
            chosen["account_id"],
            chosen["date"],
            MAX_GAP_DAYS,
        ),
    ).fetchall()
    weighted = [(row, _score(chosen, row)[0]) for row in rows]
    return [row for row, weight in sorted(weighted, key=lambda pair: -pair[1]) if weight > 0]


def _score(leg_a: sqlite3.Row, leg_b: sqlite3.Row) -> tuple[int, str | None, str | None]:
    """Weight, confidence and method of a candidate pair. Weight 0 = not a pair.

    The two legs must sit on different accounts and be close enough in time.
    What corroborates them is the IBAN each bank printed on its own leg: a leg
    naming the *other* leg's account is evidence, and a leg naming some other
    account is a contradiction — the amount coincidence this matcher exists to
    refuse. Only when an account carries no IBAN to compare against does the
    pair fall back to counting who named a counterparty at all.
    """
    if leg_a["account_id"] == leg_b["account_id"]:
        return 0, None, None
    gap = _days_between(leg_a["date"], leg_b["date"])
    if gap > MAX_GAP_DAYS:
        return 0, None, None

    own_a, own_b = _canonical_iban(leg_a["account_iban"]), _canonical_iban(leg_b["account_iban"])
    key_a, key_b = (
        _canonical_iban(leg_a["counterparty_account"]),
        _canonical_iban(leg_b["counterparty_account"]),
    )
    names_a, names_b = bool(leg_a["counterparty_account"]), bool(leg_b["counterparty_account"])
    if (key_a is not None and own_b is not None and key_a != own_b) or (
        key_b is not None and own_a is not None and key_b != own_a
    ):
        # A named counterparty that is not the other leg's account: the money
        # went to a third party, so this is not the transfer it looks like.
        return 0, None, None

    corroborates_a = key_a is not None and key_a == own_b
    corroborates_b = key_b is not None and key_b == own_a
    if corroborates_a and corroborates_b:
        return BOTH_NAMED_WEIGHT - DAY_PENALTY * gap, CORROBORATED, "amount-date-counterparty"
    if corroborates_a or corroborates_b:
        return ONE_SIDED_WEIGHT - DAY_PENALTY * gap, AMOUNT_ONLY, "amount-date-counterparty-one-sided"
    if names_a != names_b:
        # Exactly one side names a counterparty, and it is not the other leg's
        # account — or there is no IBAN to check it against. An amount
        # coincidence, not a transfer: excluding a real expense is invisible,
        # keeping it wrong is not.
        return 0, None, None
    if names_a:
        return BOTH_NAMED_WEIGHT - DAY_PENALTY * gap, AMOUNT_ONLY, "amount-date-counterparty-unverified"
    return NEITHER_NAMED_WEIGHT - DAY_PENALTY * gap, AMOUNT_ONLY, "amount-date"


def _canonical_iban(value: str | None) -> str | None:
    """The value as a canonical IBAN, or None when it is not one."""
    if not value:
        return None
    cleaned = "".join(value.split()).upper()
    return cleaned if IBAN_SHAPE.match(cleaned) else None


def _candidates(conn: sqlite3.Connection, since: dt.date | None) -> list[sqlite3.Row]:
    query = """SELECT t.id, t.account_id, t.date, t.amount, t.counterparty_account,
                      a.iban AS account_iban
               FROM transactions t
               JOIN accounts a ON a.id = t.account_id
               WHERE t.status = 'BOOK' AND a.type = 'real' AND t.amount != '0.00'
                 AND NOT EXISTS (
                     SELECT 1 FROM transfer_links l
                     WHERE l.leg_a = t.id OR l.leg_b = t.id
                 )"""
    params: list[str] = []
    if since is not None:
        query += " AND t.date >= ?"
        params.append(since.isoformat())
    query += " ORDER BY t.date, t.id"
    return list(conn.execute(query, params))


def _best_pairs(rows: list[sqlite3.Row]) -> list[tuple[sqlite3.Row, sqlite3.Row]]:
    """Exact maximum-weight matching of the candidate graph, per amount group."""
    by_amount: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        key = format_decimal(abs(parse_decimal(row["amount"])))
        by_amount.setdefault(key, []).append(row)

    pairs: list[tuple[sqlite3.Row, sqlite3.Row]] = []
    for key in sorted(by_amount):
        group = by_amount[key]
        by_id = {row["id"]: row for row in group}
        outgoing = [row for row in group if parse_decimal(row["amount"]) < 0]
        incoming = [row for row in group if parse_decimal(row["amount"]) > 0]
        weights: dict[tuple[int, int], int] = {}
        for leg_a in outgoing:
            for leg_b in incoming:
                weight, _, _ = _score(leg_a, leg_b)
                if weight > 0:
                    weights[(leg_a["id"], leg_b["id"])] = weight
        for leg_a, leg_b in max_weight_matching(weights):
            pairs.append((by_id[leg_a], by_id[leg_b]))
    pairs.sort(key=lambda pair: (pair[0]["id"], pair[1]["id"]))
    return pairs


def _days_between(first: str, second: str) -> int:
    return abs(
        (dt.date.fromisoformat(second) - dt.date.fromisoformat(first)).days
    )


def link_passthrough_legs(ledger: Ledger, declarations: "Iterable[Passthrough]") -> int:
    """Money that is not yours to count is neither spending nor income.

    Two cases, one mechanism. A Revolut deposit account appears to Enable Banking
    only through a consent that covers it, so those legs have no counterpart in
    the ledger and the pairing can never see them: they were counted as spending,
    and on the live ledger they were the largest single line of the burn. And
    money that arrives because somebody else is paying their share, or because a
    bill came back, is not income — on the live ledger those credits were the
    whole of one month's income. A declared label puts the leg's other side on a
    virtual account named after the destination: out of the burn, out of income,
    out of the review queue, and still on the books, where its balance says how
    much has moved.

    A declaration marked ``incoming_only`` looks at money arriving alone. The
    label is a name, and a name matches both directions — "Assicurazioni" would take
    the premium out of the burn as happily as it takes the reimbursement out of
    income.
    """
    moved = 0
    for declaration in declarations:
        direction = "AND CAST(t.amount AS REAL) > 0" if declaration.incoming_only else ""
        for label in declaration.labels:
            needle = label.casefold()
            rows = ledger.conn.execute(
                f"""SELECT t.id, t.description, COALESCE(t.counterparty, '') AS counterparty
                   FROM transactions t
                   JOIN accounts a ON a.id = t.account_id
                   WHERE a.type = 'real' AND t.status = 'BOOK' {direction}
                     AND (t.description LIKE ? OR COALESCE(t.counterparty, '') LIKE ?)
                     AND NOT EXISTS (
                         SELECT 1 FROM postings p JOIN accounts v ON v.id = p.account_id
                         WHERE p.transaction_id = t.id AND v.type = 'virtual'
                     )
                     AND NOT EXISTS (
                         SELECT 1 FROM transfer_links l WHERE l.leg_a = t.id OR l.leg_b = t.id
                     )
                   ORDER BY t.date, t.id""",
                (f"%{label}%", f"%{label}%"),
            ).fetchall()
            for row in rows:
                # SQLite's LIKE is case-insensitive for ASCII only, so the label
                # is confirmed the way the rest of the code compares text.
                if (
                    needle not in row["description"].casefold()
                    and needle not in row["counterparty"].casefold()
                ):
                    continue
                ledger.move_to_virtual_account(row["id"], declaration.destination)
                moved += 1
            # A proposal to categorize this money is moot: the leg is declared
            # now, and nothing here would ever categorize it.
            for suggestion in ledger.suggestions("pending"):
                if needle in suggestion["merchant"].casefold():
                    ledger.decide_suggestion(suggestion["merchant"], "dismissed")
    return moved


def transfer_amount_total(ledger: Ledger) -> Decimal:
    """Sanity helper: the clearing account must always net to zero."""
    total = Decimal(0)
    for row in ledger.conn.execute(
        """SELECT p.amount FROM postings p
           JOIN accounts a ON a.id = p.account_id
           WHERE a.name = 'Transfer clearing'"""
    ):
        total += parse_decimal(row["amount"])
    return total
