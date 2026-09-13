"""Command line entry point: sync, import, balances and the spend query."""
import argparse
import calendar
import datetime as dt
import logging
import sys
import time
from decimal import Decimal
from pathlib import Path

from amonhen.config import load_config
from amonhen.ledger import Ledger, balance_kind
from amonhen.merchants import RuleBook, categorize, rule_usage
from amonhen.models import Account, format_decimal, parse_decimal
from amonhen.settings import (
    CONFIG_FILE,
    DB_PATH,
    HOST,
    PORT,
    SYNC_INTERVAL_HOURS,
)
from amonhen.sync import SyncService
from amonhen.transfers import link_passthrough_legs, link_transfers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amonhen", description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH), help="ledger database")
    parser.add_argument("--config", default=str(CONFIG_FILE), help="accounts.json")
    parser.add_argument("-v", "--verbose", action="store_true", help="log each sync step")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sync", help="fetch every configured account into the ledger")
    sub.add_parser("validate", help="assert that every transaction balances")
    sub.add_parser("categorize", help="apply the rules to the movements still in the queue")

    serve = sub.add_parser("serve", help="run the HTTP API and the PWA")
    serve.add_argument("--host", default=HOST)
    serve.add_argument("--port", type=int, default=PORT)
    serve.add_argument(
        "--sync-interval-hours",
        type=float,
        default=0,
        help="also sync on this cadence, inside the server process (0 disables)",
    )

    sub.add_parser("rules", help="list the rules and how many movements each holds")

    metrics = sub.add_parser("metrics", help="burn, accrual, runway and savings flow")

    flags = sub.add_parser("category-flags", help="mark a category episodic or essential")
    flags.add_argument("category")
    flags.add_argument("--episodic", action="store_true", default=None)
    flags.add_argument("--not-episodic", dest="episodic", action="store_false")
    flags.add_argument("--essential", action="store_true", default=None)
    flags.add_argument("--not-essential", dest="essential", action="store_false")

    account_flags = sub.add_parser("account-flags", help="mark a real account as investment")
    account_flags.add_argument("account")
    account_flags.add_argument("--investment", action="store_true", default=None)
    account_flags.add_argument("--not-investment", dest="investment", action="store_false")

    split = sub.add_parser("split", help="split a transaction across categories")
    split.add_argument("transaction_id", type=int)
    split.add_argument("parts", nargs="+", metavar="CATEGORY=AMOUNT")

    setting = sub.add_parser("set", help="save a key/value setting in the ledger")
    setting.add_argument("key")
    setting.add_argument("value")

    budget = sub.add_parser("budget", help="set or clear a category's monthly budget")
    budget.add_argument("category")
    budget.add_argument("amount", nargs="?", help="omit to clear the budget")

    budgets = sub.add_parser("budgets", help="budget, spent and remaining per category")
    budgets.add_argument("--month", help="YYYY-MM (default: the current month)")

    anomalies = sub.add_parser("anomalies", help="explain unusually large movements")
    anomalies.add_argument("--days", type=int, default=31)

    sub.add_parser("suggest", help="classifier proposals for uncovered merchants")
    sub.add_parser("llm-suggest", help="ask the configured LLM about unseen merchants")

    category_add = sub.add_parser("category-add", help="create a category for the UI and rules")
    category_add.add_argument("name")

    rule_add = sub.add_parser("rule-add", help="add or change a rule")
    rule_add.add_argument("pattern", help="text the description contains, or /an expression/")
    rule_add.add_argument("category")

    rule_remove = sub.add_parser("rule-remove", help="drop a rule and release its movements")
    rule_remove.add_argument("pattern")

    daemon = sub.add_parser("daemon", help="run sync in a loop")
    daemon.add_argument("--interval-hours", type=float, default=SYNC_INTERVAL_HOURS)

    accounts = sub.add_parser("accounts", help="list ledger accounts with balances")
    accounts.add_argument("--as-of", help="balance date (default: today)")

    account_add = sub.add_parser("account-add", help="create a local (non-bank) account")
    account_add.add_argument("name")
    account_add.add_argument("--iban")
    account_add.add_argument("--institution")
    account_add.add_argument("--opening", help="opening balance")
    account_add.add_argument("--opening-date")

    import_cmd = sub.add_parser("import", help="import a CSV/OFX export")
    import_cmd.add_argument("file")
    import_cmd.add_argument("--account", required=True)
    import_cmd.add_argument("--profile", help="CSV profile name (revolut, fineco, actual)")

    spend = sub.add_parser("spend", help="money spent, transfers excluded")
    spend.add_argument("--month", help="YYYY-MM (default: last month)")

    balances = sub.add_parser("balances", help="record the balances the bank declares")
    balances.add_argument("--account", help="only this account")

    anchor = sub.add_parser("anchor", help="set an opening balance from a declared balance")
    anchor.add_argument("--account", required=True)
    anchor.add_argument("--as-of", required=True)
    anchor.add_argument("--declared", help="declared balance (default: latest recorded one)")
    anchor.add_argument("--kind", choices=("available", "booked"), default="available",
                        help="which figure a hand-typed --declared is (default: available)")

    check = sub.add_parser("balance-check", help="assert saldo_iniziale + movimenti == saldo banca")
    check.add_argument("--account", required=True)
    check.add_argument("--as-of", required=True)
    check.add_argument("--declared", help="declared balance (default: latest recorded one)")
    check.add_argument("--kind", choices=("available", "booked"), default="available",
                       help="which figure a hand-typed --declared is (default: available)")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    from amonhen.db import open_ledger_db

    ledger = Ledger(open_ledger_db(args.db))
    handler = HANDLERS[args.command]
    return handler(ledger, args)


