"""HTTP API: the surface the PWA talks to."""
import datetime as dt
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from amonhen.api import create_app
from amonhen.db import connect
from amonhen.ledger import Ledger
from amonhen.models import Account, IncomingTransaction
from amonhen.transfers import link_transfers


def make_txn(ledger, account_id, date, amount, description, status="BOOK"):
    return IncomingTransaction(
        account_id=account_id,
        date=dt.date.fromisoformat(date),
        amount=Decimal(amount),
        description=description,
        status=status,
        source="psd2",
        balancing_account_id=ledger.uncategorized(),
        raw={},
    )


@pytest.fixture
def api(tmp_path):
    db_path = tmp_path / "ledger.db"
    client = TestClient(create_app(db_path, web_dist=tmp_path / "missing"))

    conn = connect(db_path)
    ledger = Ledger(conn)
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    ledger.record(make_txn(ledger, revolut, "2026-08-03", "-42.50", "EKOM | Cart"))
    ledger.record(make_txn(ledger, revolut, "2026-08-07", "-3.00", "Bar Centrale"))
    ledger.record(make_txn(ledger, revolut, "2026-08-05", "1200.00", "Stipendio"))
    ledger.record(make_txn(ledger, revolut, "2026-08-06", "-9.90", "Netflix", status="PDNG"))
    ledger.record(make_txn(ledger, revolut, "2026-08-15", "-840.00", "Bonifico"))
    ledger.record(make_txn(ledger, fineco, "2026-08-15", "840.00", "Bonifico"))
    link_transfers(ledger)
    conn.close()

    yield client, db_path
    client.close()


def test_health_reports_the_api_version_the_app_reads(api):
    client, _ = api

    health = client.get("/api/health").json()

    # The PWA refuses to render against a server older than the shape it needs.
    assert health["status"] == "ok"
    assert health["api_version"] >= 2


def test_accounts_report_balances(api):
    client, _ = api

    accounts = client.get("/api/accounts").json()

    names = {account["name"] for account in accounts}
    assert names == {"Revolut", "Fineco"}
    revolut = next(account for account in accounts if account["name"] == "Revolut")
    assert Decimal(revolut["balance"]) == Decimal("304.60")


def test_accounts_report_whether_the_balance_agrees_with_the_bank(api):
    """The 5.4 assertion is only an assertion if the app says the outcome."""
    client, db_path = api
    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger

    def declare(amount: str, source: str) -> None:
        conn = open_ledger_db(db_path)
        ledger = Ledger(conn)
        ledger.record_declared_balance(
            ledger.find_account(name="Revolut")["id"], dt.date(2026, 9, 12), Decimal(amount), source
        )
        conn.close()

    def verification() -> dict:
        return {a["name"]: a["verification"] for a in client.get("/api/accounts").json()}

    nothing_declared = verification()
    assert {item["state"] for item in nothing_declared.values()} == {"unverified"}
    assert all(item["checks"] == [] for item in nothing_declared.values())

    # The bank's two figures for one date differ by the pending movement, and
    # each is compared with the ledger figure that means the same.
    declare("304.60", "eb:ITAV")
    declare("314.50", "eb:ITBD")

    agreed = verification()
    assert agreed["Revolut"]["state"] == "verified"
    assert agreed["Revolut"]["date"] == "2026-09-12"
    assert [(c["kind"], c["computed"], c["ok"]) for c in agreed["Revolut"]["checks"]] == [
        ("available", "304.60", True),
        ("booked", "314.50", True),
    ]
    # Fineco never had a balance declared: not verified, not assumed.
    assert agreed["Fineco"]["state"] == "unverified"

    declare("300.00", "eb:ITAV")

    disagreed = verification()
    assert disagreed["Revolut"]["state"] == "mismatch"
    assert [(c["kind"], c["difference"], c["ok"]) for c in disagreed["Revolut"]["checks"]] == [
        ("available", "-4.60", False),
        ("booked", "0.00", True),
    ]


def test_categories_include_the_review_bucket(api):
    client, _ = api

    names = {category["name"] for category in client.get("/api/categories").json()}

    assert "Uncategorized" in names


def test_transactions_are_filterable(api):
    client, _ = api

    everything = client.get("/api/transactions").json()
    assert everything["total"] == 6

    august = client.get("/api/transactions", params={"from": "2026-08-01", "to": "2026-08-31"}).json()
    assert august["total"] == 6
    july = client.get("/api/transactions", params={"to": "2026-07-31"}).json()
    assert july["total"] == 0

    searched = client.get("/api/transactions", params={"search": "ekom"}).json()
    assert searched["total"] == 1
    assert searched["items"][0]["merchant"] == "EKOM"

    pending = client.get("/api/transactions", params={"status": "PDNG"}).json()
    assert pending["total"] == 1


def test_transactions_paginate(api):
    client, _ = api

    page = client.get("/api/transactions", params={"limit": 2, "offset": 2}).json()

    assert page["total"] == 6
    assert len(page["items"]) == 2
    assert page["items"][0]["date"] >= page["items"][1]["date"]


def test_one_transaction_can_be_read_and_a_missing_one_is_404(api):
    client, _ = api
    first = client.get("/api/transactions").json()["items"][0]

    assert client.get(f"/api/transactions/{first['id']}").json()["id"] == first["id"]
    assert client.get("/api/transactions/999999").status_code == 404


