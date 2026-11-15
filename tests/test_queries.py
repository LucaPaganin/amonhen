"""The screens' reads, called on a ledger with no HTTP in between.

They used to be written inside the routes and could only be reached through a
request; the API tests still cover them that way, and these call them directly.
"""
import datetime as dt
from decimal import Decimal

from amonhen import queries
from amonhen.models import Account, IncomingTransaction
from amonhen.transfers import link_transfers


def record(ledger, account_id, date, amount, description, external_id):
    return ledger.record(
        IncomingTransaction(
            account_id=account_id,
            date=dt.date.fromisoformat(date),
            amount=Decimal(amount),
            description=description,
            status="BOOK",
            source="psd2",
            balancing_account_id=ledger.uncategorized(),
            external_id=external_id,
        )
    )[0]


def three_movements(ledger):
    """A coffee, and a transfer between two tracked accounts."""
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    coffee = record(ledger, fineco, "2026-09-01", "-2.50", "Caffè", "f-1")
    out = record(ledger, fineco, "2026-09-02", "-100.00", "Bonifico", "f-2")
    back = record(ledger, revolut, "2026-09-02", "100.00", "Bonifico ricevuto", "r-1")
    link_transfers(ledger)
    return fineco, revolut, coffee, out, back


def test_a_page_of_movements_newest_first(ledger):
    _, _, coffee, out, back = three_movements(ledger)

    page = queries.transaction_page(
        ledger, queries.TransactionFilter(), everyday=False, limit=10, offset=0
    )

    assert page.total == 3
    assert page.hidden == 0
    assert [row["id"] for row in page.rows][-1] == coffee


def test_everyday_leaves_the_transfer_out_and_says_how_much(ledger):
    _, _, coffee, _, _ = three_movements(ledger)

    page = queries.transaction_page(
        ledger, queries.TransactionFilter(), everyday=True, limit=10, offset=0
    )

    assert [row["id"] for row in page.rows] == [coffee]
    assert (page.total, page.hidden) == (1, 2)


def test_the_filters_narrow_by_account_text_and_size(ledger):
    fineco, revolut, coffee, out, back = three_movements(ledger)

    def ids(**fields):
        page = queries.transaction_page(
            ledger, queries.TransactionFilter(**fields), everyday=False, limit=10, offset=0
        )
        return {row["id"] for row in page.rows}

    assert ids(account_id=revolut) == {back}
    assert ids(search="caff") == {coffee}
    # A size, without sign: both legs of the transfer are a hundred.
    assert ids(amount_min="50") == {out, back}
    assert ids(transfer=False) == {coffee}


def test_one_row_answers_none_when_there_is_none(ledger):
    groceries = ledger.category("Spesa")

    assert queries.real_account(ledger, groceries) is None
    assert queries.account(ledger, groceries)["type"] == "category"
    assert queries.transaction(ledger, 999) is None
    assert queries.queue_rows(ledger, []) == []


def test_the_queue_holds_what_waits_and_names_its_accounts(ledger):
    fineco, _, coffee, _, _ = three_movements(ledger)

    backlog = queries.uncategorized_backlog(ledger)

    # The transfer legs are paired, so only the coffee waits for a category.
    assert [row["id"] for row in backlog] == [coffee]
    assert [row["name"] for row in queries.backlog_accounts(ledger)] == ["Fineco"]
    assert [row["id"] for row in queries.queue_rows(ledger, [coffee])] == [coffee]
    assert queries.proposed_transfers(ledger, 10)[0] == 1