# -- commands -------------------------------------------------------------


def cmd_sync(ledger: Ledger, args) -> int:
    config = load_config(args.config)
    service = SyncService(ledger, build_client(config), config)
    result = service.run()
    for account in result.accounts:
        summary = ", ".join(f"{action}={count}" for action, count in sorted(account.actions.items()))
        print(f"{account.account}: fetched={account.fetched} balances={account.balances} {summary}".rstrip())
        for problem in (account.error, account.balance_mismatch):
            if problem:
                print(f"{account.account}: {problem}", file=sys.stderr)
    print(f"transfers linked: {result.transfers_linked}")
    print(f"passthrough legs: {result.passthrough_legs}")
    print(f"rules applied: {result.rules_applied}")
    return 1 if result.errors else 0


def cmd_daemon(ledger: Ledger, args) -> int:
    while True:
        cmd_sync(ledger, args)
        wait = args.interval_hours * 3600
        logging.info("sleeping %.1f h", args.interval_hours)
        try:
            time.sleep(wait)
        except KeyboardInterrupt:
            return 0


def cmd_validate(ledger: Ledger, args) -> int:
    try:
        ledger.validate()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("ok: every transaction balances")
    return 0


def cmd_categorize(ledger: Ledger, args) -> int:
    applied = categorize(ledger, RuleBook(ledger.conn))
    print(f"rules applied: {applied}")
    return 0


def cmd_serve(ledger: Ledger, args) -> int:
    import threading

    import uvicorn

    from amonhen.api import create_app

    if args.sync_interval_hours > 0:
        # Fail at startup, not in a log line every interval: a missing
        # accounts.json or private.pem must be visible immediately.
        try:
            build_client(load_config(args.config))
        except (OSError, KeyError, ValueError) as exc:
            print(f"cannot sync: {exc}", file=sys.stderr)
            return 1
        threading.Thread(
            target=_sync_loop,
            args=(args.db, args.config, args.sync_interval_hours),
            name="sync",
            daemon=True,
        ).start()
    uvicorn.run(create_app(args.db), host=args.host, port=args.port)
    return 0


def _sync_loop(db_path: str, config_path: str, interval_hours: float) -> None:
    """Scheduled PSD2 sync inside the server process: one writer, one database."""
    from amonhen.db import open_ledger_db

    while True:
        try:
            conn = open_ledger_db(db_path)
            try:
                config = load_config(config_path)
                SyncService(Ledger(conn), build_client(config), config).run()
            finally:
                conn.close()
        except Exception:
            logging.exception("scheduled sync failed")
        time.sleep(interval_hours * 3600)


def cmd_rules(ledger: Ledger, args) -> int:
    book = RuleBook(ledger.conn)
    rules = book.rules()
    usage = rule_usage(ledger, rules)
    for rule in rules:
        print(f"{rule.pattern:<40} {rule.category:<20} {usage.get(rule.key, 0):>4} movements")
    return 0


