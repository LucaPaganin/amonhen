"""Snapshot the ledger and the configuration it needs, and prune the old ones.

The ledger is a SQLite database and the app may be writing it when the snapshot
is taken, so the copy is made with SQLite's own backup API rather than by reading
the file: a plain file copy of a live database can be torn, and a tombstone that
looks like a good backup is worse than none. The configuration is copied beside
the database, because a ledger without the `accounts.json` that names the
sessions is not restorable.
"""
import datetime as dt
import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Fixed width, so sorting the folder names sorts them by age.
STAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"
SNAPSHOT_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}Z$")

DATABASE_NAME = "amonhen.db"
MANIFEST_NAME = "manifest.json"
COUNTED_TABLES = ("accounts", "transactions", "postings")


@dataclass(frozen=True)
class Snapshot:
    path: Path
    created_at: str
    accounts: int
    transactions: int


def make_snapshot(
    conn: sqlite3.Connection,
    dest: Path | str,
    *,
    config_file: Path | str | None = None,
    keep: int = 0,
    now: dt.datetime | None = None,
) -> Snapshot:
    """Write one dated snapshot under `dest`, then keep only the newest `keep`.

    `now` must carry its timezone; a naive one is read as local time. `keep = 0`
    prunes nothing.
    """
    moment = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    stamp = moment.strftime(STAMP_FORMAT)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    # Under a dot and with a `.partial` suffix while it is being written: a run
    # that dies halfway must not leave behind a folder that looks like a
    # snapshot. The name it finally takes is the one retention recognises.
    partial = dest / f".{stamp}.partial"
    final = dest / stamp
    if final.exists():
        raise FileExistsError(f"{final} already exists")

    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir()
    try:
        source, counts = _copy_database(conn, partial / DATABASE_NAME)
        manifest = {
            "created_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": source,
            "db_sha256": _sha256(partial / DATABASE_NAME),
            **counts,
            "configuration": _copy_configuration(config_file, partial),
        }
        (partial / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise

    partial.rename(final)
    if keep > 0:
        _prune(dest, keep, final)
    return Snapshot(
        path=final,
        created_at=manifest["created_at"],
        accounts=counts["accounts"],
        transactions=counts["transactions"],
    )


def _copy_database(conn: sqlite3.Connection, target: Path) -> tuple[str, dict[str, int]]:
    """The live database into `target`, and what that copy holds.

    The counts are read from the copy and not from the living database: this runs
    while the server may be syncing, and a movement committed between the two
    would leave the manifest describing rows the snapshot does not hold.
    """
    copy = sqlite3.connect(str(target))
    try:
        conn.backup(copy)
        counts = {table: _count(copy, table) for table in COUNTED_TABLES}
    finally:
        copy.close()
    return _source_file(conn), counts


def _source_file(conn: sqlite3.Connection) -> str:
    for _, name, file in conn.execute("PRAGMA database_list"):
        if name == "main":
            return file
    return ""


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _copy_configuration(config_file: Path | str | None, target: Path) -> list[str]:
    """The configuration and the key it names, and the names that landed.

    Read with `json` and not with `load_config`: that one is strict on purpose,
    and a configuration this app cannot start from may still be the one worth
    keeping. What cannot be read is simply not copied.
    """
    if config_file is None:
        return []
    config = Path(config_file)
    if not config.is_file():
        return []

    shutil.copy2(config, target / config.name)
    copied = [config.name]
    try:
        settings = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return copied
    if not isinstance(settings, dict):
        return copied

    key = settings.get("pem_path")
    if not isinstance(key, str) or not key:
        return copied
    pem = (config.parent / key).resolve()
    if pem.is_file():
        shutil.copy2(pem, target / pem.name)
        copied.append(pem.name)
    return copied


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _prune(dest: Path, keep: int, written: Path) -> None:
    """Keep the newest `keep` snapshots, the one just written among them.

    The written folder is held back from the comparison instead of being assumed
    newest: a clock that stepped back, or another writer whose stamp is ahead,
    would otherwise have this call delete the snapshot it was called for — the
    newest backup lost by the very run that produced it.
    """
    others = sorted(
        (
            entry
            for entry in dest.iterdir()
            if entry.is_dir() and entry != written and SNAPSHOT_NAME.match(entry.name)
        ),
        key=lambda entry: entry.name,
        reverse=True,
    )
    for old in others[keep - 1:]:
        shutil.rmtree(old, ignore_errors=True)