def test_review_lists_uncategorized_movements_and_candidate_transfers(api):
    client, _ = api

    queue = client.get("/api/review").json()

    # Settled outflows only: the pending Netflix row and the incoming salary
    # are not review work.
    assert [item["merchant"] for item in queue["uncategorized"]] == ["Bar Centrale", "EKOM"]
    assert queue["uncategorized_total"] == 2
    assert queue["transfers_total"] == 1
    assert len(queue["transfers"]) == 1
    link = queue["transfers"][0]
    # Each half names the account that holds the other one.
    assert link["leg_a"]["transfer"]["target"] == link["leg_b"]["account"]["name"]
    assert link["leg_b"]["transfer"]["target"] == link["leg_a"]["account"]["name"]
    assert link["leg_a"]["transfer"]["state"] == "proposed"
    assert link["leg_a"]["category"] is None
    assert link["confidence"] in ("high", "medium")


def test_setting_a_category_moves_the_movement_out_of_the_queue(api):
    client, _ = api
    transaction_id = client.get("/api/review").json()["uncategorized"][0]["id"]

    response = client.post(
        f"/api/transactions/{transaction_id}/category", json={"category": "Groceries"}
    )

    assert response.status_code == 200
    assert response.json()["category"] == "Groceries"
    remaining = client.get("/api/review").json()
    assert [item["merchant"] for item in remaining["uncategorized"]] == ["EKOM"]
    assert remaining["uncategorized_total"] == 1
    categorized = client.get("/api/transactions", params={"category": "Groceries"}).json()
    assert categorized["total"] == 1


def test_categorizing_a_transfer_leg_is_refused(api):
    client, _ = api
    leg = client.get("/api/review").json()["transfers"][0]["leg_a"]["id"]

    response = client.post(f"/api/transactions/{leg}/category", json={"category": "Groceries"})

    assert response.status_code == 409
    assert "transfer" in response.json()["detail"]


def test_confirming_a_transfer_keeps_it_out_of_the_queue(api):
    client, _ = api
    link = client.get("/api/review").json()["transfers"][0]

    response = client.post(
        f"/api/transfers/{link['leg_a']['id']}/{link['leg_b']['id']}/review",
        json={"decision": "confirm"},
    )

    assert response.status_code == 200
    assert client.get("/api/review").json()["transfers"] == []


def test_rejecting_a_transfer_gives_the_expense_back(api):
    client, _ = api
    link = client.get("/api/review").json()["transfers"][0]

    client.post(
        f"/api/transfers/{link['leg_a']['id']}/{link['leg_b']['id']}/review",
        json={"decision": "reject"},
    )

    queue = client.get("/api/review").json()
    assert queue["transfers"] == []
    merchants = {item["merchant"] for item in queue["uncategorized"]}
    assert merchants == {"Bar Centrale", "EKOM", "Bonifico"}
    for leg in (link["leg_a"]["id"], link["leg_b"]["id"]):
        restored = client.get(f"/api/transactions/{leg}").json()
        assert restored["transfer"] is None
        assert restored["category"] == "Uncategorized"


def test_review_totals_are_not_capped_by_the_page(api):
    client, _ = api

    queue = client.get("/api/review", params={"limit": 1}).json()

    assert len(queue["uncategorized"]) == 1
    assert queue["uncategorized_total"] == 2
    assert len(queue["transfers"]) == 1
    assert queue["transfers_total"] == 1


def test_review_says_what_each_row_already_survived(api):
    """A merchant with a pending proposal is waiting for a decision; one
    without it fell through every automatic pass and is manual work."""
    client, db_path = api
    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger

    conn = open_ledger_db(db_path)
    Ledger(conn).record_suggestion("EKOM", "Trasporti", "classifier")
    conn.close()

    queue = client.get("/api/review").json()

    assert {item["merchant"]: item["review_state"] for item in queue["uncategorized"]} == {
        "Bar Centrale": "unhandled",
        "EKOM": "proposed",
    }
    proposed = next(item for item in queue["uncategorized"] if item["merchant"] == "EKOM")
    assert proposed["proposed_category"] == "Trasporti"
    assert queue["proposed_total"] == 1
    assert queue["unhandled_total"] == 1
    assert queue["proposals_total"] == 1
    assert queue["uncategorized_total"] == 2


def test_review_filters_narrow_the_page_and_leave_the_counts_alone(api):
    client, db_path = api
    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger

    conn = open_ledger_db(db_path)
    ledger = Ledger(conn)
    ledger.record_suggestion("EKOM", "Trasporti", "classifier")
    revolut = ledger.find_account(name="Revolut")["id"]
    fineco = ledger.find_account(name="Fineco")["id"]
    conn.close()

    unhandled = client.get("/api/review", params={"state": "unhandled"}).json()
    assert [item["merchant"] for item in unhandled["uncategorized"]] == ["Bar Centrale"]

    proposed = client.get("/api/review", params={"state": "proposed"}).json()
    assert [item["merchant"] for item in proposed["uncategorized"]] == ["EKOM"]

    searched = client.get("/api/review", params={"search": "ekom"}).json()
    assert [item["merchant"] for item in searched["uncategorized"]] == ["EKOM"]

    mine = client.get("/api/review", params={"account_id": revolut}).json()
    assert len(mine["uncategorized"]) == 2
    other = client.get("/api/review", params={"account_id": fineco}).json()
    assert other["uncategorized"] == []

    # Whatever the filter, the chips keep counting the whole backlog.
    for payload in (unhandled, proposed, searched, other):
        assert payload["uncategorized_total"] == 2
        assert payload["proposed_total"] == 1
        assert payload["unhandled_total"] == 1


