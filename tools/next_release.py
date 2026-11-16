"""The next release: its tag and the message the tag carries.

Run by `.github/workflows/release.yml` after every push to `main`, and by hand to
see what the next release would say:

    python tools/next_release.py --bump patch --title "…" [--pr 12] [--body-file f]

It prints `version=vX.Y.Z` on the first line, then writes the message to
`--message-file` (or prints it after a blank line). It reads only git: the last
release is the highest `vX.Y.Z` tag, and what the release does to the ledger is
read from `amonhen/db.py` at that tag and at HEAD, parsed and never imported, so
it needs no dependency installed.

The message answers what README *Updating safely* asks of every release: does it
migrate the ledger, and is the rollback the tag alone or the snapshot as well.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BUMPS = ("major", "minor", "patch")
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
DB = "amonhen/db.py"
VERSION = "amonhen/api/version.py"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def parse_tag(tag: str) -> tuple[int, int, int] | None:
    match = TAG.match(tag.strip())
    return tuple(int(part) for part in match.groups()) if match else None  # type: ignore[return-value]


def last_release(tags: list[str]) -> str | None:
    """The highest `vX.Y.Z` among the tags, by number and not by text."""
    releases = [tag for tag in tags if parse_tag(tag)]
    return max(releases, key=parse_tag) if releases else None  # type: ignore[arg-type]


def bump(tag: str | None, part: str) -> str:
    if part not in BUMPS:
        raise ValueError(f"bump must be one of {BUMPS}, not {part!r}")
    major, minor, patch = parse_tag(tag) if tag else (0, 0, 0)  # type: ignore[misc]
    if part == "major":
        return f"v{major + 1}.0.0"
    if part == "minor":
        return f"v{major}.{minor + 1}.0"
    return f"v{major}.{minor}.{patch + 1}"


def migrations(source: str) -> list[str]:
    """The names in `MIGRATIONS = (...)`, in order, read from the source."""
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "MIGRATIONS" for t in node.targets)
            and isinstance(node.value, (ast.Tuple, ast.List))
        ):
            return [elt.id for elt in node.value.elts if isinstance(elt, ast.Name)]
    return []


def api_version(source: str) -> int | None:
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "API_VERSION" for t in node.targets)
            and isinstance(node.value, ast.Constant)
        ):
            return int(node.value.value)
    return None


@dataclass(frozen=True)
class Release:
    previous: str | None
    version: str
    title: str
    pr: int | None
    body: str
    old_db: str | None
    new_db: str
    old_api: int | None
    new_api: int | None

    def ledger_line(self) -> str:
        if self.previous is None or self.old_db is None:
            return "Ledger: prima release, nessun confronto."
        if self.old_db == self.new_db:
            return f"Ledger: {DB} invariato, il rollback a {self.previous} è il solo tag."
        before, after = migrations(self.old_db), migrations(self.new_db)
        added = after[len(before):] if after[: len(before)] == before else after
        if added:
            names = ", ".join(added)
            return (
                f"Ledger: {len(added)} nuove migrazioni ({names}), user_version "
                f"{len(before)} → {len(after)}. Irreversibile: il rollback a "
                f"{self.previous} è lo snapshot più il tag."
            )
        return (
            f"Ledger: {DB} cambia senza nuove migrazioni. Leggi il diff prima del "
            "deploy: una colonna o una tabella aggiunta da `initialize` è "
            "irreversibile, e allora il rollback è lo snapshot più il tag."
        )

    def api_line(self) -> str:
        if self.new_api is None:
            return "API_VERSION: non trovata."
        if self.old_api is None or self.old_api == self.new_api:
            return f"API_VERSION {self.new_api}, invariata."
        return f"API_VERSION {self.old_api} → {self.new_api}."

    def message(self) -> str:
        source = f"PR #{self.pr}" if self.pr else "push diretto su main"
        since = f"{self.previous}..{self.version}" if self.previous else self.version
        lines = [
            self.title.strip(),
            "",
            f"{source}, {since}.",
            self.api_line(),
            self.ledger_line(),
        ]
        if self.body.strip():
            lines += ["", self.body.strip()]
        return "\n".join(lines) + "\n"


def show(ref: str, path: str) -> str | None:
    try:
        return git("show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return None


def plan(part: str, title: str, pr: int | None, body: str) -> Release:
    previous = last_release(git("tag", "--list", "v*").split())
    old_db = show(previous, DB) if previous else None
    old_api_src = show(previous, VERSION) if previous else None
    new_api_src = show("HEAD", VERSION)
    return Release(
        previous=previous,
        version=bump(previous, part),
        title=title,
        pr=pr,
        body=body,
        old_db=old_db,
        new_db=show("HEAD", DB) or "",
        old_api=api_version(old_api_src) if old_api_src else None,
        new_api=api_version(new_api_src) if new_api_src else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bump", choices=BUMPS, default="patch")
    parser.add_argument("--title", required=True)
    parser.add_argument("--pr", type=int)
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--message-file", type=Path)
    args = parser.parse_args(argv)
    body = args.body_file.read_text(encoding="utf-8") if args.body_file else ""
    release = plan(args.bump, args.title, args.pr, body)
    print(f"version={release.version}")
    if args.message_file:
        args.message_file.write_text(release.message(), encoding="utf-8")
    else:
        print()
        print(release.message(), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
