"""Desiderata 5.13: a tag is a label on a movement, and a flag on it counts."""
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from amonhen.anomalies import MIN_AMOUNT, detect_anomalies
from amonhen.api import create_app
from amonhen.db import open_ledger_db
from amonhen.ledger import Ledger
from amonhen.merchants import RuleBook, categorize, rule_usage
from amonhen.metrics import LedgerScope, compute_metrics, month_reading, spend_by_category
from amonhen.models import Account, IncomingTransaction

MINIMAL_CONFIG = Path(__file__).resolve().parent / "fixtures" / "config" / "minimal.json"
TODAY = dt.date(2026, 9, 12)
MONTHS = ("2026-03-10", "2026-04-10", "2026-05-10", "2026-06-10", "2026-07-10", "2026-08-10")


def spend(ledger, account_id, category_id, date, amount, description="spend"):
    return ledger.record(
        IncomingTransaction(
            account_id=account_id,
            date=dt.date.fromisoformat(date),
            amount=Decimal(amount),
            description=description,
            status="BOOK",
            source="import",
            balancing_account_id=category_id,
        )
    )[0]


@pytest.fixture
def account(ledger):
    return ledger.ensure_account(Account(name="Revolut", type="real"))


def test_a_rare_tag_counts_like_a_rare_category(ledger, account):
    casa = ledger.category("Casa")
    for date in MONTHS:
        spend(ledger, account, casa, date, "-100", f"spesa {date}")
    fridge = spend(ledger, account, casa, "2026-08-11", "-2400", "Euronics")
    assert compute_metrics(ledger, TODAY).episodic_accrual == Decimal(0)

    rare = ledger.tag("Spesa rara")
    ledger.set_tag_flag(rare, "episodic", True)
    ledger.add_tag(fridge, "Spesa rara")

    metrics = compute_metrics(ledger, TODAY)
    assert metrics.recurring_burn == Decimal("100")
    assert metrics.episodic_accrual == Decimal("100")
    assert metrics.expected_burn == Decimal("200")


def test_a_movement_rare_and_essential_counts_as_rare_once(ledger, account):
    bills = ledger.category("Bollette")
    ledger.set_category_flag(bills, "essential", True)
    for date in MONTHS:
        spend(ledger, account, bills, date, "-50", f"luce {date}")
    big = spend(ledger, account, bills, "2026-08-11", "-240", "conguaglio")
    ledger.set_tag_flag(ledger.tag("Rara"), "episodic", True)
    ledger.add_tag(big, "Rara")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.essential_monthly == Decimal("50")
    assert metrics.episodic_accrual == Decimal("10")


def test_an_essential_tag_moves_spending_out_of_the_cuttable_part(ledger, account):
    other = ledger.category("Altro")
    tag = ledger.tag("Mutuo")
    ledger.set_tag_flag(tag, "essential", True)
    for date in MONTHS:
        ledger.add_tag(spend(ledger, account, other, date, "-300", f"rata {date}"), "Mutuo")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.essential_monthly == Decimal("300")
    assert metrics.discretionary_monthly is None


def test_a_tag_narrows_the_spending_alone(ledger, account):
    casa = ledger.category("Casa")
    spend(ledger, account, casa, "2026-08-11", "-500", "Euronics")
    tagged = spend(ledger, account, casa, "2026-08-12", "-300", "Unieuro")
    ledger.add_tag(tagged, "Elettrodomestici")

    slices = spend_by_category(
        ledger, dt.date(2026, 8, 1), dt.date(2026, 8, 31), LedgerScope(tags=("Elettrodomestici",))
    )

    assert [(item.category, item.amount) for item in slices] == [("Casa", Decimal("300"))]


def test_a_tag_rule_adds_to_a_category_rule_on_the_same_text(ledger, account):
    uncategorized = ledger.uncategorized()
    movement = spend(ledger, account, uncategorized, "2026-08-11", "-500", "EURONICS 123")
    small = spend(ledger, account, uncategorized, "2026-08-12", "-20", "EURONICS 124")
    book = RuleBook(ledger.conn)

    book.set_rule("euronics", "Casa", ledger)
    book.set_rule("euronics", "Spesa rara", ledger, action="tag", amount_min=Decimal("150"))
    book.set_rule("euronics", "Elettrodomestici", ledger, action="tag")

    assert ledger.category_of(movement) == "Casa"
    assert ledger.tags_of(movement) == ["Elettrodomestici", "Spesa rara"]
    assert ledger.tags_of(small) == ["Elettrodomestici"]
    rules = book.rules()
    usage = rule_usage(ledger, rules)
    assert sorted(usage[rule.id] for rule in rules if rule.action == "tag") == [1, 2]


