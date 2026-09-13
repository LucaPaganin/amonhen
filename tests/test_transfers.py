"""Internal transfers: pairing, the clearing account, and managing one by hand."""
import datetime as dt
from decimal import Decimal

import pytest

from amonhen.models import Account, IncomingTransaction
from amonhen.config import Passthrough
from amonhen.transfers import (
    link_passthrough_legs,
    link_transfers,
    pair_candidates,
    transfer_amount_total,
)


def make_txn(ledger, account_id, date, amount, description, balancing=None, counterparty_account=None):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(date),
        amount=Decimal(amount),
        description=description,
        status="BOOK",
        source="psd2",
        balancing_account_id=balancing or ledger.uncategorized(),
        counterparty_account=counterparty_account,
        raw={},
    )


# IBAN-shaped identifiers, so the matcher compares the accounts instead of
# falling back to "did the bank print a counterparty account at all".
REVOLUT_IBAN = "IT40S0542811101000000123457"
FINECO_IBAN = "IT60X0542811101000000123456"
THIRD_PARTY_IBAN = "IT14J0366901600435270529695"


def setup_accounts(ledger, ibans=False):
    revolut = ledger.ensure_account(
        Account(name="Revolut", type="real", iban=REVOLUT_IBAN if ibans else None)
    )
    fineco = ledger.ensure_account(
        Account(name="Fineco", type="real", iban=FINECO_IBAN if ibans else None)
    )
    return revolut, fineco


def test_opposite_legs_on_different_accounts_are_linked(ledger):
    revolut, fineco = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Bonifico"))
    ledger.record(make_txn(ledger, fineco, "2026-02-16", "840.00", "Bonifico ricevuto"))

    linked = link_transfers(ledger)

    assert linked == 1
    number_of_links = ledger.conn.execute("SELECT COUNT(*) AS c FROM transfer_links").fetchone()["c"]
    assert number_of_links == 1
    assert transfer_amount_total(ledger) == Decimal("0.00")
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("0.00")
    ledger.validate()


def test_legs_on_the_same_account_are_not_linked(ledger):
    revolut, _ = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Out"))
    ledger.record(make_txn(ledger, revolut, "2026-02-16", "840.00", "In"))

    assert link_transfers(ledger) == 0


def test_legs_further_than_two_days_apart_are_not_linked(ledger):
    revolut, fineco = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Out"))
    ledger.record(make_txn(ledger, fineco, "2026-02-18", "840.00", "In"))

    assert link_transfers(ledger) == 0


def test_ambiguous_candidates_link_only_one_leg_each(ledger):
    revolut, fineco = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Out"))
    ledger.record(make_txn(ledger, fineco, "2026-02-15", "840.00", "In A"))
    ledger.record(make_txn(ledger, fineco, "2026-02-16", "840.00", "In B"))

    linked = link_transfers(ledger)

    assert linked == 1
    assert transfer_amount_total(ledger) == Decimal("0.00")


def test_pending_legs_are_not_linked(ledger):
    revolut, fineco = setup_accounts(ledger)
    pending = make_txn(ledger, revolut, "2026-02-15", "-840.00", "Out")
    ledger.record(IncomingTransaction(**{**pending.__dict__, "status": "PDNG"}))
    ledger.record(make_txn(ledger, fineco, "2026-02-15", "840.00", "In"))

    assert link_transfers(ledger) == 0


def test_already_linked_legs_are_not_linked_twice(ledger):
    revolut, fineco = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Out"))
    ledger.record(make_txn(ledger, fineco, "2026-02-15", "840.00", "In"))
    link_transfers(ledger)

    assert link_transfers(ledger) == 0
    assert transfer_amount_total(ledger) == Decimal("0.00")
    ledger.validate()


def test_exactly_one_side_naming_the_counterparty_is_an_amount_coincidence(ledger):
    """A supplier payment that happens to match an incoming amount is not a transfer."""
    revolut, fineco = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-06-30", "-183.00", "To a supplier",
                           counterparty_account="IT96Z0538710610000047333158"))
    ledger.record(make_txn(ledger, fineco, "2026-06-30", "183.00", "From deposit"))

    assert link_transfers(ledger) == 0
    assert ledger.spend_between(dt.date(2026, 6, 1), dt.date(2026, 6, 30)) == Decimal("183.00")