def cmd_metrics(ledger: Ledger, args) -> int:
    from amonhen.metrics import compute_metrics

    metrics = compute_metrics(ledger, dt.date.today())
    history = f"{metrics.months_of_history} month(s) of history"
    if metrics.partial:
        history += " — recurring burn is partial"
    if metrics.episodic_partial:
        history += " — episodic accrual is partial"
    print(history)
    print(f"recurring burn      {_money(metrics.recurring_burn):>12}")
    print(f"episodic accrual    {_money(metrics.episodic_accrual):>12}")
    print(f"expected burn       {_money(metrics.expected_burn):>12}")
    print(f"essential monthly   {_money(metrics.essential_monthly):>12}")
    print(f"discretionary       {_money(metrics.discretionary_monthly):>12}")
    print(f"liquidity (tracked) {_money(metrics.liquidity):>12}")
    runway = f"{metrics.runway_months:.1f}" if metrics.runway_months is not None else "n/a"
    print(f"runway (stress)     {runway:>12} months")
    print(f"savings flow        {_money(metrics.savings_flow):>12}")
    return 0


def cmd_category_flags(ledger: Ledger, args) -> int:
    account_id = ledger.category(args.category)
    if args.episodic is not None:
        ledger.set_category_flag(account_id, "episodic", args.episodic)
    if args.essential is not None:
        ledger.set_category_flag(account_id, "essential", args.essential)
    row = ledger.account(account_id)
    print(f"{row['name']}: episodic={bool(row['episodic'])} essential={bool(row['essential'])}")
    return 0


def cmd_account_flags(ledger: Ledger, args) -> int:
    account = require_account(ledger, args.account)
    if args.investment is None:
        print(f"{account['name']}: investment={bool(account['investment'])}")
        return 0
    ledger.set_investment(account["id"], args.investment)
    print(f"{account['name']}: investment={args.investment}")
    return 0


def cmd_split(ledger: Ledger, args) -> int:
    parts = []
    for part in args.parts:
        category, _, amount = part.partition("=")
        if not category or not amount:
            print(f"expected CATEGORY=AMOUNT, got {part!r}", file=sys.stderr)
            return 2
        parts.append((ledger.category(category), parse_decimal(amount)))
    ledger.set_splits(args.transaction_id, parts)
    ledger.validate()
    print(f"transaction {args.transaction_id} split into {len(parts)} categories")
    return 0


def cmd_set(ledger: Ledger, args) -> int:
    ledger.set_setting(args.key, args.value)
    print(f"{args.key} = {args.value}")
    return 0


def cmd_budget(ledger: Ledger, args) -> int:
    try:
        account_id = ledger.category(args.category)
        if args.amount is None:
            ledger.set_budget(account_id, None)
            print(f"{args.category}: budget cleared")
            return 0
        ledger.set_budget(account_id, parse_decimal(args.amount))
    except (ValueError, ArithmeticError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"{args.category}: budget {args.amount}")
    return 0


def cmd_budgets(ledger: Ledger, args) -> int:
    start, end = month_range(args.month) if args.month else current_month_range()
    print(f"{start}..{end}")
    for row in ledger.budget_status(start, end):
        budget = row["budget"] if row["budget"] is not None else "—"
        remaining = row["remaining"] if row["remaining"] is not None else "—"
        print(f"{row['category']:<28} {budget:>10}  spent {row['spent']:>10}  left {remaining:>10}")
    return 0


def cmd_anomalies(ledger: Ledger, args) -> int:
    from amonhen.anomalies import detect_anomalies

    today = dt.date.today()
    cutoff = today - dt.timedelta(days=args.days)
    found = [anomaly for anomaly in detect_anomalies(ledger, today) if anomaly.date >= cutoff]
    if not found:
        print(f"no anomalies in the last {args.days} day(s)")
        return 0
    for anomaly in found:
        print(anomaly.sentence)
    return 0


def cmd_suggest(ledger: Ledger, args) -> int:
    from amonhen.classifier import apply_proposals, coverage, propose_categories

    proposals = propose_categories(ledger)
    recorded = apply_proposals(ledger, proposals)
    share = coverage(ledger, proposals)
    print(f"considered {len(proposals)} merchant(s), recorded {recorded} proposal(s)")
    print(
        f"coverage: rules/manual {share['categorized']}/{share['spending']} settled movements, "
        f"classifier proposes for {share['proposed']} of the {share['uncovered']} uncovered"
    )
    return 0


def cmd_llm_suggest(ledger: Ledger, args) -> int:
    from amonhen.llm import llm_config
    from amonhen.suggestions import propose_for_unseen

    try:
        recorded = propose_for_unseen(ledger, llm_config())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"recorded {recorded} proposal(s)")
    return 0


def _money(value) -> str:
    return format_decimal(value) if value is not None else "n/a"