def test_reviewing_an_unknown_link_is_404(api):
    client, _ = api

    response = client.post("/api/transfers/1/2/review", json={"decision": "confirm"})

    assert response.status_code == 404


def test_a_rule_can_be_added_and_applied(api):
    client, _ = api

    created = client.post("/api/rules", json={"pattern": "EKOM", "category": "Groceries"})
    assert created.status_code == 201
    assert created.json()["count"] == 1

    # Adding a rule applies it on the spot, so a later pass has nothing to do.
    applied = client.post("/api/categorize").json()
    assert applied["applied"] == 0
    assert client.get("/api/rules").json() == [
        {"pattern": "EKOM", "category": "Groceries", "count": 1}
    ]
    assert client.get("/api/transactions", params={"category": "Groceries"}).json()["total"] == 1


def test_categories_carry_the_metrics_flags_and_can_be_toggled(api):
    client, _ = api
    groceries = next(c for c in client.get("/api/categories").json() if c["name"] == "Uncategorized")
    assert groceries["episodic"] is False and groceries["essential"] is False

    patched = client.patch(f"/api/categories/{groceries['id']}", json={"essential": True})

    assert patched.status_code == 200
    assert patched.json()["essential"] is True
    assert client.patch(f"/api/categories/{groceries['id']}", json={}).status_code == 422


def test_accounts_carry_the_investment_flag_and_can_be_toggled(api):
    client, _ = api
    revolut = next(a for a in client.get("/api/accounts").json() if a["name"] == "Revolut")

    patched = client.patch(f"/api/accounts/{revolut['id']}", json={"investment": True})

    assert patched.status_code == 200
    assert patched.json()["investment"] is True
    assert client.patch(f"/api/accounts/{revolut['id']}", json={}).status_code == 422


def test_splits_balance_and_are_reported(api):
    client, _ = api
    client.post("/api/categories", json={"name": "Groceries"})
    client.post("/api/categories", json={"name": "Household"})
    transaction_id = client.get("/api/transactions", params={"search": "ekom"}).json()["items"][0]["id"]

    response = client.put(
        f"/api/transactions/{transaction_id}/splits",
        json={"splits": [
            {"category": "Groceries", "amount": "30.00"},
            {"category": "Household", "amount": "12.50"},
        ]},
    )

    assert response.status_code == 200
    assert response.json()["splits"] == [
        {"category": "Groceries", "amount": "30.00"},
        {"category": "Household", "amount": "12.50"},
    ]
    assert client.get("/api/transactions", params={"category": "Groceries"}).json()["total"] == 1
    assert client.get("/api/transactions", params={"category": "Household"}).json()["total"] == 1


def test_an_unbalanced_split_is_refused(api):
    client, _ = api
    client.post("/api/categories", json={"name": "Groceries"})
    transaction_id = client.get("/api/transactions", params={"search": "ekom"}).json()["items"][0]["id"]

    response = client.put(
        f"/api/transactions/{transaction_id}/splits",
        json={"splits": [{"category": "Groceries", "amount": "10.00"}]},
    )

    assert response.status_code == 422
    assert "does not balance" in response.json()["detail"]


def test_a_transfer_leg_cannot_be_split(api):
    client, _ = api
    leg = client.get("/api/review").json()["transfers"][0]["leg_a"]["id"]

    response = client.put(
        f"/api/transactions/{leg}/splits",
        json={"splits": [{"category": "Uncategorized", "amount": "1.00"}]},
    )

    assert response.status_code == 409


def test_metrics_expose_the_section_5_6_shape(api):
    client, _ = api

    metrics = client.get("/api/metrics").json()

    assert set(metrics) >= {
        "months_of_history", "partial", "episodic_partial", "recurring_burn",
        "episodic_accrual", "expected_burn", "liquidity",
        "runway_months", "essential_monthly", "discretionary_monthly", "savings_flow",
    }
    # The mortgage is not a concept any more: not in the payload, not in the query.
    assert "mortgage_monthly" not in metrics
    # The fixture covers a single month, so nothing may be presented as final.
    assert metrics["partial"] is True
    assert metrics["episodic_partial"] is True


def test_spending_endpoint_is_the_pie_of_the_period(api):
    client, _ = api

    payload = client.get(
        "/api/spending", params={"from": "2026-08-01", "to": "2026-08-31"}
    ).json()

    assert payload["period"] == {"start": "2026-08-01", "end": "2026-08-31"}
    assert payload["applied"]["from"] == "2026-08-01"
    # The transfer leg balances through the transfer account, and the pending
    # row is not settled money: neither belongs in the pie.
    assert payload["categories"] == [{"category": "Uncategorized", "amount": "45.50"}]
    assert payload["total"] == "45.50"