def test_legs_naming_each_other_account_link_as_corroborated(ledger):
    """Each bank printed the other account on its own leg: the strongest evidence."""
    revolut, fineco = setup_accounts(ledger, ibans=True)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Out",
                           counterparty_account=FINECO_IBAN))
    ledger.record(make_txn(ledger, fineco, "2026-02-15", "840.00", "In",
                           counterparty_account=REVOLUT_IBAN))

    link_transfers(ledger)

    row = ledger.conn.execute("SELECT confidence, method FROM transfer_links").fetchone()
    assert row["confidence"] == "high"
    assert row["method"] == "amount-date-counterparty"


def test_a_leg_naming_some_other_account_refuses_the_pair(ledger):
    """A contradiction outranks a corroboration.

    The incoming leg names the outgoing account, but the outgoing one went to a
    supplier: the money is not the same money, and a real expense must not
    disappear into a transfer because the amounts happen to match.
    """
    revolut, fineco = setup_accounts(ledger, ibans=True)
    ledger.record(make_txn(ledger, revolut, "2026-06-30", "-183.00", "To a supplier",
                           counterparty_account=THIRD_PARTY_IBAN))
    ledger.record(make_txn(ledger, fineco, "2026-06-30", "183.00", "From deposit",
                           counterparty_account=REVOLUT_IBAN))

    assert link_transfers(ledger) == 0
    assert ledger.spend_between(dt.date(2026, 6, 1), dt.date(2026, 6, 30)) == Decimal("183.00")


def test_the_credit_the_bank_attributed_to_the_debit_wins(ledger):
    """Two credits of the same amount, and only one of them is the pair.

    A transfer out and an unrelated credit from a third party, same amount, same
    day: this is the shape a live ledger got wrong. Naming each other's account
    decides it; counting who named a counterparty at all could not.
    """
    revolut, fineco = setup_accounts(ledger, ibans=True)
    out = ledger.record(make_txn(ledger, revolut, "2026-08-17", "-350.00", "Bonifico",
                                 counterparty_account=FINECO_IBAN))[0]
    from_third_party = ledger.record(make_txn(ledger, fineco, "2026-08-17", "350.00",
                                              "Da terzi",
                                              counterparty_account=THIRD_PARTY_IBAN))[0]
    from_us = ledger.record(make_txn(ledger, fineco, "2026-08-17", "350.00", "Dal conto",
                                     counterparty_account=REVOLUT_IBAN))[0]

    assert link_transfers(ledger) == 1

    linked = ledger.conn.execute("SELECT leg_a, leg_b FROM transfer_links").fetchall()
    assert {(row["leg_a"], row["leg_b"]) for row in linked} == {(out, from_us)}
    assert ledger.category_of(from_third_party) == "Uncategorized"
    assert transfer_amount_total(ledger) == Decimal("0.00")
    ledger.validate()


def test_one_leg_identifying_the_other_account_is_enough(ledger):
    """A bank that prints no counterparty on its own leg must not hide the transfer."""
    revolut, fineco = setup_accounts(ledger, ibans=True)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Bonifico",
                           counterparty_account=FINECO_IBAN))
    ledger.record(make_txn(ledger, fineco, "2026-02-15", "840.00", "Bonifico ricevuto"))

    assert link_transfers(ledger) == 1

    row = ledger.conn.execute("SELECT confidence, method FROM transfer_links").fetchone()
    assert row["confidence"] == "medium"
    assert row["method"] == "amount-date-counterparty-one-sided"
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("0.00")
    ledger.validate()


