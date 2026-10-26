"""Configuration: Enable Banking credentials and the accounts to sync.

The file is the `accounts.json` the Actual connector already used. Only the
keys the monitoring system needs are read; the Actual Budget section is ignored.
"""
import datetime as dt
import json
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.serialization import load_pem_private_key

from amonhen.settings import CONFIG_FILE

# One writer at a time in this process. The document is read, changed and
# written whole, so two writes that overlap would lose one of them: the setup
# screen saves one account row at a time while the OAuth callback can land in
# the same moment. The CLI is a separate process with its own lock, the same
# reasoning as the sync's `SyncBusy`.
_DOCUMENT_LOCK = threading.Lock()


DEFAULT_WINDOW_DAYS = 30


class UnknownConfiguredAccount(LookupError):
    """The configuration holds no account with that uid: a stale row, not a bad value."""


@dataclass(frozen=True)
class ConfiguredAccount:
    name: str
    institution: str
    session_id: str
    account_uid: str
    start_sync_date: dt.date | None = None
    # The widest range one request asks this bank for. Some refuse 30 days;
    # the period sync also halves a refused window on its own.
    max_window_days: int = DEFAULT_WINDOW_DAYS


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


def unique_name(wanted: str, taken: set[str]) -> str:
    """``wanted``, or ``wanted 2``, ``wanted 3``… — the first one not in ``taken``."""
    name, number = wanted, 1
    while name in taken:
        number += 1
        name = f"{wanted} {number}"
    return name


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
    with _editing(path) as data:
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
            # A bank that returns several accounts in one consent (FinecoBank: three
            # currencies and a card) gives them no names of their own, and the ledger
            # knows an account by its name, so a new entry never takes one in use.
            taken = {account_name(existing) for existing in accounts if isinstance(existing, dict)}
            entry = {**entry, "notes": unique_name(account_name(entry), taken)}
            accounts.append(entry)
            stored, action = entry, "added"
        data["accounts"] = accounts
        return action, account_name(stored)


def save_credentials(
    path: str | Path,
    *,
    application_id: str,
    redirect_url: str,
    account_holder_name: str | None = None,
    private_key: str | None = None,
) -> Path:
    """Write the Enable Banking credentials the first setup collected.

    The two addresses that must agree — the one the browser reaches and the one
    Enable Banking has registered — are checked here, because the bank's own
    refusal arrives after a browser round trip and names only itself. A key that
    does not load is refused for the same reason: a wizard that accepts it hands
    the person a configuration that fails at the next sync.

    `private_key` and `account_holder_name` are written only when they are given
    — `None`, not empty — so a step that left them out keeps what an earlier one
    decided, while an empty holder name is a person clearing it.
    """
    config_path = Path(path)
    application = application_id.strip()
    if not application:
        raise ValueError("the application ID is empty")
    redirect = redirect_url.strip()
    _check_redirect_url(redirect)
    # Checked before anything is written: a key that is not one must leave both
    # files exactly as they were.
    pem_bytes = _checked_private_key(private_key)

    with _editing(config_path) as document:
        declared_pem = str(document.get("pem_path") or "./private.pem")
        document["application_id"] = application
        document["redirect_url"] = redirect
        document["pem_path"] = declared_pem
        if account_holder_name is not None:
            holder = account_holder_name.strip()
            if holder:
                document["account_holder_name"] = holder
            else:
                document.pop("account_holder_name", None)
        document.setdefault("accounts", [])

    # The document first: a key written for an application id the file does not
    # name yet is a key nothing can use, and that half state is the one to avoid.
    if pem_bytes is not None:
        _write_private_key(_resolved_pem_path(config_path, declared_pem), pem_bytes)
    return config_path


def rename_account(
    path: str | Path,
    account_uid: str,
    *,
    name: str,
    start_sync_date: str | None = None,
) -> Path:
    """Name a configured account, and say from when its movements are imported.

    The name is how the ledger knows the account, so a name another entry
    already uses is refused here: two entries under one name are one ledger
    account, and their movements would land in it together.
    """
    config_path = Path(path)
    with _editing(config_path) as document:
        entries = _account_entries(document)
        entry = _entry_by_uid(entries, account_uid)
        wanted = name.strip()
        if not wanted:
            raise ValueError("the account name is empty")
        for other in entries:
            if other is not entry and account_name(other) == wanted:
                raise ValueError(f"another configured account is already called {wanted!r}")

        start = (start_sync_date or "").strip()
        if start:
            dt.date.fromisoformat(start)
            entry["start_sync_date"] = start
        else:
            entry.pop("start_sync_date", None)
        entry["notes"] = wanted
        return config_path


def remove_account(path: str | Path, account_uid: str) -> Path:
    """Drop a configured account: the sync stops asking the bank for it.

    What the ledger already holds stays where it is. A bank that returns four
    accounts when one was wanted is why this exists — the entry was written by
    an authorization, not by a person.
    """
    config_path = Path(path)
    with _editing(config_path) as document:
        entries = _account_entries(document)
        _entry_by_uid(entries, account_uid)
        # From the original list, not the parsed one: an entry the app does not
        # know about is not the app's to delete.
        document["accounts"] = [
            entry
            for entry in document["accounts"]
            if not (isinstance(entry, dict) and entry.get("account_uid") == account_uid)
        ]
        return config_path


