"""HTTP API and the host for the mobile PWA.

The surface is deliberately small: the two screens of phase 2 need a
filterable transaction list, the review queue, category changes and the
confirm/reject decision on a transfer link. No authentication: the app is
served behind Tailscale, and the ledger never leaves the machine."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from amonhen import db
from amonhen.api.context import AppContext
from amonhen.ports.clock import Clock, SystemClock
from amonhen.api.routes import (
    accounts,
    budgets,
    categories,
    dashboard,
    imports,
    plan,
    portfolio,
    review,
    setup,
    sync,
    transactions,
    transfers,
)
from amonhen.settings import CONFIG_FILE, DB_PATH

# The built PWA, at the repository root: this file is amonhen/api/app.py.
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def create_app(
    db_path: str | Path = DB_PATH,
    web_dist: Path | None = None,
    config_path: str | Path = CONFIG_FILE,
    clock: Clock | None = None,
) -> FastAPI:
    startup = db.connect(db_path)
    db.initialize(startup)
    startup.close()
    app = FastAPI(title="finance-monitor", docs_url=None, redoc_url=None)

    @app.exception_handler(ValueError)
    async def invalid_value(_request, exc: ValueError) -> JSONResponse:
        # The ledger validates names and amounts; a bad value is the caller's
        # problem, not a server error. ArithmeticError covers a malformed
        # decimal string from parse_decimal.
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ArithmeticError)
    async def invalid_number(_request, exc: ArithmeticError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": f"invalid number: {exc}"})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, exc: RequestValidationError) -> JSONResponse:
        """A malformed request, described without repeating what it carried.

        Pydantic's own answer echoes the whole body under `input`, and one of
        these bodies is a pasted private key: describing the offending field is
        what the client shows anyway, and it is all it needs.
        """
        problems = [
            f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422, content={"detail": "invalid request: " + "; ".join(problems)}
        )

    # The composition of the API: one context, every router built from it, in the
    # order the routes used to be declared, then the PWA as the catch-all.
    ctx = AppContext(db_path=db_path, config_path=config_path, clock=clock or SystemClock())
    app.include_router(setup.build(ctx))
    app.include_router(dashboard.build(ctx))
    app.include_router(accounts.build(ctx))
    app.include_router(categories.build(ctx))
    app.include_router(budgets.build(ctx))
    app.include_router(review.build(ctx))
    app.include_router(transactions.build(ctx))
    app.include_router(transfers.build(ctx))
    app.include_router(sync.build(ctx))
    app.include_router(imports.build(ctx))
    app.include_router(plan.build(ctx))
    app.include_router(portfolio.build(ctx))
    _mount_pwa(app, web_dist if web_dist is not None else WEB_DIST)
    return app


def _mount_pwa(app: FastAPI, web_dist: Path) -> None:
    if not web_dist.exists():
        return
    assets = web_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (web_dist / path).resolve()
        # The shell names the assets, and a deploy replaces them with new names:
        # a document served from a cache points at files that no longer exist and
        # the app comes up blank. `no-cache` is "ask before using", so the
        # revalidation still answers 304 when nothing changed.
        headers = {"Cache-Control": "no-cache"}
        if path and candidate.is_file() and web_dist.resolve() in candidate.parents:
            return FileResponse(candidate, headers=headers)
        return FileResponse(web_dist / "index.html", headers=headers)