def test_named_counterparties_without_an_iban_to_check_link_as_unverified(ledger):
    """Both banks named an account and neither account's own IBAN is known.

    All the evidence there is, so the pair links, but it does not claim the
    corroboration it cannot have.
    """
    revolut, fineco = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Out",
                           counterparty_account="IT00X1"))
    ledger.record(make_txn(ledger, fineco, "2026-02-15", "840.00", "In",
                           counterparty_account="IT11Y"))

    link_transfers(ledger)

    row = ledger.conn.execute("SELECT confidence, method FROM transfer_links").fetchone()
    assert row["confidence"] == "medium"
    assert row["method"] == "amount-date-counterparty-unverified"


def test_legs_without_counterparty_evidence_link_at_medium_confidence(ledger):
    revolut, fineco = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Out"))
    ledger.record(make_txn(ledger, fineco, "2026-02-15", "840.00", "In"))

    link_transfers(ledger)

    row = ledger.conn.execute("SELECT confidence, method FROM transfer_links").fetchone()
    assert row["confidence"] == "medium"
    assert row["method"] == "amount-date"


def test_three_way_ambiguity_resolves_to_the_maximum_total_weight(ledger):
    """A closest-date greedy pick strands a leg; the exact match does not.

    Candidates: D1-C1 (1 day, weight 40), D1-C2 (2 days, weight 30) and D2-C1
    (0 days, weight 50). Greedy takes D1-C1 and leaves D2 unpaired for a total
    of 40; the maximum-weight matching is D1-C2 + D2-C1 for 80.
    """
    revolut, fineco = setup_accounts(ledger)
    d1, _ = ledger.record(make_txn(ledger, revolut, "2026-02-09", "-840.00", "Out A"))
    d2, _ = ledger.record(make_txn(ledger, revolut, "2026-02-10", "-840.00", "Out B"))
    c2, _ = ledger.record(make_txn(ledger, fineco, "2026-02-07", "840.00", "In far"))
    c1, _ = ledger.record(make_txn(ledger, fineco, "2026-02-10", "840.00", "In near"))
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-25.00", "Coffee"))

    assert link_transfers(ledger) == 2

    linked = ledger.conn.execute("SELECT leg_a, leg_b FROM transfer_links").fetchall()
    assert {(row["leg_a"], row["leg_b"]) for row in linked} == {(d1, c2), (d2, c1)}
    # The two linked legs leave the spend side; only the unlinked coffee stays.
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("25.00")
    assert transfer_amount_total(ledger) == Decimal("0.00")
    ledger.validate()


def test_linking_is_atomic(ledger):
    """A failure after the link row must not leave a half-cleared pair."""
    revolut, fineco = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Out"))
    ledger.record(make_txn(ledger, fineco, "2026-02-15", "840.00", "In"))
    outgoing = ledger.conn.execute("SELECT id FROM transactions WHERE amount = '-840.00'").fetchone()["id"]

    with pytest.raises(KeyError):
        ledger.link_transfer_pair(outgoing, 999999, "high", "amount-date")

    assert ledger.conn.execute("SELECT COUNT(*) AS c FROM transfer_links").fetchone()["c"] == 0
    assert ledger.is_transfer(outgoing) is False
    assert ledger.category_of(outgoing) == "Uncategorized"
    ledger.validate()


# -- money that is not the holder's to count --------------------------------
#
# The bank prints a name on this money — an own account Enable Banking does not
# expose ("Conto deposito senza vincoli"), a co-holder paying their share, or a
# firm giving a bill back. A declared label keeps it out of the spend and out of
# income without pretending to know a balance.

DEPOSIT = "Conto deposito senza vincoli"


def declared(labels=(DEPOSIT,), destination=DEPOSIT, incoming_only=False):
    """One destination and the texts that route money into it."""
    return (
        Passthrough(destination=destination, labels=tuple(labels), incoming_only=incoming_only),
    )


