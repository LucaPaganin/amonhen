"""Desiderata 5.6 metrics, with hand-derived expected values."""
import datetime as dt
from decimal import Decimal

from amonhen.metrics import (
    LedgerScope,
    compute_metrics,
    latest_balances,
    monthly_flows,
    net_worth_series,
    spend_by_category,
)
from amonhen.models import Account, IncomingTransaction
from amonhen.config import Passthrough
from amonhen.transfers import link_passthrough_legs, link_transfers

TODAY = dt.date(2026, 9, 12)
# The last complete month is 2026-08; the six-month window is 2026-03..2026-08.
MONTHS = ("2026-03-10", "2026-04-10", "2026-05-10", "2026-06-10", "2026-07-10", "2026-08-10")


def record(ledger, account_id, balancing_id, date, amount, description):
    return ledger.record(
        IncomingTransaction(
            account_id=account_id,
            date=dt.date.fromisoformat(date),
            amount=Decimal(amount),
            description=description,
            status="BOOK",
            source="import",
            balancing_account_id=balancing_id,
        )
    )


def spend(ledger, account_id, category_id, date, amount):
    record(ledger, account_id, category_id, date, amount, "spend")


def transfer(ledger, source_id, destination_id, date, amount):
    value = Decimal(amount)
    clearing = ledger.transfer_account()
    record(ledger, source_id, clearing, date, -value, "transfer out")
    record(ledger, destination_id, clearing, date, value, "transfer in")


