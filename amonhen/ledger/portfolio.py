"""The portfolio's tables (desiderata 5.16): instruments, trades, the fund's contributions,
prices and the month-end snapshots.

None of it writes a posting. Persistence only — no rule of the portfolio lives here; the
arithmetic is in `core.portfolio` and `core.returns`, the order of the steps in
`services.portfolio`.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from decimal import Decimal

from amonhen.core.portfolio import INVESTED, KINDS, WITHHELD
from amonhen.models import format_decimal, parse_decimal


class PortfolioMixin:
    """One part of `Ledger`, which composes them: `self.conn` is the shared connection."""

    # -- instruments -------------------------------------------------------

    def add_instrument(
        self,
        name: str,
        kind: str,
        *,
        source: str,
        isin: str | None = None,
        fund_class: str | None = None,
        ownership: str = "1",
        horizon: str | None = None,
        terms: str | None = None,
    ) -> int:
        if kind not in KINDS:
            raise ValueError(f"tipo di strumento sconosciuto: {kind}")
        share = parse_decimal(ownership)
        if not share.is_finite() or not 0 < share <= 1:
            raise ValueError("la quota di proprietà è fra 0 e 1")
        if self.instrument(name) is not None:
            raise ValueError(f"lo strumento {name!r} esiste già")
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO instruments (name, kind, isin, class, source, ownership, horizon, terms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name.strip(), kind, isin, fund_class, source, str(share), horizon, terms),
            )
        return int(cursor.lastrowid)

    def instrument(self, name: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM instruments WHERE name = ?", (name,)).fetchone()

    def instruments(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM instruments ORDER BY name").fetchall()

    # -- trades ------------------------------------------------------------

    def record_trade(
        self, instrument_id: int, day: dt.date, units: Decimal, price: Decimal,
        amount: Decimal, fees: Decimal, source: str, reference: str,
    ) -> bool:
        """Write a trade the source reported; False when it was already there."""
        with self.conn:
            cursor = self.conn.execute(
                """INSERT OR IGNORE INTO instrument_trades
                       (instrument_id, date, units, price, amount, fees, source, reference)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (instrument_id, day.isoformat(), str(units), str(price), format_decimal(amount),
                 format_decimal(fees), source, reference),
            )
        return cursor.rowcount == 1

    def trades(self, instrument_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM instrument_trades WHERE instrument_id = ? ORDER BY date, id", (instrument_id,)
        ).fetchall()

    # -- the pension fund's contributions -----------------------------------

    def withhold(self, instrument_id: int, period: str, own: Decimal, employer: Decimal,
                 tfr: Decimal, payslip: str) -> bool:
        """A payslip's contribution, born withheld; False when that payslip was already read."""
        with self.conn:
            cursor = self.conn.execute(
                """INSERT OR IGNORE INTO pension_contributions
                       (instrument_id, period, own, employer, tfr, state, payslip)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (instrument_id, period, format_decimal(own), format_decimal(employer),
                 format_decimal(tfr), WITHHELD, payslip),
            )
        return cursor.rowcount == 1

    def invest_directly(self, instrument_id: int, day: dt.date, own: Decimal, unit_value: Decimal,
                        units: Decimal) -> int:
        """A payment made straight to the fund, with no payslip: born invested, on its own date."""
        with self.conn:
            cursor = self.conn.execute(
                """INSERT INTO pension_contributions
                       (instrument_id, period, own, employer, tfr, state, value_date, unit_value, units)
                   VALUES (?, ?, ?, '0.00', '0.00', ?, ?, ?, ?)""",
                (instrument_id, day.isoformat()[:7], format_decimal(own), INVESTED, day.isoformat(),
                 str(unit_value), str(units)),
            )
        return int(cursor.lastrowid)

    def invest(self, contribution_id: int, value_date: dt.date, unit_value: Decimal, units: Decimal) -> None:
        """A withheld contribution a statement has shown: its value date, unit value and units."""
        with self.conn:
            self.conn.execute(
                """UPDATE pension_contributions SET state = ?, value_date = ?, unit_value = ?, units = ?
                   WHERE id = ? AND state = ?""",
                (INVESTED, value_date.isoformat(), str(unit_value), str(units), contribution_id, WITHHELD),
            )

    def contributions(self, instrument_id: int) -> list[sqlite3.Row]:
        """Oldest first: the order a statement's batches are matched in."""
        return self.conn.execute(
            "SELECT * FROM pension_contributions WHERE instrument_id = ? ORDER BY period, id",
            (instrument_id,),
        ).fetchall()

    # -- prices ------------------------------------------------------------

    def set_price(self, instrument_id: int, day: dt.date, value: Decimal, source: str) -> None:
        """One value per instrument and day; a later one from the same day replaces it."""
        if value <= 0:
            raise ValueError("un prezzo è positivo")
        with self.conn:
            self.conn.execute(
                """INSERT INTO prices (instrument_id, date, value, source) VALUES (?, ?, ?, ?)
                   ON CONFLICT (instrument_id, date) DO UPDATE SET
                       value = excluded.value, source = excluded.source""",
                (instrument_id, day.isoformat(), str(value), source),
            )

    def price_at(self, instrument_id: int, day: dt.date) -> sqlite3.Row | None:
        """The price written for exactly ``day``: a missing one is said, never borrowed."""
        return self.conn.execute(
            "SELECT * FROM prices WHERE instrument_id = ? AND date = ?", (instrument_id, day.isoformat())
        ).fetchone()

    def latest_price(self, instrument_id: int, on_or_before: dt.date) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM prices WHERE instrument_id = ? AND date <= ? ORDER BY date DESC LIMIT 1",
            (instrument_id, on_or_before.isoformat()),
        ).fetchone()

    # -- documents ---------------------------------------------------------

    def document(self, paperless_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM documents WHERE paperless_id = ?", (paperless_id,)).fetchone()

    def failed_documents(self, kind: str) -> list[int]:
        return [row["paperless_id"] for row in self.conn.execute(
            "SELECT paperless_id FROM documents WHERE kind = ? AND outcome = 'errore' ORDER BY paperless_id", (kind,))]

    def record_document(self, paperless_id: int, kind: str, outcome: str, layout: str | None,
                        error: str | None) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO documents (paperless_id, kind, read_at, outcome, layout, error)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (paperless_id) DO UPDATE SET read_at = excluded.read_at,
                       outcome = excluded.outcome, layout = excluded.layout, error = excluded.error""",
                (paperless_id, kind, dt.datetime.now(dt.UTC).isoformat(), outcome, layout, error),
            )

    # -- snapshots ---------------------------------------------------------

    def save_snapshot(self, month: str, instrument_id: int, units: Decimal, value: Decimal, paid: Decimal) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO portfolio_snapshots (month, instrument_id, units, value, paid)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (month, instrument_id) DO UPDATE SET
                       units = excluded.units, value = excluded.value, paid = excluded.paid""",
                (month, instrument_id, str(units), format_decimal(value), format_decimal(paid)),
            )

    def snapshots(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY month, instrument_id"
        ).fetchall()

    # -- what the ledger holds that the portfolio reads -----------------------

    def liquidity_on(self, day: dt.date) -> Decimal:
        """The cash of every real account on a date, by the ledger's own arithmetic.

        The same sum `compute_metrics` calls liquidity: the portfolio is never part of it.
        """
        return sum(
            (self.balance(row["id"], day) for row in
             self.conn.execute("SELECT id FROM accounts WHERE type = 'real'")),
            Decimal(0),
        )

    def credits_between(self, account_name: str, start: dt.date, end: dt.date, text: str) -> list[tuple[dt.date, Decimal]]:
        """Money that came in on an account in a window whose description holds ``text``."""
        return self._movements_between(account_name, start, end, text, "> 0")

    def debits_between(self, account_name: str, start: dt.date, end: dt.date, text: str) -> list[tuple[dt.date, Decimal]]:
        """Money that went out of an account in a window whose description holds ``text`` (negative)."""
        return self._movements_between(account_name, start, end, text, "< 0")

    def _movements_between(self, account_name: str, start: dt.date, end: dt.date, text: str,
                           sign: str) -> list[tuple[dt.date, Decimal]]:
        rows = self.conn.execute(
            f"""SELECT t.date, t.amount FROM transactions t JOIN accounts a ON a.id = t.account_id
               WHERE a.name = ? AND t.date >= ? AND t.date <= ?
                 AND CAST(t.amount AS REAL) {sign} AND LOWER(t.description) LIKE ?""",
            (account_name, start.isoformat(), end.isoformat(), f"%{text.lower()}%"),
        )
        return [(dt.date.fromisoformat(row["date"]), parse_decimal(row["amount"])) for row in rows]

    def trades_total(self, instrument_id: int) -> Decimal:
        """Everything paid in trades, fees included, as the ledger's PAC transfers are compared to."""
        return sum(
            (parse_decimal(row["amount"]) + parse_decimal(row["fees"]) for row in self.trades(instrument_id)),
            Decimal(0),
        )