def test_a_declared_own_account_leg_stops_being_spending(ledger):
    revolut, _ = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-10", "-2550.00", f"To {DEPOSIT}"))
    ledger.record(make_txn(ledger, revolut, "2026-02-11", "-42.50", "EKOM | Cart"))

    moved = link_passthrough_legs(ledger, declared())

    assert moved == 1
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("42.50")
    # Kept, not deleted: the virtual account is where you can see what moved.
    deposit_leg = ledger.conn.execute(
        "SELECT id FROM transactions WHERE amount = '-2550.00'"
    ).fetchone()["id"]
    assert ledger.transfer_target(deposit_leg) == DEPOSIT
    assert ledger.is_transfer(deposit_leg) is True
    ledger.validate()


def test_the_pass_matches_the_label_anywhere_but_only_where_it_is(ledger):
    revolut, _ = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-10", "-100.00", "Bonifico", counterparty_account=None))
    ledger.record(
        IncomingTransaction(
            account_id=revolut,
            date=dt.date(2026, 2, 11),
            amount=Decimal("-50.00"),
            description="Bonifico",
            status="BOOK",
            source="psd2",
            balancing_account_id=ledger.uncategorized(),
            counterparty=f"to {DEPOSIT.upper()}",
            raw={},
        )
    )

    moved = link_passthrough_legs(ledger, declared())

    # The counterparty carries the label in a different case; the plain bonifico
    # stays a normal outflow, because nothing declared it.
    assert moved == 1
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("100.00")


def test_the_pass_is_idempotent_and_leaves_paired_transfers_alone(ledger):
    revolut, fineco = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", f"To {DEPOSIT}"))
    ledger.record(make_txn(ledger, fineco, "2026-02-16", "840.00", "Bonifico ricevuto"))
    link_transfers(ledger)

    first = link_passthrough_legs(ledger, declared())
    second = link_passthrough_legs(ledger, declared())

    # The real pair won, and the label match cannot touch a linked leg.
    assert first == 0
    assert second == 0
    paired = ledger.conn.execute("SELECT id FROM transactions WHERE amount = '-840.00'").fetchone()["id"]
    assert ledger.transfer_target(paired) == "Transfer clearing"
    assert ledger.is_transfer(paired) is True
    assert ledger.category_of(paired) is None
    assert transfer_amount_total(ledger) == Decimal("0.00")


def test_a_label_that_names_a_category_is_refused(ledger):
    """Posting to an account that is not virtual would count as spending."""
    groceries = ledger.category(DEPOSIT)
    revolut, _ = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-10", "-100.00", f"To {DEPOSIT}"))

    with pytest.raises(ValueError):
        link_passthrough_legs(ledger, declared())

    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("100.00")
    assert ledger.account(groceries)["type"] == "category"


def test_a_proposal_for_the_own_account_merchant_is_dropped(ledger):
    """Nothing categorizes a leg you moved to your own account, so the proposal goes."""
    revolut, _ = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-02-10", "-500.00", f"To {DEPOSIT}"))
    ledger.record_suggestion(f"To {DEPOSIT}", "Altro", "classifier")
    ledger.record_suggestion("EKOM", "Trasporti", "classifier")

    link_passthrough_legs(ledger, declared())

    assert [row["merchant"] for row in ledger.suggestions("pending")] == ["EKOM"]


def test_an_incoming_only_declaration_leaves_the_same_name_going_out_alone(ledger):
    """A firm that gives a bill back also gets paid: only the arrival is excluded."""
    revolut, _ = setup_accounts(ledger)
    paid = ledger.record(make_txn(ledger, revolut, "2026-02-10", "-120.00", "Assicurazioni | Premio"))[0]
    refund = ledger.record(
        IncomingTransaction(
            account_id=revolut,
            date=dt.date(2026, 2, 20),
            amount=Decimal("80.00"),
            description="Assicurazioni | Rimborso",
            status="BOOK",
            source="psd2",
            balancing_account_id=ledger.uncategorized(),
            raw={},
        )
    )[0]

    moved = link_passthrough_legs(ledger, declared(("Assicurazioni",), "Rimborsi", incoming_only=True))

    assert moved == 1
    assert ledger.transfer_target(refund) == "Rimborsi"
    # The premium stays spending: the same name going the other way is not a refund.
    assert ledger.transfer_of(paid) is None
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("120.00")


