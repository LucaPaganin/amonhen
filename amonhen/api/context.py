"""The application context the routers are built from."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException

from amonhen import db
from amonhen.config import MonitorConfig, load_config, setup_state
from amonhen.ledger import Ledger
from amonhen.ports.clock import Clock, SystemClock


@dataclass(frozen=True)
class AppContext:
    """What every router needs from the app that mounts it: where the ledger and the
    configuration live, and the two ways a request reaches them.

    It replaces the closure `create_app` used to be: the routes read `db_path`,
    `config_path` and `ledger_scope` from the function around them, and now read
    them from here, handed over once when the router is built."""

    db_path: str | Path
    config_path: str | Path
    # What day it is, for every figure that depends on it (`amonhen.ports.clock`).
    clock: Clock = field(default_factory=SystemClock)

    @contextmanager
    def ledger_scope(self) -> Iterator[Ledger]:
        """One connection per request, opened and closed on the same thread.

        A `yield` dependency would not do: FastAPI runs the setup and the
        teardown in the thread pool, and sqlite3 refuses a connection used from
        a different thread than the one that created it.
        """
        conn = db.connect(self.db_path)
        try:
            yield Ledger(conn)
        finally:
            conn.close()

    def credentials_or_409(self) -> MonitorConfig:
        """The configuration a bank call needs, or the reason it cannot be made.

        What a bank call needs is the application ID and a private key that
        loads — not an account list, because the first setup authorizes its
        first bank before any account is configured. Without this a fresh
        install answers 500 for a state the screen is about to collect.
        """
        state = setup_state(self.config_path)
        missing = [name for name in state["missing"] if name != "accounts"]
        if missing:
            raise HTTPException(
                status_code=409,
                detail=(
                    "no Enable Banking credentials yet: finish the first setup "
                    f"({', '.join(missing)} missing)"
                ),
            )
        try:
            return load_config(self.config_path)
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=409, detail=f"the configuration is not usable yet: {exc}"
            ) from exc