def test_flows_endpoint_pairs_income_and_expenses_per_month(api):
    client, _ = api

    months = client.get(
        "/api/flows", params={"from": "2026-08-01", "to": "2026-09-30"}
    ).json()["months"]

    assert [item["month"] for item in months] == ["2026-08", "2026-09"]
    # The 840 coming in is the other leg of a transfer, not income.
    assert months[0] == {
        "month": "2026-08",
        "income": "1200.00",
        "expenses": "45.50",
        "partial": False,
    }
    assert months[1]["income"] == "0.00" and months[1]["expenses"] == "0.00"
    assert months[1]["partial"] is True


def test_networth_endpoint_reports_observations_without_inventing_a_series(api):
    client, db_path = api

    empty = client.get("/api/networth").json()

    assert empty["points"] == [] and empty["accounts"] == []

    conn = connect(db_path)
    ledger = Ledger(conn)
    revolut = ledger.find_account(name="Revolut")["id"]
    ledger.record_declared_balance(revolut, dt.date(2026, 9, 1), Decimal("304.60"), "eb:ITAV")
    conn.close()

    payload = client.get(
        "/api/networth", params={"from": "2026-08-01", "to": "2026-09-30"}
    ).json()

    assert payload["points"] == [{"date": "2026-09-01", "total": "304.60"}]
    assert payload["accounts"] == [
        {"account": "Revolut", "date": "2026-09-01", "balance": "304.60"}
    ]


def test_a_category_cannot_take_an_existing_account_name(api):
    client, _ = api

    response = client.post("/api/categories", json={"name": "Revolut"})

    assert response.status_code == 422
    assert "not a category" in response.json()["detail"]


def test_an_empty_category_name_is_refused(api):
    client, _ = api

    assert client.post("/api/categories", json={"name": ""}).status_code == 422
    assert client.post("/api/categories", json={"name": "  "}).status_code == 422


def test_assigning_an_empty_category_is_refused(api):
    client, _ = api
    # A transfer leg answers 409 first, so use an ordinary uncategorized row.
    transaction_id = client.get("/api/transactions", params={"search": "ekom"}).json()["items"][0]["id"]

    response = client.post(f"/api/transactions/{transaction_id}/category", json={"category": ""})

    assert response.status_code == 422
    assert "needs a name" in response.json()["detail"]


def test_a_rule_cannot_use_a_non_category_name(api):
    client, _ = api

    response = client.post("/api/rules", json={"pattern": "EKOM", "category": "Revolut"})

    assert response.status_code == 422


def test_budgets_report_spent_and_remaining(api):
    client, _ = api
    client.post("/api/categories", json={"name": "Groceries"})
    groceries = next(c for c in client.get("/api/categories").json() if c["name"] == "Groceries")
    transaction_id = client.get("/api/transactions", params={"search": "ekom"}).json()["items"][0]["id"]
    client.post(f"/api/transactions/{transaction_id}/category", json={"category": "Groceries"})

    saved = client.put(f"/api/budgets/{groceries['id']}", json={"amount": "100.00"})
    assert saved.status_code == 200

    month = client.get("/api/transactions").json()["items"][0]["date"][:7]
    status = {row["category"]: row for row in client.get("/api/budgets", params={"month": month}).json()}
    assert status["Groceries"]["budget"] == "100.00"
    assert status["Groceries"]["spent"] == "42.50"
    assert status["Groceries"]["remaining"] == "57.50"


def test_a_budget_can_be_cleared_and_cannot_be_negative(api):
    client, _ = api
    client.post("/api/categories", json={"name": "Groceries"})
    groceries = next(c for c in client.get("/api/categories").json() if c["name"] == "Groceries")

    assert client.put(f"/api/budgets/{groceries['id']}", json={"amount": "-5.00"}).status_code == 422
    client.put(f"/api/budgets/{groceries['id']}", json={"amount": "50.00"})
    client.put(f"/api/budgets/{groceries['id']}", json={"amount": None})

    status = {row["category"]: row for row in client.get("/api/budgets").json()}
    assert status["Groceries"]["budget"] is None


def test_budgets_refuse_a_non_category(api):
    client, _ = api
    revolut = next(a for a in client.get("/api/accounts").json() if a["name"] == "Revolut")

    response = client.put(f"/api/budgets/{revolut['id']}", json={"amount": "10.00"})

    assert response.status_code == 422


def test_suggestions_can_be_reviewed_and_accepting_creates_a_rule(api):
    client, db_path = api
    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger

    conn = open_ledger_db(db_path)
    Ledger(conn).record_suggestion("EKOM", "Groceries", "classifier")
    conn.close()

    listed = client.get("/api/suggestions").json()
    assert len(listed) == 1
    assert listed[0]["merchant"] == "EKOM"
    assert listed[0]["category"] == "Groceries"
    assert listed[0]["source"] == "classifier"
    # The fixture's EKOM movement is one movement of 42,50 on one day: the queue
    # has to say what a yes decides, not just whose decision it is.
    assert listed[0]["stake"] == {
        "movements": 1,
        "total": "42.50",
        "first_date": "2026-08-03",
        "last_date": "2026-08-03",
    }

    accepted = client.post(
        "/api/suggestions/decision", json={"merchant": "EKOM", "decision": "accept"}
    )

    assert accepted.status_code == 200
    assert client.get("/api/suggestions").json() == []
    assert client.get("/api/rules").json() == [
        {"pattern": "EKOM", "category": "Groceries", "count": 1}
    ]
    assert client.get("/api/transactions", params={"category": "Groceries"}).json()["total"] == 1