def test_one_destination_collects_several_names(ledger):
    """The co-holder's share and somebody's reimbursement are the same kind of money."""
    revolut, _ = setup_accounts(ledger)
    share = ledger.record(
        IncomingTransaction(
            account_id=revolut,
            date=dt.date(2026, 6, 14),
            amount=Decimal("300.00"),
            description="From Chiara B",
            status="BOOK",
            source="psd2",
            balancing_account_id=ledger.uncategorized(),
            counterparty="Chiara Bianchi",
            raw={},
        )
    )[0]
    back = ledger.record(
        IncomingTransaction(
            account_id=revolut,
            date=dt.date(2026, 6, 30),
            amount=Decimal("150.00"),
            description="Telefono cellulare",
            status="BOOK",
            source="psd2",
            balancing_account_id=ledger.uncategorized(),
            counterparty="Marco Neri",
            raw={},
        )
    )[0]

    moved = link_passthrough_legs(
        ledger, declared(("Chiara", "Marco"), "Rimborsi e quote", incoming_only=True)
    )

    # One name is on the description, the other only on the counterparty.
    assert moved == 2
    assert ledger.virtual_accounts() == ["Rimborsi e quote"]
    assert ledger.transfer_target(share) == "Rimborsi e quote"
    assert ledger.transfer_target(back) == "Rimborsi e quote"


# -- managing a transfer by hand -------------------------------------------
#
# The matcher proposes; a person decides. Each decision below promises
# something about the ledger afterwards, and the promise is what is asserted.


def test_a_leg_says_where_its_other_half_is(ledger):
    revolut, fineco = setup_accounts(ledger)
    out = ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Bonifico"))[0]
    back = ledger.record(make_txn(ledger, fineco, "2026-02-16", "840.00", "Bonifico ricevuto"))[0]
    plain = ledger.record(make_txn(ledger, revolut, "2026-02-17", "-9.90", "Netflix"))[0]
    link_transfers(ledger)

    proposed = ledger.transfer_of(out)

    # The clearing account is an implementation detail: what a person needs to
    # see is which account holds the other half.
    assert proposed == {"kind": "pair", "target": "Fineco", "state": "proposed", "leg_id": back}
    assert ledger.transfer_of(plain) is None

    ledger.set_transfer_review(out, back, "confirm")

    assert ledger.transfer_of(out)["state"] == "confirmed"


def test_a_leg_recorded_to_an_own_account_names_it(ledger):
    revolut, _ = setup_accounts(ledger)
    leg = ledger.record(make_txn(ledger, revolut, "2026-02-10", "-500.00", f"To {DEPOSIT}"))[0]

    ledger.mark_passthrough(leg, DEPOSIT)

    assert ledger.transfer_of(leg) == {
        "kind": "passthrough",
        "target": DEPOSIT,
        "state": "confirmed",
        "leg_id": None,
    }
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("0.00")
    ledger.validate()


def test_a_leg_cannot_be_recorded_anywhere_but_an_own_account(ledger):
    revolut, _ = setup_accounts(ledger)
    leg = ledger.record(make_txn(ledger, revolut, "2026-02-10", "-500.00", "Bonifico"))[0]

    # A tracked account has two legs to link; the pairing account is not a
    # destination; and a destination needs a name to be one.
    with pytest.raises(ValueError, match="link the two legs instead"):
        ledger.mark_passthrough(leg, "Fineco")
    with pytest.raises(ValueError, match="pairing account"):
        ledger.mark_passthrough(leg, "Transfer clearing")
    with pytest.raises(ValueError, match="needs a name"):
        ledger.mark_passthrough(leg, "   ")

    assert ledger.transfer_of(leg) is None


