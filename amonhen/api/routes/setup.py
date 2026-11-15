"""The consent flow and the first setup (desiderata 7 and 5.10)."""
from __future__ import annotations

import json

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from amonhen.adapters.enable_banking.client import ConsentExpiredError, session_accounts
from amonhen.api.context import AppContext
from amonhen.api.payloads import (
    PENDING_OAUTH,
    SETUP_LAST_CONNECT,
    _auth_refusal,
    _last_connect,
    _shape,
    _suggested_name,
    _upstream_refusal,
    log,
)
from amonhen.api.schemas import SetupAccountRequest, SetupConnectRequest, SetupCredentialsRequest
from amonhen.composition import enable_banking_client
from amonhen.config import (
    UnknownConfiguredAccount,
    remove_account,
    rename_account,
    save_account,
    save_credentials,
    setup_state,
)


def build(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    clock = ctx.clock
    config_path = ctx.config_path
    ledger_scope = ctx.ledger_scope
    credentials_or_409 = ctx.credentials_or_409

    def start_authorization(bank: str, country: str, psu_type: str) -> str:
        """Ask Enable Banking for an authorization URL and remember the state.

        The two callers differ only in what the browser does with the answer:
        `/connect` redirects to it, and the setup screen navigates to it in the
        same tab, because the return has to land inside the app.
        """
        config = credentials_or_409()
        client = enable_banking_client(config)
        try:
            state, valid_until, url = client.start_auth(bank, country, psu_type)
        except requests.HTTPError as exc:
            # The bank rejects an ASPSP name it does not know: say so, rather
            # than turning it into a server error.
            raise HTTPException(
                status_code=502,
                detail=_auth_refusal(exc, config.redirect_url),
            ) from exc
        with ledger_scope() as ledger:
            ledger.set_setting(
                PENDING_OAUTH,
                json.dumps(
                    {
                        "state": state,
                        "bank": bank,
                        "country": country,
                        "valid_until": valid_until,
                        "created_at": clock.now().isoformat(),
                    }
                ),
            )
        return url

    @router.get("/connect")
    def connect(bank: str, country: str, psu_type: str = "personal") -> RedirectResponse:
        return RedirectResponse(start_authorization(bank, country, psu_type), status_code=302)

    @router.get("/callback")
    def callback(code: str, state: str) -> RedirectResponse:
        with ledger_scope() as ledger:
            pending = ledger.setting(PENDING_OAUTH)
            if not pending:
                raise HTTPException(status_code=400, detail="no authorization was started")
            request = json.loads(pending)
            if request.get("state") != state:
                raise HTTPException(status_code=400, detail="the authorization state does not match")
            config = credentials_or_409()
            client = enable_banking_client(config)
            try:
                session = client.complete_auth(code, state)
            except requests.HTTPError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Enable Banking refused the session: {_upstream_refusal(exc)}",
                ) from exc
            session_id = session.get("session_id")
            connected = session_accounts(session)
            described: object = None
            if not connected and session_id:
                # The answer to the login can arrive before the accounts do: the
                # session itself is asked once more before calling it empty.
                try:
                    described = client.get_session(session_id)
                    connected = session_accounts(described) if isinstance(described, dict) else []
                except requests.RequestException as exc:
                    described = f"unreadable: {exc}"
            if connected:
                log.info(
                    "Enable Banking session for %s: keys %s, accounts %s, accounts_data %s, kept %d",
                    request.get("bank"),
                    sorted(session),
                    _shape(session.get("accounts")),
                    _shape(session.get("accounts_data")),
                    len(connected),
                )
            else:
                # A consent that shared nothing is the case someone has to debug,
                # and the server logs only warnings: both answers go in whole.
                # They carry the session's status and access, uids at most — no
                # token, no movement.
                log.warning(
                    "Enable Banking session for %s shared no account. POST /sessions: %s"
                    " — GET /sessions/%s: %s",
                    request.get("bank"),
                    json.dumps(session, default=str),
                    session_id,
                    json.dumps(described, default=str),
                )
            written = []
            for account in connected:
                entry = {
                    "session_id": session_id,
                    "account_uid": account.get("uid"),
                    "bank_name": request.get("bank"),
                    "country": request.get("country"),
                    "notes": account.get("name")
                    or _suggested_name(client, account.get("uid"), request.get("bank")),
                    "start_sync_date": clock.today().isoformat(),
                    # Enable Banking reports when this consent stops working, and
                    # the file is where a person looks before re-authorizing.
                    "session_expiry": request.get("valid_until"),
                }
                action, name = save_account(config_path, entry)
                written.append({"account": name, "action": action})
            ledger.set_setting(PENDING_OAUTH, "")
            # Which entries were refreshed and which were added: a bank that
            # returns several accounts writes several, and the setup screen
            # keeps the ones wanted before the sync imports them all. It is read
            # back from `/api/setup`, because what the browser gets here is a
            # redirect into the app rather than a JSON document nobody sees.
            ledger.set_setting(
                SETUP_LAST_CONNECT,
                json.dumps(
                    {
                        "when": clock.now().isoformat(),
                        "written": written,
                        # Kept so an empty consent can be asked about again.
                        "session_id": session_id,
                    }
                ),
            )
        return RedirectResponse("/?setup=1", status_code=303)
    # -- first setup (desiderata 5.10) --------------------------------------

    def setup_payload() -> dict:
        with ledger_scope() as ledger:
            payload = setup_state(config_path)
            payload["last_connect"] = _last_connect(ledger)
        return payload

    @router.get("/api/setup")
    def setup() -> dict:
        return setup_payload()

    @router.put("/api/setup/credentials")
    def write_credentials(request: SetupCredentialsRequest) -> dict:
        try:
            save_credentials(
                config_path,
                application_id=request.application_id,
                redirect_url=request.redirect_url,
                account_holder_name=request.account_holder_name,
                private_key=request.private_key,
            )
        except OSError as exc:
            # A folder the container's user cannot write in is the first setup's
            # likeliest failure, and it deserves its own words rather than a 500.
            raise HTTPException(
                status_code=503, detail=f"the configuration could not be written: {exc}"
            ) from exc
        return setup_payload()

    @router.get("/api/setup/banks")
    def setup_banks(country: str = "IT") -> dict:
        """The banks Enable Banking knows in one country, by exact name.

        `/connect` takes the ASPSP name character for character, and a screen
        that asks a person to remember it is asking them to get it wrong.
        """
        config = credentials_or_409()
        try:
            banks = enable_banking_client(config).list_banks()
        except (requests.HTTPError, ConsentExpiredError) as exc:
            # The client reports a refused credential two ways — an HTTPError
            # from a status code, a ConsentExpiredError from 401/403 — and both
            # are the bank's answer, not a server error.
            raise HTTPException(
                status_code=502,
                detail=f"Enable Banking refused the request: {_upstream_refusal(exc)}",
            ) from exc
        wanted = country.strip().upper()
        return {
            "country": wanted,
            "banks": sorted(
                (
                    {"name": bank["name"], "country": bank.get("country") or ""}
                    for bank in banks
                    if (bank.get("country") or "").upper() == wanted
                ),
                key=lambda bank: bank["name"],
            ),
        }

    @router.post("/api/setup/connect")
    def setup_connect(request: SetupConnectRequest) -> dict:
        return {"url": start_authorization(request.bank, request.country, "personal")}

    @router.patch("/api/setup/accounts/{account_uid}")
    def rename_configured_account(account_uid: str, request: SetupAccountRequest) -> dict:
        """Rename a connected account in `accounts.json` and in the ledger at once.

        The ledger knows a connected account by its uid, so the account it already
        holds takes the new name now instead of keeping the first one; a name
        another ledger account holds is refused before the file is written.
        """
        with ledger_scope() as ledger:
            existing = ledger.find_account(external_uid=account_uid)
            other = ledger.find_account(name=request.name.strip())
            if other is not None and (existing is None or other["id"] != existing["id"]):
                raise HTTPException(
                    status_code=422,
                    detail=f"another account in the ledger is already called {request.name.strip()!r}",
                )
        try:
            rename_account(
                config_path,
                account_uid,
                name=request.name,
                start_sync_date=request.start_sync_date,
            )
        except UnknownConfiguredAccount as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if existing is not None:
            with ledger_scope() as ledger:
                ledger.rename_account(existing["id"], request.name)
        return setup_payload()

    @router.delete("/api/setup/accounts/{account_uid}")
    def remove_configured_account(account_uid: str) -> dict:
        try:
            remove_account(config_path, account_uid)
        except UnknownConfiguredAccount as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return setup_payload()

    return router