def test_removing_a_rule_takes_its_tag_and_leaves_a_persons(ledger, account):
    uncategorized = ledger.uncategorized()
    movement = spend(ledger, account, uncategorized, "2026-08-11", "-500", "Euronics")
    book = RuleBook(ledger.conn)
    book.set_rule("euronics", "Dalla regola", ledger, action="tag")
    ledger.add_tag(movement, "A mano")
    assert ledger.tags_of(movement) == ["A mano", "Dalla regola"]

    book.remove(book.rules()[0].id, ledger)

    assert ledger.tags_of(movement) == ["A mano"]


def test_a_sync_tags_the_new_movements(ledger, account):
    book = RuleBook(ledger.conn)
    book.set_rule("euronics", "Elettrodomestici", ledger, action="tag")
    movement = spend(ledger, account, ledger.uncategorized(), "2026-08-11", "-50", "Euronics")

    categorize(ledger, book)

    assert ledger.tags_of(movement) == ["Elettrodomestici"]


def test_a_tag_a_person_wrote_comes_back_with_the_movement(ledger, account):
    movement = spend(ledger, account, ledger.uncategorized(), "2026-08-11", "-50", "Euronics")
    ledger.add_tag(movement, "Elettrodomestici")

    ledger.delete_transaction(movement)
    tombstone = ledger.deleted_transactions()[0]
    restored = ledger.restore_deleted(tombstone["id"])

    assert ledger.tags_of(restored) == ["Elettrodomestici"]


def test_deleting_a_tag_takes_its_rules(ledger, account):
    movement = spend(ledger, account, ledger.uncategorized(), "2026-08-11", "-50", "Euronics")
    book = RuleBook(ledger.conn)
    book.set_rule("euronics", "Elettrodomestici", ledger, action="tag")

    ledger.delete_tag(ledger.tag("Elettrodomestici"))

    assert ledger.tags_of(movement) == []
    assert book.rules() == []


def test_a_rare_movement_is_not_an_anomaly(ledger, account):
    casa = ledger.category("Casa")
    for index in range(10):
        spend(ledger, account, casa, f"2026-0{1 + index % 7}-0{1 + index % 9}", "-100", f"s{index}")
    fridge = spend(ledger, account, casa, "2026-09-01", "-900", "Euronics")
    assert len(detect_anomalies(ledger, TODAY, min_amount=MIN_AMOUNT)) == 1

    ledger.set_tag_flag(ledger.tag("Rara"), "episodic", True)
    ledger.add_tag(fridge, "Rara")

    assert detect_anomalies(ledger, TODAY, min_amount=MIN_AMOUNT) == []


def test_the_month_is_read_against_the_same_point_of_the_months_before(ledger, account):
    food = ledger.category("Alimentari")
    for date in MONTHS:
        spend(ledger, account, food, date, "-100", f"inizio {date}")
        spend(ledger, account, food, date[:8] + "25", "-900", f"fine {date}")
    spend(ledger, account, food, "2026-09-05", "-150", "questo mese")

    reading = month_reading(ledger, TODAY)

    assert reading.spent == Decimal("150")
    assert reading.usual == Decimal("100")
    assert reading.months_compared == 6
    assert [(item.category, item.spent, item.usual) for item in reading.categories] == [
        ("Alimentari", Decimal("150"), Decimal("100"))
    ]


def test_rare_spending_has_a_line_of_its_own_in_the_month(ledger, account):
    travel = ledger.category("Viaggi")
    ledger.set_category_flag(travel, "episodic", True)
    food = ledger.category("Alimentari")
    spend(ledger, account, travel, "2026-09-02", "-4000", "volo")
    spend(ledger, account, food, "2026-09-03", "-40", "spesa")

    reading = month_reading(ledger, TODAY)

    assert reading.spent == Decimal("40")
    assert reading.rare == Decimal("4000")
    assert reading.usual is None
    assert [item.category for item in reading.categories] == ["Alimentari"]