def test_marking_an_inflow_as_own_money_takes_it_out_of_income(ledger):
    """The shape of a top-up from an account that is not connected here."""
    from amonhen.metrics import monthly_flows

    revolut, _ = setup_accounts(ledger)
    ledger.record(make_txn(ledger, revolut, "2026-06-26", "2600.00", "ricarica revolut da stipendio"))
    ledger.record(make_txn(ledger, revolut, "2026-06-30", "300.00", "From Chiara B"))
    top_up = ledger.conn.execute(
        "SELECT id FROM transactions WHERE description LIKE 'ricarica%'"
    ).fetchone()["id"]
    today = dt.date(2026, 9, 13)

    def june():
        return next(
            flow
            for flow in monthly_flows(ledger, dt.date(2026, 1, 1), today)
            if flow.month == "2026-06"
        )

    before = june()

    ledger.mark_passthrough(top_up, "Conto stipendio")

    assert before.income == Decimal("2900.00")
    assert june().income == Decimal("300.00")
    ledger.validate()


def test_unlinking_an_own_leg_gives_it_back_to_the_queue(ledger):
    revolut, _ = setup_accounts(ledger)
    leg = ledger.record(make_txn(ledger, revolut, "2026-02-10", "-500.00", f"To {DEPOSIT}"))[0]
    ledger.mark_passthrough(leg, DEPOSIT)

    released = ledger.unlink_transfer(leg)

    assert released == DEPOSIT
    assert ledger.transfer_of(leg) is None
    assert ledger.category_of(leg) == "Uncategorized"
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("500.00")
    ledger.validate()


def test_unlinking_a_pair_keeps_the_decision_so_the_matcher_cannot_take_it_back(ledger):
    revolut, fineco = setup_accounts(ledger)
    out = ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Bonifico"))[0]
    back = ledger.record(make_txn(ledger, fineco, "2026-02-16", "840.00", "Bonifico ricevuto"))[0]
    link_transfers(ledger)
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("0.00")

    assert ledger.unlink_transfer(out) is None

    # The legs are spending again, and the row that says "no" keeps the pair out
    # of the candidate query: without it the next sync would put it straight back.
    assert ledger.category_of(out) == "Uncategorized"
    assert ledger.category_of(back) == "Uncategorized"
    assert ledger.transfer_link(out)["confirmed_by_human"] == -1
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("840.00")
    assert link_transfers(ledger) == 0
    ledger.validate()


def test_a_pair_made_by_hand_is_marked_as_already_reviewed(ledger):
    revolut, fineco = setup_accounts(ledger)
    out = ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Bonifico"))[0]
    back = ledger.record(make_txn(ledger, fineco, "2026-02-16", "840.00", "Bonifico ricevuto"))[0]

    ledger.mark_transfer_pair(out, back)

    assert ledger.transfer_of(out) == {
        "kind": "pair",
        "target": "Fineco",
        "state": "confirmed",
        "leg_id": back,
    }
    assert ledger.transfer_of(back)["target"] == "Revolut"
    assert ledger.transfer_link(out)["method"] == "human"
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("0.00")
    assert transfer_amount_total(ledger) == Decimal("0.00")
    ledger.validate()


def test_a_pair_the_matcher_would_not_accept_is_refused_by_hand_too(ledger):
    revolut, fineco = setup_accounts(ledger)
    out = ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Bonifico"))[0]
    same_account = ledger.record(make_txn(ledger, revolut, "2026-02-16", "840.00", "Rientro"))[0]
    other_amount = ledger.record(make_txn(ledger, fineco, "2026-02-16", "700.00", "Altro"))[0]
    spent = ledger.record(make_txn(ledger, revolut, "2026-02-17", "-500.00", "Spesa"))[0]
    cover = ledger.record(make_txn(ledger, fineco, "2026-02-17", "500.00", "Rimborso"))[0]

    with pytest.raises(ValueError, match="same account"):
        ledger.mark_transfer_pair(out, same_account)
    with pytest.raises(ValueError, match="equal and opposite"):
        ledger.mark_transfer_pair(out, other_amount)
    # A split carries a person's work, and linking a leg drops its category side.
    ledger.set_splits(
        spent,
        [(ledger.category("Groceries"), Decimal("300.00")), (ledger.uncategorized(), Decimal("200.00"))],
    )
    with pytest.raises(ValueError, match="split"):
        ledger.mark_transfer_pair(spent, cover)

    assert ledger.transfer_of(spent) is None