def cmd_category_add(ledger: Ledger, args) -> int:
    try:
        account_id = ledger.category(args.name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"category {account_id}: {args.name}")
    return 0


def cmd_rule_add(ledger: Ledger, args) -> int:
    try:
        count = RuleBook(ledger.conn).set_rule(args.pattern, args.category, ledger)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"rule added: {args.pattern} -> {args.category} ({count} movements)")
    return 0


def cmd_rule_remove(ledger: Ledger, args) -> int:
    held = RuleBook(ledger.conn).remove_rule(args.pattern, ledger)
    if held is None:
        print(f"no rule for {args.pattern!r}", file=sys.stderr)
        return 1
    print(f"rule removed: {args.pattern} ({held} movements released)")
    return 0


def cmd_accounts(ledger: Ledger, args) -> int:
    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()
    rows = ledger.conn.execute("SELECT * FROM accounts ORDER BY type, name").fetchall()
    for row in rows:
        balance = ledger.balance(row["id"], as_of) if row["type"] == "real" else Decimal(0)
        print(f"{row['id']:>3}  {row['type']:<8} {row['name']:<28} {format_decimal(balance):>12}")
    return 0


def cmd_account_add(ledger: Ledger, args) -> int:
    account_id = ledger.ensure_account(
        Account(
            name=args.name,
            type="real",
            iban=args.iban,
            institution=args.institution,
            opening_balance=parse_decimal(args.opening) if args.opening else None,
            opening_date=dt.date.fromisoformat(args.opening_date) if args.opening_date else None,
        )
    )
    print(f"account {account_id}: {args.name}")
    return 0


def cmd_import(ledger: Ledger, args) -> int:
    from amonhen.adapters import ACTUAL, FINECO, REVOLUT, parse_export

    profiles = {"actual": ACTUAL, "fineco": FINECO, "revolut": REVOLUT}
    if args.profile and args.profile not in profiles:
        raise SystemExit(f"unknown profile {args.profile!r}; known: {', '.join(sorted(profiles))}")
    account = require_account(ledger, args.account)
    transactions = parse_export(
        args.file,
        account_id=account["id"],
        balancing_account_id=ledger.uncategorized(),
        profile=profiles[args.profile] if args.profile else None,
        source_file=Path(args.file).name,
    )
    counts = ledger.record_batch(transactions)
    link_transfers(ledger)
    legs = link_passthrough_legs(ledger, load_config(args.config).passthrough)
    ledger.validate()
    applied = categorize(ledger, RuleBook(ledger.conn))
    print(f"{args.account}: parsed={len(transactions)} " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"passthrough legs: {legs}")
    print(f"rules applied: {applied}")
    return 0


def cmd_spend(ledger: Ledger, args) -> int:
    start, end = month_range(args.month)
    total = ledger.spend_between(start, end)
    print(f"spent {start}..{end}: {format_decimal(total)} EUR (booked, transfers excluded)")
    return 0


def cmd_balances(ledger: Ledger, args) -> int:
    from amonhen.providers.enable_banking import ConsentExpiredError

    config = load_config(args.config)
    client = build_client(config)
    accounts = config.accounts if not args.account else [
        entry for entry in config.accounts if entry.name == args.account
    ]
    if not accounts:
        print(f"account {args.account} is not configured", file=sys.stderr)
        return 1
    failures = 0
    for entry in accounts:
        account = require_account(ledger, entry.name)
        try:
            payload = client.fetch_balances(entry.account_uid)
        except ConsentExpiredError as exc:
            print(f"{entry.name}: consent expired: {exc}", file=sys.stderr)
            failures += 1
            continue
        for balance in payload.get("balances", []):
            amount = balance.get("balance_amount") or {}
            if not amount.get("amount"):
                continue
            reference = (balance.get("reference_date") or dt.date.today().isoformat())[:10]
            ledger.record_declared_balance(
                account["id"], dt.date.fromisoformat(reference), parse_decimal(amount["amount"]),
                f"eb:{balance.get('balance_type', 'unknown')}",
            )
            print(f"{entry.name}: {reference} {balance.get('balance_type')} {amount['amount']} {amount.get('currency')}")
    return 1 if failures else 0


