"""Desiderata 5.7 anomalies, with hand-derived values."""
import datetime as dt
from decimal import Decimal

from amonhen.anomalies import detect_anomalies
from amonhen.models import Account, IncomingTransaction

TODAY = dt.date(2026, 9, 12)

# Ten settled months of history for one category. Sorted, they are
# 90,95,95,100,100,100,100,105,105,110: median 100, MAD 5.
HISTORY_DATES = (
    "2025-10-10", "2025-11-10", "2025-12-10", "2026-01-10", "2026-02-10",
    "2026-03-10", "2026-04-10", "2026-05-10", "2026-06-10", "2026-07-10",
)
HISTORY_AMOUNTS = ("-90", "-95", "-100", "-105", "-110", "-100", "-100", "-95", "-105", "-100")


def record(ledger, account_id, balancing_id, date, amount, description, status="BOOK"):
    transaction_id, _ = ledger.record(
        IncomingTransaction(
            account_id=account_id,
            date=dt.date.fromisoformat(date),
            amount=Decimal(amount),
            description=description,
            status=status,
            source="import",
            balancing_account_id=balancing_id,
        )
    )
    return transaction_id


def spend(ledger, account_id, category_id, date, amount, description="spend", status="BOOK"):
    return record(ledger, account_id, category_id, date, amount, description, status)


def build_history(ledger, account, category):
    for date, amount in zip(HISTORY_DATES, HISTORY_AMOUNTS):
        spend(ledger, account, category, date, amount)


def test_an_outlier_in_a_category_with_a_spread_is_flagged_with_the_expected_score(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    build_history(ledger, account, groceries)
    outlier = spend(ledger, account, groceries, "2026-09-01", "-500")

    anomalies = detect_anomalies(ledger, TODAY)

    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly.transaction_id == outlier
    assert anomaly.date == dt.date(2026, 9, 1)
    assert anomaly.category == "Groceries"
    assert anomaly.method == "mad"
    assert anomaly.amount == Decimal("500")
    assert anomaly.median == Decimal("100")
    assert anomaly.mad == Decimal("5")
    # 0.6745 * (500 - 100) / 5
    assert anomaly.score == Decimal("53.96")


def test_a_normal_amount_in_the_same_category_is_not_flagged(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    build_history(ledger, account, groceries)
    spend(ledger, account, groceries, "2026-09-02", "-105")

    assert detect_anomalies(ledger, TODAY) == []


def test_a_category_with_too_little_history_is_not_examined(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    for date in ("2026-04-10", "2026-05-10", "2026-06-10", "2026-07-10", "2026-08-10"):
        spend(ledger, account, groceries, date, "-100")
    spend(ledger, account, groceries, "2026-09-01", "-5000")

    assert detect_anomalies(ledger, TODAY) == []


def test_a_constant_category_falls_back_to_its_p95(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    # Twelve identical months make the MAD zero: the p95 stays at the amount.
    for index in range(12):
        day = dt.date(2025, 9, 15) + dt.timedelta(days=28 * index)
        spend(ledger, account, groceries, day.isoformat(), "-100")
    spend(ledger, account, groceries, "2026-09-01", "-100")
    spike = spend(ledger, account, groceries, "2026-09-02", "-200")

    anomalies = detect_anomalies(ledger, TODAY)

    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly.transaction_id == spike
    assert anomaly.method == "p95"
    assert anomaly.median == Decimal("100")
    assert anomaly.mad == Decimal("0")
    assert anomaly.amount == Decimal("200")
    assert anomaly.score == Decimal("100")


def test_income_pending_and_transfer_rows_are_never_flagged(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    other = ledger.ensure_account(Account(name="Fineco", type="real"))
    groceries = ledger.category("Groceries")
    build_history(ledger, account, groceries)

    # Incoming money is not spending even when it lands on a category.
    spend(ledger, account, groceries, "2026-09-01", "5000", "salary")
    # A movement the bank has not settled yet is not judged.
    spend(ledger, account, groceries, "2026-09-02", "-5000", "pending splurge", status="PDNG")
    # A transfer leg is balanced by the clearing account, so it has no category.
    spend(ledger, account, ledger.transfer_account(), "2026-09-03", "-8000", "Bonifico")
    spend(ledger, other, ledger.transfer_account(), "2026-09-03", "8000", "Bonifico")

    assert detect_anomalies(ledger, TODAY) == []


def test_the_sentence_names_the_category_the_amount_the_merchant_and_the_median(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    build_history(ledger, account, groceries)
    spend(ledger, account, groceries, "2026-09-01", "-500", "Amazon Marketplace")

    sentence = detect_anomalies(ledger, TODAY)[0].sentence

    assert "Groceries" in sentence
    assert "500" in sentence
    assert "Amazon Marketplace" in sentence
    assert "mediana 100.00" in sentence


def test_detection_is_deterministic_and_a_higher_threshold_flags_no_more(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    build_history(ledger, account, groceries)
    spend(ledger, account, groceries, "2026-09-03", "-110")
    spend(ledger, account, groceries, "2026-09-04", "-120")
    spend(ledger, account, groceries, "2026-09-05", "-500")

    first = detect_anomalies(ledger, TODAY)
    second = detect_anomalies(ledger, TODAY)
    assert first == second

    low = detect_anomalies(ledger, TODAY, z_threshold=Decimal("1"))
    high = detect_anomalies(ledger, TODAY, z_threshold=Decimal("10"))
    low_ids = {(anomaly.transaction_id, anomaly.date) for anomaly in low}
    high_ids = {(anomaly.transaction_id, anomaly.date) for anomaly in high}
    assert high_ids <= low_ids
    assert len(high) <= len(low)