def test_a_rejected_pair_is_re_linked_on_the_row_it_already_has(ledger):
    revolut, fineco = setup_accounts(ledger)
    out = ledger.record(make_txn(ledger, revolut, "2026-02-15", "-840.00", "Bonifico"))[0]
    back = ledger.record(make_txn(ledger, fineco, "2026-02-16", "840.00", "Bonifico ricevuto"))[0]
    link_transfers(ledger)
    ledger.unlink_transfer(out)

    ledger.mark_transfer_pair(out, back)

    rows = ledger.conn.execute("SELECT COUNT(*) AS c FROM transfer_links").fetchone()["c"]
    # One row per pair: two rows for the same two legs would make the unmark
    # ambiguous, because rejecting them would only answer half of it.
    assert rows == 1
    assert ledger.transfer_link(out)["confirmed_by_human"] == 1
    assert ledger.spend_between(dt.date(2026, 2, 1), dt.date(2026, 2, 28)) == Decimal("0.00")


def test_candidates_are_the_legs_the_matcher_would_have_accepted(ledger):
    revolut, fineco = setup_accounts(ledger)
    out = ledger.record(make_txn(ledger, revolut, "2026-06-14", "-300.00", "Bonifico"))[0]
    near = ledger.record(make_txn(ledger, fineco, "2026-06-14", "300.00", "Bonifico ricevuto"))[0]
    ledger.record(make_txn(ledger, fineco, "2026-06-20", "300.00", "Troppo tardi"))
    ledger.record(make_txn(ledger, revolut, "2026-06-14", "300.00", "Stesso conto"))

    candidates = pair_candidates(ledger, out)

    assert [row["id"] for row in candidates] == [near]


def test_the_panel_offers_the_leg_the_bank_identified_first(ledger):
    """Two legs the matcher would accept, listed by how much evidence each carries."""
    revolut, fineco = setup_accounts(ledger, ibans=True)
    out = ledger.record(make_txn(ledger, revolut, "2026-06-14", "-300.00", "Bonifico",
                                 counterparty_account=FINECO_IBAN))[0]
    anonymous = ledger.record(
        make_txn(ledger, fineco, "2026-06-14", "300.00", "Senza controparte")
    )[0]
    identified = ledger.record(make_txn(ledger, fineco, "2026-06-14", "300.00", "Dal conto",
                                        counterparty_account=REVOLUT_IBAN))[0]

    candidates = pair_candidates(ledger, out)

    assert [row["id"] for row in candidates] == [identified, anonymous]


def test_a_leg_already_spoken_for_is_not_a_candidate(ledger):
    revolut, fineco = setup_accounts(ledger)
    out = ledger.record(make_txn(ledger, revolut, "2026-06-14", "-300.00", "Bonifico"))[0]
    recorded = ledger.record(make_txn(ledger, fineco, "2026-06-14", "300.00", "Bonifico ricevuto"))[0]
    paired = ledger.record(make_txn(ledger, fineco, "2026-06-15", "300.00", "Ancora"))[0]
    other = ledger.record(make_txn(ledger, revolut, "2026-06-16", "-300.00", "Il suo"))[0]
    ledger.mark_passthrough(recorded, DEPOSIT)
    ledger.mark_transfer_pair(paired, other)

    assert pair_candidates(ledger, out) == []


def test_a_candidate_the_matcher_scores_zero_is_not_offered(ledger):
    revolut, fineco = setup_accounts(ledger)
    out = ledger.record(make_txn(ledger, revolut, "2026-06-14", "-300.00", "Bonifico"))[0]
    ledger.record(
        make_txn(
            ledger,
            fineco,
            "2026-06-14",
            "300.00",
            "Bonifico ricevuto",
            counterparty_account="IT00X0000000000000000000000",
        )
    )

    # One side names the counterparty account and the other names a third party:
    # an amount coincidence, which the matcher refuses and so does the panel.
    assert pair_candidates(ledger, out) == []