def test_a_proposal_can_be_accepted_with_a_category_that_corrects_it(api):
    """The proposal is a starting point: a person may correct it, and the rule
    that is written carries the category that was chosen, not the proposed one."""
    client, db_path = api
    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger

    conn = open_ledger_db(db_path)
    Ledger(conn).record_suggestion("EKOM", "Groceries", "classifier")
    conn.close()

    accepted = client.post(
        "/api/suggestions/decision",
        json={"merchant": "EKOM", "decision": "accept", "category": "Trasporti"},
    )

    assert accepted.status_code == 200
    assert client.get("/api/rules").json() == [
        {"pattern": "EKOM", "category": "Trasporti", "count": 1}
    ]
    movement = client.get("/api/transactions", params={"search": "ekom"}).json()["items"][0]
    assert movement["category"] == "Trasporti"


def test_a_proposal_cannot_be_accepted_into_the_review_bucket(api):
    """A rule pointing at the bucket would take movements out of the queue
    without categorizing them: the ledger refuses it, whichever route asks."""
    client, db_path = api
    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger

    conn = open_ledger_db(db_path)
    Ledger(conn).record_suggestion("EKOM", "Groceries", "classifier")
    conn.close()

    refused = client.post(
        "/api/suggestions/decision",
        json={"merchant": "EKOM", "decision": "accept", "category": "Uncategorized"},
    )

    assert refused.status_code == 422
    assert client.get("/api/rules").json() == []


def test_a_proposal_for_a_merchant_with_nothing_waiting_has_a_zero_stake(api):
    """A proposal can outlive its movements: a rule that answered them, or a
    person's own decision, leaves the queue with nothing left to weigh."""
    client, db_path = api
    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger

    conn = open_ledger_db(db_path)
    Ledger(conn).record_suggestion("MAI VISTO", "Groceries", "classifier")
    conn.close()

    stake = client.get("/api/suggestions").json()[0]["stake"]

    assert stake == {"movements": 0, "total": "0.00", "first_date": None, "last_date": None}


def test_dismissing_a_suggestion_leaves_no_rule(api):
    client, db_path = api
    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger

    conn = open_ledger_db(db_path)
    Ledger(conn).record_suggestion("EKOM", "Groceries", "llm")
    conn.close()

    dismissed = client.post(
        "/api/suggestions/decision", json={"merchant": "EKOM", "decision": "dismiss"}
    )
    assert dismissed.status_code == 200

    assert client.get("/api/suggestions").json() == []
    assert client.get("/api/rules").json() == []


def test_reviewing_an_unknown_suggestion_is_404(api):
    client, _ = api

    response = client.post(
        "/api/suggestions/decision", json={"merchant": "NOPE", "decision": "accept"}
    )

    assert response.status_code == 404


def test_anomalies_endpoint_returns_the_explained_list(api):
    client, _ = api

    response = client.get("/api/anomalies")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_the_classifier_endpoint_records_proposals_without_applying_them(api):
    client, _ = api

    response = client.post("/api/propose")

    assert response.status_code == 200
    assert set(response.json()) == {"considered", "recorded"}
    assert client.get("/api/transactions", params={"category": "Uncategorized"}).json()["total"] > 0


def test_a_merchant_with_a_slash_can_still_be_decided(api):
    """Merchant names come from the bank and routinely contain a slash."""
    client, db_path = api
    from amonhen.db import open_ledger_db
    from amonhen.ledger import Ledger

    conn = open_ledger_db(db_path)
    Ledger(conn).record_suggestion("1051455028466/paypal", "Spesa", "classifier")
    conn.close()

    response = client.post(
        "/api/suggestions/decision",
        json={"merchant": "1051455028466/paypal", "decision": "accept"},
    )

    assert response.status_code == 200
    assert client.get("/api/suggestions").json() == []
    assert client.get("/api/rules").json() == [
        {"pattern": "1051455028466/paypal", "category": "Spesa", "count": 0}
    ]


def test_a_budget_on_the_uncategorized_bucket_is_refused(api):
    client, _ = api
    uncategorized = next(c for c in client.get("/api/categories").json() if c["name"] == "Uncategorized")

    response = client.put(f"/api/budgets/{uncategorized['id']}", json={"amount": "10.00"})

    assert response.status_code == 422
    assert all(row["budget"] is None for row in client.get("/api/budgets").json())


def test_a_budget_on_an_unknown_account_is_404(api):
    client, _ = api

    assert client.put("/api/budgets/99999", json={"amount": "10.00"}).status_code == 404


def test_a_malformed_budget_amount_is_422(api):
    client, _ = api
    client.post("/api/categories", json={"name": "Groceries"})
    groceries = next(c for c in client.get("/api/categories").json() if c["name"] == "Groceries")

    for amount in ("abc", "", "1.2.3"):
        response = client.put(f"/api/budgets/{groceries['id']}", json={"amount": amount})
        assert response.status_code == 422, amount