def test_recurring_burn_median_ignores_the_outlier_month(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    for date, amount in zip(MONTHS, ("-100", "-100", "-100", "-100", "-100", "-1000")):
        spend(ledger, account, groceries, date, amount)

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.recurring_burn == Decimal("100")
    assert metrics.months_of_history == 6
    assert metrics.partial is False
    assert metrics.episodic_partial is True


def test_median_of_an_even_count_of_months_averages_the_two_middle_values(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    for date, amount in zip(MONTHS, ("-100", "-200", "-300", "-400", "-500", "-600")):
        spend(ledger, account, groceries, date, amount)

    metrics = compute_metrics(ledger, TODAY)

    # Sorted totals 100, 200, 300, 400, 500, 600 -> (300 + 400) / 2.
    assert metrics.recurring_burn == Decimal("350")


def test_episodic_payment_feeds_the_accrual_not_the_recurring_burn(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    medical = ledger.category("Medical")
    ledger.set_category_flag(medical, "episodic", True)
    for date in MONTHS:
        spend(ledger, account, groceries, date, "-100")
    spend(ledger, account, medical, "2026-08-15", "-2400")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.recurring_burn == Decimal("100")
    assert metrics.episodic_accrual == Decimal("2400") / 24
    assert metrics.episodic_accrual == Decimal("100")
    assert metrics.expected_burn == Decimal("200")
    # The one-off is episodic, so it is neither essential nor discretionary.
    assert metrics.essential_monthly is None
    assert metrics.discretionary_monthly == Decimal("100")


def test_essential_and_discretionary_split_non_episodic_spending(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    rent = ledger.category("Rent")
    fun = ledger.category("Fun")
    ledger.set_category_flag(rent, "essential", True)
    for date in MONTHS:
        spend(ledger, account, rent, date, "-800")
        spend(ledger, account, fun, date, "-200")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.essential_monthly == Decimal("800")
    assert metrics.discretionary_monthly == Decimal("200")
    assert metrics.recurring_burn == Decimal("1000")


def test_short_history_reports_metrics_with_partial_flags(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    for date, amount in zip(MONTHS[3:], ("-100", "-200", "-300")):
        spend(ledger, account, groceries, date, amount)

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.months_of_history == 3
    assert metrics.partial is True
    assert metrics.episodic_partial is True
    # Median over the three observed months, not padded with pre-history zeros.
    assert metrics.recurring_burn == Decimal("200")
    assert metrics.expected_burn == Decimal("200")
    assert metrics.liquidity == Decimal("-600")  # 100 + 200 + 300 spent


def test_runway_is_liquidity_over_the_expected_burn(ledger):
    account = ledger.ensure_account(
        Account(
            name="Revolut",
            type="real",
            opening_balance=Decimal("2000"),
            opening_date=dt.date(2026, 3, 1),
        )
    )
    groceries = ledger.category("Groceries")
    for date in MONTHS:
        spend(ledger, account, groceries, date, "-100")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.liquidity == Decimal("1400")  # 2000 opening - 600 spent
    assert metrics.expected_burn == Decimal("100")
    assert metrics.runway_months == Decimal("1400") / Decimal("100")
    assert metrics.runway_months == Decimal("14")


def test_runway_is_none_when_the_denominator_is_zero(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    broker = ledger.ensure_account(Account(name="Broker", type="real"))
    transfer(ledger, account, broker, "2026-08-05", "500")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.recurring_burn is None
    assert metrics.expected_burn == Decimal("0")
    assert metrics.runway_months is None


def test_savings_flow_counts_investment_postings_and_not_as_spending(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    broker = ledger.ensure_account(Account(name="Broker", type="real"))
    ledger.set_investment(broker, True)
    groceries = ledger.category("Groceries")
    for date in MONTHS:
        spend(ledger, account, groceries, date, "-100")
    transfer(ledger, account, broker, "2026-08-05", "1000")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.savings_flow == Decimal("1000")
    # The transfer balances through the virtual clearing account, not a category.
    assert metrics.recurring_burn == Decimal("100")


def test_empty_ledger_returns_missing_money_metrics_without_raising(ledger):
    metrics = compute_metrics(ledger, TODAY)

    assert metrics.months_of_history == 0
    assert metrics.partial is True
    assert metrics.episodic_partial is True
    assert metrics.recurring_burn is None
    assert metrics.episodic_accrual is None
    assert metrics.expected_burn is None
    assert metrics.essential_monthly is None
    assert metrics.discretionary_monthly is None
    assert metrics.savings_flow is None
    assert metrics.runway_months is None
    assert metrics.liquidity == Decimal("0")
    assert metrics.period_start == dt.date(2026, 3, 1)
    assert metrics.period_end == dt.date(2026, 8, 31)


def test_incoming_money_does_not_net_against_spending(ledger):
    """A salary month is still a spending month: burn is what left the accounts."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    for date in MONTHS:
        spend(ledger, account, groceries, date, "-100")
        record(ledger, account, groceries, date, "2000", "salary")

    metrics = compute_metrics(ledger, TODAY)

    assert metrics.recurring_burn == Decimal("100")
    assert metrics.essential_monthly is None
    assert metrics.discretionary_monthly == Decimal("100")


# -- dashboard series ------------------------------------------------------
#
# Each series is asserted against a hand-derived number, and the category pie
# is tied to spend_between so the chart and the burn cannot drift apart.

def test_spend_by_category_ranks_the_slices_and_sums_to_the_month_spend(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    transport = ledger.category("Transport")
    spend(ledger, account, groceries, "2026-08-03", "-40.00")
    spend(ledger, account, groceries, "2026-08-20", "-10.50")
    spend(ledger, account, transport, "2026-08-05", "-25.00")

    slices = spend_by_category(ledger, dt.date(2026, 8, 1), dt.date(2026, 8, 31))

    assert [(item.category, item.amount) for item in slices] == [
        ("Groceries", Decimal("50.50")),
        ("Transport", Decimal("25.00")),
    ]
    assert sum(item.amount for item in slices) == ledger.spend_between(
        dt.date(2026, 8, 1), dt.date(2026, 8, 31)
    )


def test_spend_by_category_shows_uncategorized_money_and_ignores_pending_and_transfers(ledger):
    """Hiding uncategorized spending would make the pie smaller than reality."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    broker = ledger.ensure_account(Account(name="Broker", type="real"))
    spend(ledger, account, ledger.uncategorized(), "2026-08-07", "-5.00")
    record(ledger, account, ledger.uncategorized(), "2026-08-08", "-99.00", "pending")
    ledger.conn.execute("UPDATE transactions SET status = 'PDNG' WHERE description = 'pending'")
    transfer(ledger, account, broker, "2026-08-09", "500")

    slices = spend_by_category(ledger, dt.date(2026, 8, 1), dt.date(2026, 8, 31))

    assert [(item.category, item.amount) for item in slices] == [("Uncategorized", Decimal("5.00"))]


def test_monthly_flows_pair_income_and_spending_and_leave_transfers_out(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    broker = ledger.ensure_account(Account(name="Broker", type="real"))
    groceries = ledger.category("Groceries")
    spend(ledger, account, groceries, "2026-07-03", "-60.00")
    spend(ledger, account, groceries, "2026-08-03", "-40.00")
    record(ledger, account, ledger.uncategorized(), "2026-08-05", "1200.00", "salary")
    transfer(ledger, account, broker, "2026-08-06", "500")
    # Production links the legs during the sync; income excludes them by that link.
    link_transfers(ledger)

    flows = monthly_flows(ledger, dt.date(2026, 7, 1), TODAY)

    assert [flow.month for flow in flows] == ["2026-07", "2026-08", "2026-09"]
    assert [(flow.income, flow.expenses) for flow in flows] == [
        (Decimal("0"), Decimal("60.00")),
        (Decimal("1200.00"), Decimal("40.00")),
        (Decimal("0"), Decimal("0")),
    ]
    # Moving money to your own broker is not income, and the month still running
    # is flagged so a short bar is not read as a cheap month.
    assert [flow.partial for flow in flows] == [False, False, True]


def test_monthly_flows_do_not_count_money_arriving_from_an_own_account(ledger):
    """A purchase funded from the deposit is spending; the arrival is not income."""
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    spend(ledger, account, groceries, "2026-08-03", "-40.00")
    record(ledger, account, ledger.uncategorized(), "2026-08-04", "40.00", "From Conto deposito")
    link_passthrough_legs(
        ledger, (Passthrough(destination="Conto deposito", labels=("Conto deposito",)),)
    )

    flows = monthly_flows(ledger, dt.date(2026, 8, 1), TODAY)

    assert [(flow.income, flow.expenses) for flow in flows] == [
        (Decimal("0"), Decimal("40.00")),
        (Decimal("0"), Decimal("0")),
    ]


def test_monthly_flows_do_not_count_a_declared_contribution_as_income(ledger):
    """The co-holder's share funds the joint account's spending; it is not income."""
    account = ledger.ensure_account(Account(name="Revolut cointestato", type="real"))
    groceries = ledger.category("Groceries")
    spend(ledger, account, groceries, "2026-08-03", "-300.00")
    record(ledger, account, ledger.uncategorized(), "2026-08-04", "300.00", "From Chiara B")
    link_passthrough_legs(
        ledger,
        (Passthrough(destination="Rimborsi e quote", labels=("Chiara",), incoming_only=True),),
    )

    flows = monthly_flows(ledger, dt.date(2026, 8, 1), TODAY)

    assert [(flow.income, flow.expenses) for flow in flows] == [
        (Decimal("0"), Decimal("300.00")),
        (Decimal("0"), Decimal("0")),
    ]


def test_monthly_flows_do_not_chart_months_the_ledger_does_not_cover(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    spend(ledger, account, groceries, "2026-08-03", "-40.00")

    # A period reaching back before the ledger starts is clipped to the data.
    flows = monthly_flows(ledger, dt.date(2025, 10, 1), TODAY)

    assert [flow.month for flow in flows] == ["2026-08", "2026-09"]


def test_monthly_flows_on_an_empty_ledger_report_the_current_month_alone(ledger):
    flows = monthly_flows(ledger, dt.date(2025, 10, 1), TODAY)

    assert [(flow.month, flow.expenses) for flow in flows] == [("2026-09", Decimal("0"))]


def test_net_worth_series_counts_an_account_from_its_first_reported_balance(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    ledger.record_declared_balance(revolut, dt.date(2026, 9, 1), Decimal("1000.00"), "eb:ITAV")
    ledger.record_declared_balance(fineco, dt.date(2026, 9, 3), Decimal("250.00"), "eb:ITAV")
    ledger.record_declared_balance(revolut, dt.date(2026, 9, 3), Decimal("900.00"), "eb:ITAV")

    points = net_worth_series(ledger)

    # Fineco has no balance yet on the 1st, so it contributes nothing there.
    assert [(point.date.isoformat(), point.total) for point in points] == [
        ("2026-09-01", Decimal("1000.00")),
        ("2026-09-03", Decimal("1150.00")),
    ]
    latest = latest_balances(ledger)
    assert [item.account for item in latest] == ["Fineco", "Revolut"]
    assert [item.balance for item in latest] == [Decimal("250.00"), Decimal("900.00")]


def test_net_worth_series_ignores_balances_of_accounts_that_are_not_real(ledger):
    groceries = ledger.category("Groceries")
    ledger.record_declared_balance(groceries, dt.date(2026, 9, 1), Decimal("999.00"), "eb:ITAV")

    assert net_worth_series(ledger) == []
    assert latest_balances(ledger) == []


def test_a_scope_by_account_reads_only_what_that_account_paid(ledger):
    """'What did I spend on these two cards' has to be an answerable question."""
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    groceries = ledger.category("Groceries")
    spend(ledger, revolut, groceries, "2026-08-03", "-40.00")
    spend(ledger, fineco, groceries, "2026-08-04", "-60.00")
    august = (dt.date(2026, 8, 1), dt.date(2026, 8, 31))

    both = spend_by_category(ledger, *august)
    only_fineco = spend_by_category(ledger, *august, LedgerScope(accounts=("Fineco",)))

    assert [item.amount for item in both] == [Decimal("100.00")]
    assert [(item.category, item.amount) for item in only_fineco] == [
        ("Groceries", Decimal("60.00"))
    ]


def test_the_flows_chart_reads_only_the_accounts_it_is_given(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    groceries = ledger.category("Groceries")
    record(ledger, revolut, ledger.uncategorized(), "2026-08-05", "1000.00", "salary")
    record(ledger, fineco, ledger.uncategorized(), "2026-08-06", "250.00", "interest")
    spend(ledger, revolut, groceries, "2026-08-03", "-40.00")
    spend(ledger, fineco, groceries, "2026-08-04", "-60.00")

    flows = monthly_flows(
        ledger,
        dt.date(2026, 8, 1),
        dt.date(2026, 8, 31),
        LedgerScope(accounts=("Fineco",)),
    )

    assert [(flow.income, flow.expenses) for flow in flows] == [
        (Decimal("250.00"), Decimal("60.00"))
    ]


def test_liquidity_follows_the_accounts_and_ignores_the_categories(ledger):
    """A category is not an account: it cannot change what the accounts are worth."""
    revolut = ledger.ensure_account(
        Account(
            name="Revolut",
            type="real",
            opening_balance=Decimal("500.00"),
            opening_date=dt.date(2026, 7, 31),
        )
    )
    fineco = ledger.ensure_account(
        Account(
            name="Fineco",
            type="real",
            opening_balance=Decimal("200.00"),
            opening_date=dt.date(2026, 7, 31),
        )
    )
    groceries = ledger.category("Groceries")
    health = ledger.category("Salute")
    spend(ledger, revolut, groceries, "2026-08-03", "-40.00")
    spend(ledger, fineco, health, "2026-08-04", "-60.00")

    both = compute_metrics(ledger, TODAY)
    only_revolut = compute_metrics(ledger, TODAY, scope=LedgerScope(accounts=("Revolut",)))
    only_groceries = compute_metrics(ledger, TODAY, scope=LedgerScope(categories=("Groceries",)))

    assert both.liquidity == Decimal("600.00")  # 500 + 200 - 40 - 60
    assert only_revolut.liquidity == Decimal("460.00")  # 500 - 40
    assert both.recurring_burn == Decimal("100.00")
    assert only_revolut.recurring_burn == Decimal("40.00")
    assert only_groceries.recurring_burn == Decimal("40.00")
    assert only_groceries.liquidity == both.liquidity


def test_the_flows_chart_reads_the_period_it_is_given(ledger):
    account = ledger.ensure_account(Account(name="Revolut", type="real"))
    groceries = ledger.category("Groceries")
    spend(ledger, account, groceries, "2026-04-10", "-30.00")
    spend(ledger, account, groceries, "2026-06-10", "-50.00")

    flows = monthly_flows(ledger, dt.date(2026, 4, 1), dt.date(2026, 5, 31))

    # The period decides the months, and a month that has closed is final even
    # when the chart stops long before today.
    assert [(flow.month, flow.expenses, flow.partial) for flow in flows] == [
        ("2026-04", Decimal("30.00"), False),
        ("2026-05", Decimal("0"), False),
    ]


def test_the_period_of_the_net_worth_line_cuts_points_not_the_running_total(ledger):
    revolut = ledger.ensure_account(Account(name="Revolut", type="real"))
    fineco = ledger.ensure_account(Account(name="Fineco", type="real"))
    ledger.record_declared_balance(revolut, dt.date(2026, 6, 1), Decimal("100.00"), "eb:ITAV")
    ledger.record_declared_balance(fineco, dt.date(2026, 8, 1), Decimal("200.00"), "eb:ITAV")

    points = net_worth_series(ledger, dt.date(2026, 8, 1), dt.date(2026, 8, 31))

    # June's observation is not shown, but it still says what Revolut was worth
    # when August arrived.
    assert [(point.date.isoformat(), point.total) for point in points] == [
        ("2026-08-01", Decimal("300.00"))
    ]
