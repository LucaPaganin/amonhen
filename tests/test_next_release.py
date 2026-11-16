"""The next release's tag and message, computed by `tools/next_release.py`."""

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "tools" / "next_release.py"
_SPEC = importlib.util.spec_from_file_location("next_release", _PATH)
next_release = importlib.util.module_from_spec(_SPEC)
sys.modules["next_release"] = next_release  # a dataclass looks its module up there
_SPEC.loader.exec_module(next_release)

DB_V1 = "MIGRATIONS = (\n    _a,\n    _b,\n)\n"
DB_V2 = "MIGRATIONS = (\n    _a,\n    _b,\n    _c,\n)\n"


def release(**changes):
    fields = dict(
        previous="v1.19.0",
        version="v1.19.1",
        title="Un titolo",
        pr=7,
        body="",
        old_db=DB_V1,
        new_db=DB_V1,
        old_api=42,
        new_api=42,
    )
    fields.update(changes)
    return next_release.Release(**fields)


def test_the_last_release_is_the_highest_by_number_not_by_text():
    tags = ["v1.9.5", "v1.19.0", "v1.10.2", "nightly", "v2.0.0-rc1"]
    assert next_release.last_release(tags) == "v1.19.0"


@pytest.mark.parametrize(
    ("part", "expected"),
    [("patch", "v1.19.1"), ("minor", "v1.20.0"), ("major", "v2.0.0")],
)
def test_bump(part, expected):
    assert next_release.bump("v1.19.0", part) == expected


def test_the_first_release_starts_from_nothing():
    assert next_release.bump(None, "minor") == "v0.1.0"


def test_migrations_are_read_without_importing():
    assert next_release.migrations(DB_V2) == ["_a", "_b", "_c"]


def test_an_unchanged_ledger_rolls_back_with_the_tag_alone():
    assert "il solo tag" in release().ledger_line()


def test_a_new_migration_is_called_one_way():
    line = release(new_db=DB_V2).ledger_line()
    assert "1 nuove migrazioni (_c)" in line
    assert "user_version 2 → 3" in line
    assert "snapshot più il tag" in line


def test_a_schema_change_without_a_migration_asks_to_read_the_diff():
    line = release(new_db=DB_V1 + "\nSCHEMA = 'x'\n").ledger_line()
    assert "Leggi il diff" in line


def test_the_message_names_the_pr_the_range_and_the_api():
    message = release(new_api=43, body="Il corpo della PR.").message()
    assert message.splitlines()[0] == "Un titolo"
    assert "PR #7, v1.19.0..v1.19.1." in message
    assert "API_VERSION 42 → 43." in message
    assert message.rstrip().endswith("Il corpo della PR.")


def test_the_real_db_module_has_its_migrations_read():
    source = (_PATH.parents[1] / "amonhen" / "db.py").read_text(encoding="utf-8")
    names = next_release.migrations(source)
    assert names and names[0] == "_add_income_flag"
