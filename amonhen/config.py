"""Configuration: Enable Banking credentials and the accounts to sync.

The file is the `accounts.json` the Actual connector already used. Only the
keys the monitoring system needs are read; the Actual Budget section is ignored.
"""
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from amonhen.settings import CONFIG_FILE


@dataclass(frozen=True)
class ConfiguredAccount:
    name: str
    institution: str
    session_id: str
    account_uid: str
    start_sync_date: dt.date | None = None


@dataclass(frozen=True)
class Passthrough:
    """A declared destination for money that is neither income nor spending.

    ``labels`` are pieces of text the bank prints on such a movement: the name of
    an own account that is not connected here ("Conto deposito senza vincoli"),
    or of a person or a firm whose money is passing through — a co-holder's share
    of a joint account, a reimbursement. ``incoming_only`` is for the second
    kind: a label that names somebody else matches the money arriving alone, or
    the same label swallows the insurance premium paid to the same firm.
    """

    destination: str
    labels: tuple[str, ...]
    incoming_only: bool = False


@dataclass(frozen=True)
class MonitorConfig:
    application_id: str
    pem_path: Path
    redirect_url: str
    own_names: frozenset[str]
    accounts: tuple[ConfiguredAccount, ...] = ()
    passthrough: tuple[Passthrough, ...] = ()


def parse_passthrough(raw: object) -> tuple[Passthrough, ...]:
    """Read the declared destinations, refusing one that says nothing.

    A declaration that does not parse raises instead of being skipped: money
    that stays in the burn because a bracket was in the wrong place is worse
    than a sync that stops and names the line it could not read.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("passthrough must be a list of declarations")
    declared = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"passthrough entry is not an object: {entry!r}")
        destination = str(entry.get("destination", "")).strip()
        if not destination:
            raise ValueError(f"passthrough entry without a destination: {entry!r}")
        labels = entry.get("labels")
        if not isinstance(labels, list):
            raise ValueError(f"passthrough entry {destination!r} declares no label")
        texts = tuple(str(label).strip() for label in labels if str(label).strip())
        if not texts:
            raise ValueError(f"passthrough entry {destination!r} declares no label")
        incoming_only = entry.get("incoming_only", False)
        if not isinstance(incoming_only, bool):
            raise ValueError(f"passthrough entry {destination!r}: incoming_only is true or false")
        declared.append(
            Passthrough(destination=destination, labels=texts, incoming_only=incoming_only)
        )
    return tuple(declared)


def parse_own_names(raw: str) -> frozenset[str]:
    return frozenset(name.strip().lower() for name in (raw or "").split(",") if name.strip())


def account_name(entry: dict) -> str:
    return (entry.get("notes") or entry.get("bank_name") or entry["account_uid"]).strip()


def save_account(config_path: str | Path, entry: dict) -> tuple[str, str]:
    """Add a connected account, or refresh the entry that account already has.

    The OAuth callback writes here, so the file stays the single place that
    lists the connected sessions, and unknown keys are preserved. The identity
    that matters is the account **uid**: a session is per authorization and
    changes when a consent is renewed, while the uid stays the same, so keying
    only on the (session, uid) pair used to append a second entry for an account
    that was already there — with today's start date and the bank's own name for
    it. The ledger matches an account by name, so the second entry became a
    second account, and the history came in again under it. An entry whose uid
    is already known is therefore refreshed in place: the session is replaced
    and the name and start date a person curated are kept.

    Returns what happened (``"refreshed"`` or ``"added"``) and the name the entry
    now has, which the callback reports back.
    """
    path = Path(config_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    accounts = list(data.get("accounts", []))
    incoming = (entry.get("session_id"), entry.get("account_uid"))
    stored: dict = entry
    for index, existing in enumerate(accounts):
        if existing.get("account_uid") == entry.get("account_uid") and entry.get("account_uid"):
            # A new authorization of an account already connected: take the new
            # session and keep what was decided about the account. `notes` is how
            # the ledger knows it — a new name would create a second account and
            # import the history into it — and `start_sync_date` is the history it
            # already has.
            merged = {**existing, **entry}
            for key in ("notes", "start_sync_date"):
                if existing.get(key):
                    merged[key] = existing[key]
            accounts[index] = merged
            stored, action = merged, "refreshed"
            break
        if (existing.get("session_id"), existing.get("account_uid")) == incoming:
            # The same authorization again: update the entry in place.
            accounts[index] = {**existing, **entry}
            stored, action = accounts[index], "refreshed"
            break
    else:
        accounts.append(entry)
        stored, action = entry, "added"
    data["accounts"] = accounts
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return action, account_name(stored)


def load_config(path: str | Path = CONFIG_FILE) -> MonitorConfig:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    pem_path = Path(data["pem_path"])
    if not pem_path.is_absolute():
        # Relative to the config file, so the same accounts.json works both in
        # the checkout and with the container's /config mount.
        pem_path = config_path.parent / pem_path
    accounts = []
    for entry in data.get("accounts", []):
        start = entry.get("start_sync_date")
        accounts.append(
            ConfiguredAccount(
                name=account_name(entry),
                institution=entry.get("bank_name") or entry.get("institution") or "",
                session_id=entry["session_id"],
                account_uid=entry["account_uid"],
                start_sync_date=dt.date.fromisoformat(start) if start else None,
            )
        )
    return MonitorConfig(
        application_id=data["application_id"],
        pem_path=pem_path,
        redirect_url=data.get("redirect_url", "http://localhost:3000/callback"),
        own_names=parse_own_names(data.get("account_holder_name", "")),
        accounts=tuple(accounts),
        passthrough=parse_passthrough(data.get("passthrough")),
    )