def cmd_anchor(ledger: Ledger, args) -> int:
    account = require_account(ledger, args.account)
    found = declared_balance(
        ledger, account["id"], dt.date.fromisoformat(args.as_of), args.declared, args.kind
    )
    if found is None:
        print(f"no declared balance for {args.account} on or before {args.as_of}", file=sys.stderr)
        return 1
    as_of, declared, source = found
    kind = balance_kind(source)
    opening, opening_date = ledger.anchor_opening(account["id"], as_of, declared, kind)
    if args.declared:
        ledger.record_declared_balance(account["id"], as_of, declared, f"anchor:{kind}")
    print(
        f"{args.account}: opening {format_decimal(opening)} before {opening_date} "
        f"from the declared balance of {format_decimal(declared)} on {as_of} ({kind})"
    )
    return 0


def cmd_balance_check(ledger: Ledger, args) -> int:
    account = require_account(ledger, args.account)
    found = declared_balance(
        ledger, account["id"], dt.date.fromisoformat(args.as_of), args.declared, args.kind
    )
    if found is None:
        print("declared balance required (--declared or `monitor balances`)", file=sys.stderr)
        return 1
    as_of, declared, source = found
    check = ledger.check_balance(
        account["id"], declared, as_of, kind=balance_kind(source), source=source
    )
    print(
        f"{args.account} {as_of}: opening={format_decimal(check.opening)} "
        f"computed={format_decimal(check.computed)} declared={format_decimal(check.declared)} "
        f"difference={format_decimal(check.difference)} kind={check.kind}"
    )
    if not check.ok:
        print("MISMATCH: duplicates or gaps in the ledger", file=sys.stderr)
        return 1
    return 0


# -- helpers --------------------------------------------------------------


def build_client(config):
    from amonhen.providers.enable_banking import EnableBankingClient

    return EnableBankingClient(
        application_id=config.application_id,
        pem_path=config.pem_path,
        redirect_url=config.redirect_url,
    )


def require_account(ledger: Ledger, name: str):
    account = ledger.find_account(name=name)
    if account is None:
        raise SystemExit(f"unknown account: {name} (run `monitor sync` or `monitor account-add`)")
    return account


def declared_balance(
    ledger: Ledger, account_id: int, as_of: dt.date, explicit: str | None, kind: str = "available"
) -> tuple[dt.date, Decimal, str] | None:
    """The declaration to compare against, the date it refers to, and its source.

    Without an explicit value the latest recorded balance on or before `as_of`
    decides the date too: comparing a balance dated 2026-09-10 against the
    ledger as of 2026-09-12 would report a mismatch that is not one. The pick
    itself lives in the ledger, so the CLI, the sync and the app agree on it.

    A number typed by hand has no bank tag to say which of the two figures it
    is, so it carries the word instead (`manual:booked`) and the rest of the
    code treats it exactly like a tag from the bank.
    """
    if explicit is not None:
        return as_of, parse_decimal(explicit), f"manual:{kind}"
    row = ledger.declaration_for(account_id, as_of)
    if row is None:
        return None
    return dt.date.fromisoformat(row["date"]), parse_decimal(row["balance"]), row["source"]


def month_range(month: str | None) -> tuple[dt.date, dt.date]:
    """A YYYY-MM month; with no month, the previous one (the spend default)."""
    if month:
        year, number = (int(part) for part in month.split("-"))
    else:
        first_of_this = dt.date.today().replace(day=1)
        previous = first_of_this - dt.timedelta(days=1)
        year, number = previous.year, previous.month
    last_day = calendar.monthrange(year, number)[1]
    return dt.date(year, number, 1), dt.date(year, number, last_day)


def current_month_range() -> tuple[dt.date, dt.date]:
    """The month in progress, which is what a budget is measured against."""
    today = dt.date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=1), dt.date(today.year, today.month, last_day)


HANDLERS = {
    "sync": cmd_sync,
    "daemon": cmd_daemon,
    "validate": cmd_validate,
    "categorize": cmd_categorize,
    "serve": cmd_serve,
    "rules": cmd_rules,
    "metrics": cmd_metrics,
    "category-flags": cmd_category_flags,
    "account-flags": cmd_account_flags,
    "split": cmd_split,
    "set": cmd_set,
    "budget": cmd_budget,
    "budgets": cmd_budgets,
    "anomalies": cmd_anomalies,
    "suggest": cmd_suggest,
    "llm-suggest": cmd_llm_suggest,
    "category-add": cmd_category_add,
    "rule-add": cmd_rule_add,
    "rule-remove": cmd_rule_remove,
    "accounts": cmd_accounts,
    "account-add": cmd_account_add,
    "import": cmd_import,
    "spend": cmd_spend,
    "balances": cmd_balances,
    "anchor": cmd_anchor,
    "balance-check": cmd_balance_check,
}


if __name__ == "__main__":
    sys.exit(main())