def test_a_malformed_model_reply_is_reported_as_an_upstream_failure(api, monkeypatch):
    import requests

    from amonhen import api as api_module

    class BadResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "not json"}}]}

    monkeypatch.setattr(requests, "post", lambda *a, **k: BadResponse())
    from amonhen.llm import LlmConfig

    monkeypatch.setattr(
        api_module,
        "llm_config",
        lambda: LlmConfig(url="https://llm.test/v1/chat/completions", api_key="k", model="m"),
    )
    client, _ = api
    # Without a real category there is nothing to propose into, and the
    # endpoint would return before calling the model at all.
    client.post("/api/categories", json={"name": "Groceries"})

    response = client.post("/api/llm-suggest")

    assert response.status_code == 502
    assert "unusably" in response.json()["detail"]


def fake_model(answer: dict):
    """A stand-in for the chat completion call: one request, one answer, counted."""
    calls: list[dict] = []

    class Reply:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(answer)}}]}

    def post(url, json=None, headers=None, timeout=None):
        calls.append(json)
        return Reply()

    return post, calls


def test_the_assistant_says_it_is_off_instead_of_failing(api, monkeypatch):
    from amonhen import api as api_module
    from amonhen.llm import LlmConfig

    monkeypatch.setattr(api_module, "llm_config", lambda: LlmConfig(url="", api_key="", model=""))
    client, _ = api

    response = client.post("/api/assistant/ask", json={"question": "Come va?"})

    assert response.status_code == 503
    assert "no LLM configured" in response.json()["detail"]
    assert client.get("/api/assistant").json()["configured"] is False


def test_the_assistant_answers_with_the_numbers_it_was_given(api, monkeypatch):
    import requests

    from amonhen import api as api_module
    from amonhen.llm import LlmConfig

    # A reading that quotes a figure the fixture really computes, and one that
    # quotes a figure nobody did: only the first is allowed through.
    post, calls = fake_model({"lettura": "Ad agosto sono entrati 1200,00."})
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(
        api_module,
        "llm_config",
        lambda: LlmConfig(url="https://llm.test/v1/chat/completions", api_key="k", model="m"),
    )
    client, _ = api

    first = client.post("/api/assistant/ask", json={"question": "Quanto e' entrato?"}).json()
    second = client.post("/api/assistant/ask", json={"question": "Quanto e' entrato?"}).json()

    assert first["answer"] == "Ad agosto sono entrati 1200,00."
    assert first["cached"] is False
    assert second["cached"] is True
    assert len(calls) == 1
    assert client.get("/api/assistant").json()["calls_today"] == 1
    assert client.get("/api/assistant/readings").json()[0]["model"] == "m"


def test_a_reading_that_invents_a_figure_is_refused_by_the_api(api, monkeypatch):
    import requests

    from amonhen import api as api_module
    from amonhen.llm import LlmConfig

    post, _ = fake_model({"lettura": "Hai speso 9876,54 in piu' del solito."})
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(
        api_module,
        "llm_config",
        lambda: LlmConfig(url="https://llm.test/v1/chat/completions", api_key="k", model="m"),
    )
    client, _ = api

    response = client.post("/api/assistant/ask", json={"question": "Come va?"})

    assert response.status_code == 502
    assert "cifre non calcolate" in response.json()["detail"]
    refused = client.get("/api/assistant/readings").json()[0]
    assert refused["refused"] is not None
    assert refused["answer"] == ""


def test_a_rule_reports_how_many_movements_it_holds(api):
    client, _ = api

    created = client.post("/api/rules", json={"pattern": "EKOM", "category": "Trasporti"})

    assert created.status_code == 201
    assert created.json()["count"] == 1
    assert client.get("/api/rules").json() == [
        {"pattern": "EKOM", "category": "Trasporti", "count": 1}
    ]


def test_a_rule_matches_a_fragment_of_the_description(api):
    """The pattern needs no merchant name: `cart` is enough for the row it appears in."""
    client, _ = api

    created = client.post("/api/rules", json={"pattern": "cart", "category": "Groceries"})

    assert created.json() == {"pattern": "cart", "category": "Groceries", "count": 1}
    movement = client.get("/api/transactions", params={"search": "ekom"}).json()["items"][0]
    assert movement["category"] == "Groceries"


def test_creating_a_rule_takes_its_movements_out_of_the_queue(api):
    client, _ = api

    client.post("/api/rules", json={"pattern": "Bar Centrale", "category": "Spesa"})

    queue = client.get("/api/review").json()
    assert [item["merchant"] for item in queue["uncategorized"]] == ["EKOM"]
    assert queue["uncategorized_total"] == 1


def test_editing_a_rule_moves_what_it_held(api):
    client, _ = api
    client.post("/api/rules", json={"pattern": "Bar Centrale", "category": "Spesa"})

    edited = client.post("/api/rules", json={"pattern": "Bar Centrale", "category": "Ristoranti"})

    assert edited.json()["count"] == 1
    assert client.get("/api/rules").json() == [
        {"pattern": "Bar Centrale", "category": "Ristoranti", "count": 1}
    ]
    movement = client.get("/api/transactions", params={"search": "Bar Centrale"}).json()["items"][0]
    assert movement["category"] == "Ristoranti"


def test_removing_a_rule_sends_its_movements_back_to_the_queue(api):
    client, _ = api
    client.post("/api/rules", json={"pattern": "Bar Centrale", "category": "Spesa"})

    removed = client.post("/api/rules/remove", json={"pattern": "Bar Centrale"})

    assert removed.status_code == 200
    assert removed.json()["held"] == 1
    assert client.get("/api/rules").json() == []
    queue = client.get("/api/review").json()
    assert {item["merchant"] for item in queue["uncategorized"]} == {"EKOM", "Bar Centrale"}
    assert client.post("/api/rules/remove", json={"pattern": "Bar Centrale"}).status_code == 404