def setup_state(path: str | Path = CONFIG_FILE) -> dict:
    """What the first-setup screen needs to know, for a file that may not exist.

    An empty document is the state a fresh install is in, so this answers
    instead of raising: without it the app could not tell "nothing configured
    yet" from "this server is broken". The private key is never part of the
    answer — only whether a file is there and whether it loads as one.
    """
    config_path = Path(path)
    document = _read_document(config_path)
    application = str(document.get("application_id") or "").strip()
    pem_path = _resolved_pem_path(config_path, document.get("pem_path"))
    key_loads = _loads_as_private_key(pem_path)
    entries = _account_entries(document)

    missing = []
    if not application:
        missing.append("application_id")
    if not key_loads:
        missing.append("private_key")
    if not entries:
        missing.append("accounts")
    return {
        "configured": not missing,
        "missing": missing,
        "application_id": application,
        "redirect_url": str(document.get("redirect_url") or "").strip(),
        "account_holder_name": str(document.get("account_holder_name") or ""),
        "pem_path": str(pem_path),
        "key_loads": key_loads,
        "accounts": [
            {
                "account_uid": str(entry.get("account_uid") or ""),
                "name": account_name(entry),
                "institution": entry.get("bank_name") or entry.get("institution") or "",
                "country": entry.get("country") or "",
                "start_sync_date": entry.get("start_sync_date"),
                "session_expiry": entry.get("session_expiry"),
            }
            for entry in entries
        ],
    }


def load_config(path: str | Path = CONFIG_FILE) -> MonitorConfig:
    config_path = Path(path)
    data = _read_document(config_path)
    if not data:
        raise FileNotFoundError(f"no configuration file at {config_path}")
    pem_path = _resolved_pem_path(config_path, data.get("pem_path"))
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
                max_window_days=_window_days(entry.get("max_window_days")),
            )
        )
    return MonitorConfig(
        application_id=data["application_id"],
        pem_path=pem_path,
        redirect_url=data.get("redirect_url", "http://localhost:8000/callback"),
        own_names=parse_own_names(data.get("account_holder_name", "")),
        accounts=tuple(accounts),
        passthrough=parse_passthrough(data.get("passthrough")),
    )


def _window_days(value) -> int:
    """`max_window_days` as written by hand: a positive whole number of days."""
    if value is None:
        return DEFAULT_WINDOW_DAYS
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"max_window_days must be a positive number of days, not {value!r}")
    return value


def _read_document(path: Path) -> dict:
    """The configuration as the document it is, or an empty one when absent."""
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not hold a JSON object")
    return data


@contextmanager
def _editing(path: Path) -> Iterator[dict]:
    """The document to change, with read-change-write held as one step.

    An exception raised inside the block skips the write, so a step that
    refuses what it was given leaves the file exactly as it was.
    """
    with _DOCUMENT_LOCK:
        document = _read_document(path)
        yield document
        _write_document(path, document)


def _write_document(path: Path, data: dict) -> None:
    """Replace the document in one step, so a reader never sees half of it.

    Readers do not take the lock — `/api/setup`, `/connect` and the sync loop are
    separate threads — so a truncate-then-write would show them an empty file for
    an instant, and a crash in the middle would leave one: the whole
    configuration, gone, with a JSON parser message to diagnose it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    scratch = path.with_name(f".{path.name}.tmp")
    scratch.write_text(payload, encoding="utf-8")
    os.replace(scratch, path)


def _account_entries(document: dict) -> list[dict]:
    entries = document.setdefault("accounts", [])
    if not isinstance(entries, list):
        raise ValueError("accounts must be a list")
    return [entry for entry in entries if isinstance(entry, dict)]


def _entry_by_uid(entries: list[dict], account_uid: str) -> dict:
    for entry in entries:
        if entry.get("account_uid") == account_uid:
            return entry
    raise UnknownConfiguredAccount(f"no configured account with uid {account_uid!r}")


def _resolved_pem_path(config_path: Path, raw: object) -> Path:
    path = Path(str(raw) if raw else "./private.pem")
    if path.is_absolute():
        return path
    # Relative to the config file, so the same accounts.json works both in the
    # checkout and with the container's /config mount.
    return config_path.parent / path


def _loads_as_private_key(path: Path) -> bool:
    try:
        load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, TypeError, ValueError):
        return False
    return True


def _checked_private_key(pem: str | None) -> bytes | None:
    """The pasted key as bytes, refused when it is not one. None when absent."""
    if pem is None or not pem.strip():
        return None
    payload = pem.strip().encode("utf-8")
    try:
        load_pem_private_key(payload, password=None)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"the private key is not a PEM private key: {exc}") from exc
    return payload


def _write_private_key(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload + b"\n")
    path.chmod(0o600)
    return path


# The one http shape that stays usable: the rehearsal against the stub bank serves
# the callback from the machine the browser is on, and has no certificate to offer.
_LOCAL_REDIRECT_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _check_redirect_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"the redirect URL is not an http(s) address: {url!r}")
    if parts.scheme == "http" and parts.hostname not in _LOCAL_REDIRECT_HOSTS:
        raise ValueError(
            "the redirect URL must be https: Enable Banking registers no http address, so "
            "the registered one and this one could never agree. An http address on localhost "
            "is the exception, for the rehearsal against the stub bank, where the machine "
            "serving the callback is the one the browser runs on"
        )
    if parts.path.rstrip("/") != "/callback":
        raise ValueError(
            "the redirect URL must be the app's /callback — scheme, host and port included — "
            "because it is the address Enable Banking sends the browser back to, and nothing "
            "else serves that route"
        )
