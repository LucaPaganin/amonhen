"""Dump raw Enable Banking payloads to disk.

The parsing tests are built from real, anonymized payloads, so regenerating the
fixtures starts here: this writes the raw JSON that `tools/anonymize_dump.py`
then pseudonymizes. It parses nothing and writes nothing to the ledger.

Usage:
    uv run python tools/dump_raw.py
    uv run python tools/dump_raw.py --from 2026-01-01 --out dumps
    uv run python tools/dump_raw.py --account 0
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amonhen.config import load_config
from amonhen.providers.enable_banking import ConsentExpiredError, EnableBankingClient
from amonhen.settings import CONFIG_FILE


def build_client(config) -> EnableBankingClient:
    return EnableBankingClient(
        application_id=config.application_id,
        pem_path=config.pem_path,
        redirect_url=config.redirect_url,
    )


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "account").lower()).strip("-")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def dump_sessions(client: EnableBankingClient, config, out_dir: Path) -> dict[str, list[dict]]:
    """Fetch every distinct session, so the account list comes from the API."""
    sessions: dict[str, list[dict]] = {}
    for session_id in dict.fromkeys(account.session_id for account in config.accounts):
        accounts = client.list_accounts(session_id)
        sessions[session_id] = accounts
        write_json(out_dir / "sessions" / f"{session_id}.json", accounts)
        print(f"  session {session_id}: {len(accounts)} account(s)")
    return sessions


def dump_account(
    client: EnableBankingClient, entry, date_from: dt.date, date_to: dt.date, out_dir: Path
) -> dict:
    label = f"{entry.institution} {slug(entry.name)}"
    try:
        transactions = client.fetch_transactions(entry.account_uid, date_from, date_to)
    except ConsentExpiredError as exc:
        print(f"  {label}: {exc}")
        return {"label": label, "account_uid": entry.account_uid, "error": str(exc)}

    statuses: dict[str, int] = {}
    for transaction in transactions:
        status = transaction.get("status") or "?"
        statuses[status] = statuses.get(status, 0) + 1
    write_json(
        out_dir / "accounts" / f"{label}.json",
        {
            "account": {
                "bank_name": entry.institution,
                "account_uid": entry.account_uid,
                "notes": entry.name,
            },
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "count": len(transactions),
            "transactions": transactions,
        },
    )
    print(f"  {label}: {len(transactions)} transaction(s) {statuses}")
    return {
        "label": label,
        "account_uid": entry.account_uid,
        "bank": entry.institution,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "count": len(transactions),
        "statuses": statuses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(CONFIG_FILE), help="Path to accounts.json")
    parser.add_argument("--from", dest="date_from", help="Earliest date (default: start_sync_date)")
    parser.add_argument("--to", dest="date_to", help="Latest date (default: today)")
    parser.add_argument("--out", default="dumps", help="Output directory (default: dumps)")
    parser.add_argument("--account", help="Only this account index or uid")
    args = parser.parse_args()

    config = load_config(args.config)
    accounts = list(config.accounts)
    if not accounts:
        sys.exit(f"no accounts configured in {args.config}")
    if args.account is not None:
        try:
            accounts = [accounts[int(args.account)]]
        except (ValueError, IndexError):
            accounts = [entry for entry in accounts if entry.account_uid == args.account]
            if not accounts:
                sys.exit(f"account {args.account} not found")

    client = build_client(config)
    out_dir = Path(args.out)
    date_to = dt.date.fromisoformat(args.date_to) if args.date_to else dt.date.today()

    print(f"Enable Banking dump -> {out_dir}")
    sessions = dump_sessions(client, config, out_dir)

    results = []
    for entry in accounts:
        date_from = dt.date.fromisoformat(args.date_from) if args.date_from else (
            entry.start_sync_date or date_to - dt.timedelta(days=90)
        )
        results.append(dump_account(client, entry, date_from, date_to, out_dir))

    write_json(
        out_dir / "index.json",
        {
            "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
            "sessions": sorted(sessions),
            "accounts": results,
        },
    )
    print(f"index written: {out_dir / 'index.json'}")


if __name__ == "__main__":
    main()