def test_a_rule_needs_a_text_and_a_real_category(api):
    client, _ = api

    blank = client.post("/api/rules", json={"pattern": "   ", "category": "Spesa"})
    on_an_account = client.post("/api/rules", json={"pattern": "EKOM", "category": "Revolut"})

    assert blank.status_code == 422
    assert on_an_account.status_code == 422


def test_transactions_can_be_narrowed_to_the_transfer_legs(api):
    client, _ = api

    legs = client.get("/api/transactions", params={"transfer": "true"}).json()
    rest = client.get("/api/transactions", params={"transfer": "false"}).json()
    everything = client.get("/api/transactions").json()

    assert legs["total"] == 2
    assert {item["transfer"]["target"] for item in legs["items"]} == {"Revolut", "Fineco"}
    assert rest["total"] == everything["total"] - 2
    assert all(item["transfer"] is None for item in rest["items"])


def test_the_api_says_what_a_leg_is_attached_to(api):
    client, _ = api

    legs = client.get("/api/transactions", params={"transfer": "true"}).json()["items"]
    out = next(item for item in legs if item["amount"] == "-840.00")
    back = next(item for item in legs if item["amount"] == "840.00")

    # Without this the app can only show a row with no category, which is what a
    # movement nobody has decided about looks like too.
    assert out["transfer"] == {
        "kind": "pair",
        "target": "Fineco",
        "state": "proposed",
        "leg_id": back["id"],
    }
    assert out["category"] is None
    # The clearing account is an implementation detail and never leaves the ledger.
    assert "clearing" not in json.dumps(out["transfer"]).casefold()


def test_recording_a_leg_into_a_declared_destination_takes_it_out_of_income(api):
    client, _ = api
    salary = client.get("/api/transactions", params={"search": "Stipendio"}).json()["items"][0]
    month = "2026-08"

    def income() -> Decimal:
        months = client.get("/api/flows").json()["months"]
        return Decimal(next(flow["income"] for flow in months if flow["month"] == month))

    assert income() == Decimal("1200.00")

    response = client.post(
        "/api/transfers/passthrough",
        json={"transaction_id": salary["id"], "destination": "Conto stipendio"},
    )

    assert response.status_code == 200
    assert response.json()["transfer"] == {
        "kind": "passthrough",
        "target": "Conto stipendio",
        "state": "confirmed",
        "leg_id": None,
    }
    # The chart and the ledger agree: money moved from a count of your own is not
    # money earned.
    assert income() == Decimal("0.00")


def test_pairing_two_legs_from_the_api_is_a_decision_already_taken(api):
    client, _ = api
    legs = client.get("/api/transactions", params={"transfer": "true"}).json()["items"]
    out = next(item for item in legs if item["amount"] == "-840.00")
    back = next(item for item in legs if item["amount"] == "840.00")
    client.post("/api/transfers/unlink", json={"transaction_id": out["id"]})

    response = client.post("/api/transfers/pair", json={"leg_a": out["id"], "leg_b": back["id"]})

    assert response.status_code == 200
    assert response.json()["transfer"] == {
        "kind": "pair",
        "target": "Fineco",
        "state": "confirmed",
        "leg_id": back["id"],
    }
    assert client.get("/api/transactions", params={"transfer": "false"}).json()["total"] == 4


def test_the_api_refuses_a_pairing_the_ledger_refuses(api):
    client, _ = api
    smaller = client.get("/api/transactions", params={"search": "EKOM"}).json()["items"][0]
    legs = client.get("/api/transactions", params={"transfer": "true"}).json()["items"]
    out = next(item for item in legs if item["amount"] == "-840.00")
    back = next(item for item in legs if item["amount"] == "840.00")
    client.post("/api/transfers/unlink", json={"transaction_id": out["id"]})

    response = client.post("/api/transfers/pair", json={"leg_a": smaller["id"], "leg_b": back["id"]})

    # Two amounts that do not cancel are not two halves of one movement.
    assert response.status_code == 422
    assert "equal and opposite" in response.json()["detail"]
    assert client.get("/api/transactions", params={"transfer": "true"}).json()["total"] == 0


