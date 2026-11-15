"""Balances: the double-entry check, spending, balances as of a date, declarations, section 5.4, the opening."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from decimal import Decimal

from amonhen.ledger.definitions import (
    BalanceCheck,
    COUNTED_SOURCES_SQL,
    FORECAST_SOURCES_SQL,
    INVESTMENTS_ACCOUNT,
    SPENDING_SQL,
    UNRECOGNIZED_SOURCES_SQL,
    VALUATION_PREFIX,
    _declaration_order,
    balance_kind,
)
from amonhen.models import Account, format_decimal, parse_decimal


class BalancesMixin:
    """Balances: the double-entry check, spending, balances as of a date, declarations, section 5.4, the opening.

    One part of `Ledger`, which composes them: the methods use `self.conn` and call
    each other through `self`, whatever part they are in."""

    # -- invariants and reporting -----------------------------------------

    def unbalanced(self) -> list[int]:
        totals: dict[int, Decimal] = {}
        counts: dict[int, int] = {}
        for row in self.conn.execute("SELECT transaction_id, amount FROM postings"):
            totals[row["transaction_id"]] = totals.get(row["transaction_id"], Decimal(0)) + parse_decimal(row["amount"])
            counts[row["transaction_id"]] = counts.get(row["transaction_id"], 0) + 1
        ids = set(totals) | set(counts) | {row["id"] for row in self.conn.execute("SELECT id FROM transactions")}
        return sorted(
            tid for tid in ids
            if totals.get(tid, Decimal(0)) != 0 or counts.get(tid, 0) < 2
        )

    def validate(self) -> None:
        broken = self.unbalanced()
        if broken:
            raise ValueError(f"transactions whose postings do not sum to zero: {broken}")

    def spend_between(self, start: dt.date, end: dt.date) -> Decimal:
        """Money actually spent in the period: category postings, so transfers are out.

        A refund, money in on a category that is not income, takes it down
        (`SPENDING_SQL`); a salary or a credit nobody decided does not.
        """
        total = Decimal(0)
        for row in self.conn.execute(
            f"""SELECT p.amount FROM postings p
               JOIN transactions t ON t.id = p.transaction_id
               JOIN accounts a ON a.id = p.account_id
               WHERE a.type = 'category' AND t.status = 'BOOK'
                 AND {SPENDING_SQL}
                 AND t.date >= ? AND t.date <= ?""",
            (start.isoformat(), end.isoformat()),
        ):
            total += parse_decimal(row["amount"])
        return total

    def movement(self, account_id: int, as_of: dt.date, *, settled: bool = False) -> Decimal:
        """Sum of the postings on the account up to the date, opening excluded.

        `settled=True` leaves the pending movements out — the same split the two
        declared figures make. An opening derived from one of them has to be
        derived with the postings that figure contains, or the pending sum ends
        up folded into the opening.
        """
        return self._postings_sum(account_id, as_of, settled=settled)

    def balance(self, account_id: int, as_of: dt.date, *, settled: bool = False) -> Decimal:
        """What the account holds on the date, by the ledger's own arithmetic.

        The bank declares two figures for the same date and they differ by the
        pending movements: `settled=False` counts them, matching its *available*
        balance, while `settled=True` leaves them out for its *booked* one.
        """
        account = self.account(account_id)
        opening = parse_decimal(account["opening_balance"]) if account["opening_balance"] else Decimal(0)
        return opening + self._postings_sum(
            account_id, as_of, after=account["opening_date"], settled=settled
        )

    def _postings_sum(self, account_id: int, as_of: dt.date, *, after: str | None = None,
                      settled: bool = False) -> Decimal:
        """The postings up to the date, optionally only those after an opening date.

        One query behind both figures, so `movement` and `balance` cannot drift
        apart: the invariant is their difference, and it is nonsense if the two
        sides count different movements.
        """
        total = Decimal(0)
        for row in self.conn.execute(
            """SELECT p.amount FROM postings p
               JOIN transactions t ON t.id = p.transaction_id
               WHERE p.account_id = ? AND t.date <= ?
                 AND (? IS NULL OR t.date > ?)
                 AND (? = 0 OR t.status = 'BOOK')""",
            (account_id, as_of.isoformat(), after, after, 1 if settled else 0),
        ):
            total += parse_decimal(row["amount"])
        return total

    def check_balance(
        self,
        account_id: int,
        declared: Decimal,
        as_of: dt.date,
        *,
        kind: str = "available",
        source: str = "",
    ) -> BalanceCheck:
        account = self.account(account_id)
        opening = parse_decimal(account["opening_balance"]) if account["opening_balance"] else Decimal(0)
        deleted = self.deleted_total(account_id, as_of, kind)
        return BalanceCheck(
            account_id=account_id,
            as_of=as_of,
            opening=opening,
            declared=declared,
            computed=self.balance(account_id, as_of, settled=kind == "booked"),
            kind=kind,
            source=source,
            suppressed=deleted.amount,
            suppressed_count=deleted.count,
        )

    def declarations(self, account_id: int, as_of: dt.date | None = None) -> list[sqlite3.Row]:
        """Every counted balance declared for the account, optionally up to a date."""
        sql = (
            f"SELECT date, balance, source FROM account_balances WHERE account_id = ?"
            f" AND {COUNTED_SOURCES_SQL}"
        )
        params: list = [account_id]
        if as_of is not None:
            sql += " AND date <= ?"
            params.append(as_of.isoformat())
        return list(self.conn.execute(sql, params))

    def unrecognized_balances(self, account_id: int) -> list[sqlite3.Row]:
        """Each balance type the bank declared that nothing reads, at its newest date.

        The rows are kept: they are the evidence for adding the type to the list,
        and for as long as nobody has, Conti says the account has them.
        """
        return self.conn.execute(
            f"""SELECT source, balance, MAX(date) AS date FROM account_balances
                WHERE account_id = ? AND {UNRECOGNIZED_SOURCES_SQL}
                GROUP BY source ORDER BY source""",
            (account_id,),
        ).fetchall()

    def overdraft_forecast(self, account_id: int, today: dt.date) -> sqlite3.Row | None:
        """The bank's furthest forecast for the account, when it has it below zero.

        An advisory about what may happen, never a state of the account: its
        balance and its check are what they are.
        """
        row = self.conn.execute(
            f"""SELECT date, balance FROM account_balances
                WHERE account_id = ? AND source IN {FORECAST_SOURCES_SQL} AND date >= ?
                ORDER BY date DESC LIMIT 1""",
            (account_id, today.isoformat()),
        ).fetchone()
        return row if row is not None and parse_decimal(row["balance"]) < 0 else None

    def declaration_for(self, account_id: int, as_of: dt.date) -> sqlite3.Row | None:
        """The declaration to assert against for that date: the newest, deterministically."""
        rows = self.declarations(account_id, as_of)
        return max(rows, key=_declaration_order) if rows else None

    def declared_checks(self, account_id: int) -> list[BalanceCheck]:
        """The newest declaration of each kind, each against the figure that means the same.

        One check per kind at most, and never a choice between two rows of the
        same date made by row order: that is what turned a booked balance into a
        difference the size of the pending movements.
        """
        newest: dict[str, sqlite3.Row] = {}
        for row in self.declarations(account_id):
            kind = balance_kind(row["source"])
            if kind not in newest or _declaration_order(row) > _declaration_order(newest[kind]):
                newest[kind] = row
        return [
            self.check_balance(
                account_id,
                parse_decimal(row["balance"]),
                dt.date.fromisoformat(row["date"]),
                kind=kind,
                source=row["source"],
            )
            for kind, row in sorted(newest.items())
        ]

    def record_declared_balance(self, account_id: int, date: dt.date, balance: Decimal, source: str) -> None:
        """Record what was declared for the account on that date.

        A figure a person wrote (`manual:` or `anchor:`) replaces any other one
        of the same kind on the same date: they are one statement about one day,
        and nothing in the row says which was written last, so keeping both left
        the older one winning the tie — a corrected declaration was ignored and
        *Allinea* then anchored to the stale figure. The bank's own rows are
        never touched.
        """
        with self.conn:
            if not source.startswith("eb:"):
                kind = balance_kind(source)
                for row in self.conn.execute(
                    "SELECT source FROM account_balances WHERE account_id = ? AND date = ?"
                    " AND source <> ? AND source NOT LIKE 'eb:%'",
                    (account_id, date.isoformat(), source),
                ).fetchall():
                    if balance_kind(row["source"]) == kind:
                        self.conn.execute(
                            "DELETE FROM account_balances WHERE account_id = ? AND date = ? AND source = ?",
                            (account_id, date.isoformat(), row["source"]),
                        )
            self.conn.execute(
                """INSERT INTO account_balances (account_id, date, balance, source)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (account_id, date, source) DO UPDATE SET
                       balance = excluded.balance""",
                (account_id, date.isoformat(), format_decimal(balance), source),
            )

    def opening_from(
        self, account_id: int, as_of: dt.date, declared: Decimal, kind: str
    ) -> tuple[Decimal, dt.date]:
        """The opening that makes the declared figure hold, without writing it.

        Everything the bank reported up to then is already inside the declared
        balance — the pending movements only if the declared figure contains them
        too, which is what ``kind`` says. The movement is opening-independent, so
        the answer does not depend on the opening already written.

        ``opening_balance`` is the balance *before* ``opening_date`` and
        ``balance()`` adds only the postings strictly after it, so the opening is
        dated the day before the first movement. The app asks this first and
        shows what anchoring would move, because an anchor folds any difference
        into the opening, where the 5.4 check can no longer see it.
        """
        opening = declared - self.movement(account_id, as_of, settled=kind == "booked")
        first = self.conn.execute(
            "SELECT MIN(date) AS first FROM transactions WHERE account_id = ? AND date <= ?",
            (account_id, as_of.isoformat()),
        ).fetchone()["first"]
        opening_date = dt.date.fromisoformat(first) - dt.timedelta(days=1) if first else as_of
        return opening, opening_date

    def record_valuation(
        self, account_id: int, date: dt.date, value: Decimal
    ) -> tuple[Decimal, int | None]:
        """Say how much cash a broker's account holds on a date, and book the difference.

        The account holds the cash and nothing else: the portfolio is not tracked
        (desiderata 5.8). Its movements are the money that went in and out, and what
        was bought, sold or earned is in none of them, so the difference between the
        declared cash and the ledger's balance on that date is written as a movement
        of its own, against `Investimenti`: the balance agrees, and being a virtual
        posting it is neither income nor spending. The figure is also recorded as the
        account's declaration, so the check reads it. A second declaration on the
        same day replaces the first. Returns the difference and the movement's id
        (None when the balance already agreed).
        """
        account = self.account(account_id)
        if account["type"] != "real" or not account["investment"]:
            raise ValueError(f"{account['name']!r} is not an investment account")
        if account["external_uid"] is not None:
            raise ValueError(
                f"{account['name']!r} is connected to a bank, which reports what it holds"
            )
        key = f"{VALUATION_PREFIX}{account_id}:{date.isoformat()}"
        investments = self.ensure_account(Account(name=INVESTMENTS_ACCOUNT, type="virtual"))
        with self.conn:
            self.conn.execute("DELETE FROM transactions WHERE content_hash = ?", (key,))
            difference = value - self.balance(account_id, date)
            transaction_id = None
            if difference != 0:
                cursor = self.conn.execute(
                    """INSERT INTO transactions (
                           account_id, date, amount, description, status, external_id,
                           content_hash, source, source_file, raw_payload, currency, created_at
                       ) VALUES (?, ?, ?, ?, 'BOOK', NULL, ?, 'import', NULL, ?, 'EUR', ?)""",
                    (
                        account_id, date.isoformat(), format_decimal(difference),
                        "Aggiornamento liquidità", key,
                        json.dumps({"value": format_decimal(value)}),
                        dt.datetime.now(dt.UTC).isoformat(),
                    ),
                )
                transaction_id = int(cursor.lastrowid)
                self.conn.executemany(
                    "INSERT INTO postings (transaction_id, account_id, amount) VALUES (?, ?, ?)",
                    [
                        (transaction_id, account_id, format_decimal(difference)),
                        (transaction_id, investments, format_decimal(-difference)),
                    ],
                )
            self.record_declared_balance(account_id, date, value, "manual:available")
        return difference, transaction_id

    def anchor_opening(
        self, account_id: int, as_of: dt.date, declared: Decimal, kind: str
    ) -> tuple[Decimal, dt.date]:
        """Set the opening so the declared figure holds on the date it refers to.

        `opening_from`, written; anchoring twice changes nothing. Returns what it
        wrote, because the command line and the app both print it.
        """
        opening, opening_date = self.opening_from(account_id, as_of, declared, kind)
        with self.conn:
            self.conn.execute(
                "UPDATE accounts SET opening_balance = ?, opening_date = ? WHERE id = ?",
                (format_decimal(opening), opening_date.isoformat(), account_id),
            )
        return opening, opening_date
