"""Goals, the profile and the tax years (desiderata 5.16): what a person writes by hand to plan."""
from __future__ import annotations

import datetime as dt
import sqlite3

from amonhen.core.planning import LIQUIDITY, PROFILE_KEYS, TAX_KEYS, checked
from amonhen.models import format_decimal, parse_decimal


class PlanningMixin:
    """One part of `Ledger`: the tables of the plan, which no posting ever reads."""

    # -- goals -------------------------------------------------------------

    def goals_at(self, day: dt.date) -> list[sqlite3.Row]:
        """The goals as they stood on ``day``, the nearest first."""
        return self.conn.execute(
            """SELECT * FROM goals WHERE valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)
               ORDER BY target_date, name""",
            (day.isoformat(), day.isoformat()),
        ).fetchall()

    def save_goal(
        self,
        series: int | None,
        name: str,
        amount: str,
        target_date: dt.date,
        liquidity: str,
        valid_from: dt.date,
    ) -> int:
        """Write a goal from ``valid_from`` on; returns its series.

        A change replaces any later version too, as a budget default does: what is
        written from a day on is what holds from that day on.
        """
        name = name.strip()
        if not name:
            raise ValueError("un obiettivo ha un nome")
        if liquidity not in LIQUIDITY:
            raise ValueError(f"liquidità sconosciuta: {liquidity}")
        value = parse_decimal(amount)
        if not value.is_finite() or value <= 0:
            raise ValueError("la cifra di un obiettivo è positiva")
        row = (name, format_decimal(value), target_date.isoformat(), liquidity, valid_from.isoformat())
        with self.conn:
            if series is not None:
                self._end_goal(series, valid_from)
                self.conn.execute(
                    """INSERT INTO goals (series, name, amount, target_date, liquidity, valid_from)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (series, *row),
                )
                return series
            cursor = self.conn.execute(
                "INSERT INTO goals (name, amount, target_date, liquidity, valid_from) VALUES (?, ?, ?, ?, ?)",
                row,
            )
            self.conn.execute("UPDATE goals SET series = id WHERE id = ?", (cursor.lastrowid,))
            return int(cursor.lastrowid)

    def end_goal(self, series: int, day: dt.date) -> None:
        """The goal stops holding on ``day``; the days before keep it."""
        with self.conn:
            self._end_goal(series, day)

    def _end_goal(self, series: int, day: dt.date) -> None:
        if self.conn.execute("SELECT 1 FROM goals WHERE series = ?", (series,)).fetchone() is None:
            raise LookupError(f"nessun obiettivo {series}")
        self.conn.execute("DELETE FROM goals WHERE series = ? AND valid_from >= ?", (series, day.isoformat()))
        self.conn.execute(
            "UPDATE goals SET valid_to = ? WHERE series = ? AND (valid_to IS NULL OR valid_to > ?)",
            (day.isoformat(), series, day.isoformat()),
        )

    # -- profile -----------------------------------------------------------

    def profile_at(self, day: dt.date) -> dict[str, sqlite3.Row]:
        """Each fact as it stood on ``day``, by key; a fact not yet written is absent."""
        rows = self.conn.execute(
            """SELECT key, value, valid_from FROM profile_facts p
               WHERE valid_from = (SELECT MAX(valid_from) FROM profile_facts
                                   WHERE key = p.key AND valid_from <= ?)""",
            (day.isoformat(),),
        )
        return {row["key"]: row for row in rows}

    def set_profile_fact(self, key: str, value: str, valid_from: dt.date) -> None:
        """A fact true from ``valid_from`` on, replacing what was written for later."""
        if key not in PROFILE_KEYS:
            raise ValueError(f"fatto del profilo sconosciuto: {key}")
        value = checked(PROFILE_KEYS[key][1], value)
        with self.conn:
            self.conn.execute(
                "DELETE FROM profile_facts WHERE key = ? AND valid_from >= ?", (key, valid_from.isoformat())
            )
            self.conn.execute(
                "INSERT INTO profile_facts (key, value, valid_from) VALUES (?, ?, ?)",
                (key, value, valid_from.isoformat()),
            )

    # -- tax years ---------------------------------------------------------

    def tax_parameters(self) -> dict[int, dict[str, sqlite3.Row]]:
        """Every year written, each with its values and their sources."""
        years: dict[int, dict[str, sqlite3.Row]] = {}
        for row in self.conn.execute("SELECT * FROM tax_parameters ORDER BY year, key"):
            years.setdefault(row["year"], {})[row["key"]] = row
        return years

    def set_tax_parameter(self, year: int, key: str, value: str, source: str) -> None:
        if key not in TAX_KEYS:
            raise ValueError(f"parametro fiscale sconosciuto: {key}")
        if not source.strip():
            raise ValueError("ogni parametro fiscale porta la sua fonte")
        value = checked(TAX_KEYS[key][1], value)
        with self.conn:
            self.conn.execute(
                """INSERT INTO tax_parameters (year, key, value, source) VALUES (?, ?, ?, ?)
                   ON CONFLICT (year, key) DO UPDATE SET value = excluded.value, source = excluded.source""",
                (year, key, value, source.strip()),
            )

    def delete_tax_parameter(self, year: int, key: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM tax_parameters WHERE year = ? AND key = ?", (year, key))