def test_the_category_furthest_from_its_usual_comes_first(ledger, account):
    food = ledger.category("Alimentari")
    fun = ledger.category("Svago")
    for date in MONTHS:
        spend(ledger, account, food, date, "-500", f"a {date}")
        spend(ledger, account, fun, date, "-10", f"b {date}")
    spend(ledger, account, food, "2026-09-05", "-490", "a")
    spend(ledger, account, fun, "2026-09-06", "-200", "b")

    reading = month_reading(ledger, TODAY)

    assert [item.category for item in reading.categories] == ["Svago", "Alimentari"]


def test_a_shorter_month_is_cut_at_its_last_day(ledger, account):
    food = ledger.category("Alimentari")
    spend(ledger, account, food, "2026-02-28", "-70", "febbraio")

    reading = month_reading(ledger, dt.date(2026, 3, 31))

    assert reading.usual == Decimal("70")


@pytest.fixture
def api(tmp_path):
    db_path = tmp_path / "ledger.db"
    conn = open_ledger_db(db_path)
    ledger = Ledger(conn)
    bank = ledger.ensure_account(Account(name="Banca", type="real"))
    deposit = ledger.ensure_account(Account(name="Deposito", type="real"))
    ledger.set_computed_balance(deposit, True)
    casa = ledger.category("Casa")
    today = dt.date.today().isoformat()
    spend(ledger, bank, casa, today, "-500", "Euronics")
    spend(ledger, bank, ledger.uncategorized(), today, "-20", "Bar")
    # What only moves own money: a transfer out, and the deposit's interest.
    moved = spend(ledger, bank, ledger.uncategorized(), today, "-100", "Al deposito")
    ledger.move_to_virtual_account(moved, "Altro conto")
    spend(ledger, deposit, ledger.uncategorized(), today, "0.05", "Interessi")
    conn.close()
    client = TestClient(create_app(db_path, web_dist=tmp_path / "missing", config_path=MINIMAL_CONFIG))
    yield client
    client.close()


def euronics(api):
    items = api.get("/api/transactions").json()["items"]
    return next(item for item in items if item["description"] == "Euronics")


def test_the_everyday_list_says_how_many_it_left_out(api):
    every = api.get("/api/transactions").json()
    everyday = api.get("/api/transactions", params={"everyday": "true"}).json()

    assert (every["total"], every["hidden"]) == (4, 0)
    assert (everyday["total"], everyday["hidden"]) == (2, 2)
    assert {item["description"] for item in everyday["items"]} == {"Euronics", "Bar"}


def test_a_tag_is_written_and_narrows_the_list(api):
    movement = euronics(api)

    written = api.put(f"/api/transactions/{movement['id']}/tags", json={"tags": ["Casa nuova"]})

    assert written.json()["tags"] == ["Casa nuova"]
    page = api.get("/api/transactions", params={"tag": "Casa nuova"}).json()
    assert [item["id"] for item in page["items"]] == [movement["id"]]
    [tag] = api.get("/api/tags").json()
    assert (tag["name"], tag["movements"], tag["episodic"]) == ("Casa nuova", 1, False)


def test_a_missing_id_refuses_the_whole_batch(api):
    ids = [item["id"] for item in api.get("/api/transactions").json()["items"]]

    assert api.post("/api/transactions/tag", json={"ids": ids + [999999], "tag": "T"}).status_code == 404
    assert api.get("/api/tags").json() == []
    assert api.post("/api/transactions/tag", json={"ids": ids[:2], "tag": "T"}).json() == {"tagged": 2}


def test_a_tag_flag_moves_the_month(api):
    assert api.get("/api/month").json()["spent"] == "520.00"
    api.put(f"/api/transactions/{euronics(api)['id']}/tags", json={"tags": ["Rara"]})
    [tag] = api.get("/api/tags").json()

    api.patch(f"/api/tags/{tag['id']}", json={"episodic": True})

    month = api.get("/api/month").json()
    assert (month["spent"], month["rare"]) == ("20.00", "500.00")
    assert api.delete(f"/api/tags/{tag['id']}").status_code == 200
    assert api.get("/api/month").json()["spent"] == "520.00"
