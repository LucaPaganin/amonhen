"""What follows every write of movements, whatever path wrote them.

A sync pass, a period sync, the restart's `settle`, a file import from the app or
the command line, and a held movement a person decided to write all end with the
same steps in the same order. They used to be written out by each caller, and the
copies had drifted: the import paired before the transfer rules ran, so an equal
amount on another account took a transfer the person had named with a rule.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from amonhen.config import Passthrough
from amonhen.ledger import Ledger
from amonhen.merchants import RuleBook, apply_transfer_rules, categorize
from amonhen.transfers import link_passthrough_legs, link_transfers


@dataclass(frozen=True)
class Settled:
    """What the steps after a write changed, one count per step."""

    transfer_rules: int
    linked: int
    passthrough: int
    categorized: int


def settle_after_ingest(
    ledger: Ledger,
    passthrough: Sequence[Passthrough],
    *,
    since: dt.date | None = None,
) -> Settled:
    """Bring the ledger to what the rules and the pairing say, after a write.

    The order is the point (`docs/transfers.md`):

    1. the transfer rules, before the pairing: a leg the matcher paired is no
       rule's to move, so an equal amount on another account would otherwise
       take a transfer a person named;
    2. the pairing, from `since` on (everything when it is None);
    3. the declared passthrough labels, after the pairing, so a real pair
       between two tracked accounts wins over a label;
    4. the double-entry check, before anything is categorized on a broken ledger;
    5. the rules, last: on a leg the matcher paired, the pair wins.
    """
    transfer_rules = apply_transfer_rules(ledger, RuleBook(ledger.conn))
    linked = link_transfers(ledger, since=since)
    legs = link_passthrough_legs(ledger, passthrough)
    ledger.validate()
    categorized = categorize(ledger, RuleBook(ledger.conn))
    return Settled(transfer_rules, linked, legs, categorized)