def test_unlinking_says_when_the_configuration_would_put_the_leg_back(tmp_path):
    """Unlinking a label a sync re-applies is a promise the app must not make."""
    config = tmp_path / "accounts.json"
    config.write_text(
        json.dumps(
            {
                "application_id": "app-1",
                "pem_path": "private.pem",
                "redirect_url": "http://localhost:8000/callback",
                "account_holder_name": "Tester",
                "passthrough": [{"destination": "Conto deposito senza vincoli", "labels": ["Conto deposito senza vincoli"]}],
                "accounts": [],
            }
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "ledger.db"
    client = TestClient(create_app(db_path, web_dist=tmp_path / "missing", config_path=config))
    conn = connect(db_path)
    ledger = Ledger(conn)
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    declared = ledger.record(
        make_txn(ledger, revolut, "2026-08-03", "-500.00", "To Conto deposito senza vincoli")
    )[0]
    chosen = ledger.record(make_txn(ledger, revolut, "2026-08-04", "-200.00", "Bonifico"))[0]
    conn.close()

    assert client.get("/api/transfers/labels").json() == {
        "configured": ["Conto deposito senza vincoli"],
        "recorded": [],
    }
    client.post(
        "/api/transfers/passthrough",
        json={"transaction_id": declared, "destination": "Conto deposito senza vincoli"},
    )
    client.post(
        "/api/transfers/passthrough",
        json={"transaction_id": chosen, "destination": "Conto stipendio"},
    )
    assert client.get("/api/transfers/labels").json() == {
        "configured": ["Conto deposito senza vincoli"],
        "recorded": ["Conto deposito senza vincoli", "Conto stipendio"],
    }

    declared_back = client.post("/api/transfers/unlink", json={"transaction_id": declared}).json()
    chosen_back = client.post("/api/transfers/unlink", json={"transaction_id": chosen}).json()

    assert declared_back["released"] == "Conto deposito senza vincoli"
    assert declared_back["configured"] is True
    assert chosen_back["released"] == "Conto stipendio"
    assert chosen_back["configured"] is False
    assert chosen_back["transaction"]["transfer"] is None
    client.close()


def test_the_metrics_follow_the_accounts_they_are_given(api):
    client, _ = api

    both = client.get("/api/metrics").json()
    only_revolut = client.get("/api/metrics", params={"accounts": "Revolut"}).json()

    # Liquidity is what the tracked accounts are worth: one of them cannot be
    # worth both, and the response says what it applied.
    assert Decimal(both["liquidity"]) == Decimal("1144.60")
    assert Decimal(only_revolut["liquidity"]) == Decimal("304.60")
    assert only_revolut["applied"]["accounts"] == ["Revolut"]


def test_the_category_filter_moves_the_spending_and_not_the_liquidity(api):
    client, _ = api

    unfiltered = client.get("/api/metrics").json()
    nothing_in_it = client.get("/api/metrics", params={"categories": "Vacanze"}).json()

    assert nothing_in_it["recurring_burn"] is None
    assert Decimal(nothing_in_it["liquidity"]) == Decimal(unfiltered["liquidity"])
    assert nothing_in_it["applied"]["categories"] == ["Vacanze"]


def test_the_pie_says_which_period_and_accounts_it_drew(api):
    client, _ = api

    payload = client.get(
        "/api/spending",
        params={"from": "2026-08-01", "to": "2026-08-31", "accounts": "Fineco"},
    ).json()

    # Fineco paid nothing in the fixture: an empty pie, not a missing one.
    assert payload["categories"] == []
    assert payload["total"] == "0.00"
    assert payload["applied"] == {
        "accounts": ["Fineco"],
        "categories": [],
        "from": "2026-08-01",
        "to": "2026-08-31",
    }


def test_a_period_that_ends_before_it_starts_is_refused(api):
    client, _ = api

    response = client.get("/api/spending", params={"from": "2026-09-01", "to": "2026-08-01"})

    assert response.status_code == 422


def test_an_account_can_be_added_by_hand(api):
    client, _ = api

    created = client.post(
        "/api/accounts",
        json={
            "name": "Fondo pensione",
            "institution": "Amundi",
            "opening_balance": "12000.00",
            "opening_date": "2026-01-01",
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["name"] == "Fondo pensione"
    assert Decimal(payload["balance"]) == Decimal("12000.00")
    assert payload["verification"]["state"] == "unverified"
    assert "Fondo pensione" in {a["name"] for a in client.get("/api/accounts").json()}

    # The same name twice would silently hand back the first account, so it is
    # refused; an opening balance without a date is refused too.
    assert client.post("/api/accounts", json={"name": "Fondo pensione"}).status_code == 422
    assert (
        client.post(
            "/api/accounts", json={"name": "Contanti", "opening_balance": "50.00"}
        ).status_code
        == 422
    )


def test_declaring_a_balance_from_the_app_makes_the_account_say_whether_it_agrees(api):
    client, _ = api

    revolut = next(a for a in client.get("/api/accounts").json() if a["name"] == "Revolut")
    assert revolut["verification"]["state"] == "unverified"

    wrong = client.put(
        f"/api/accounts/{revolut['id']}/declaration",
        json={"date": "2026-09-12", "balance": "999.00", "kind": "available"},
    ).json()
    assert wrong["verification"]["state"] == "mismatch"

    right = client.put(
        f"/api/accounts/{revolut['id']}/declaration",
        json={"date": "2026-09-12", "balance": revolut["balance"], "kind": "available"},
    ).json()

    assert right["verification"]["state"] == "verified"
    assert right["verification"]["checks"][0]["kind"] == "available"
    assert right["verification"]["checks"][0]["difference"] == "0.00"


def test_anchoring_from_a_declaration_makes_the_invariant_hold_by_construction(api):
    client, _ = api

    revolut = next(a for a in client.get("/api/accounts").json() if a["name"] == "Revolut")
    anchored = client.put(
        f"/api/accounts/{revolut['id']}/opening",
        json={"date": "2026-09-12", "balance": "304.60", "kind": "available"},
    ).json()

    # The opening was solved from the declared figure, so the two now agree and
    # the opening is dated the day before the account's first movement.
    assert anchored["verification"]["state"] == "verified"
    assert anchored["opening_balance"] == "0.00"
    assert anchored["opening_date"] == "2026-08-02"
