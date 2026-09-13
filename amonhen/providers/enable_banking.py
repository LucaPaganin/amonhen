"""Enable Banking HTTP client.

One class, one responsibility: talk to the Enable Banking API. Authentication
is an RS256 JWT signed per request with a one-hour expiry.
"""
import datetime as dt
import logging
import time
import uuid
from pathlib import Path

import jwt as pyjwt
import requests
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from amonhen.settings import EB_API

log = logging.getLogger(__name__)

# Number of attempts before a 429 is surfaced to the caller.
_RATE_LIMIT_ATTEMPTS = 4
_RATE_LIMIT_BASE_SECONDS = 5
_PAGE_DELAY_SECONDS = 1
# Inclusive window width; ASPSPs reject broader transaction ranges.
_WINDOW_DAYS = 30


class ConsentExpiredError(RuntimeError):
    """Enable Banking rejected a request because the consent/session expired."""


class EnableBankingClient:
    def __init__(
        self,
        application_id: str,
        pem_path: str | Path,
        redirect_url: str,
        api_url: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.application_id = application_id
        self.pem_path = Path(pem_path)
        self.redirect_url = redirect_url
        # Resolved here, not in the signature, so a test can point the client at
        # a stub by patching the module constant.
        self.api_url = (api_url or EB_API).rstrip("/")
        self.timeout = timeout
        self._key = load_pem_private_key(self.pem_path.read_bytes(), password=None)

    # -- auth ---------------------------------------------------------------

    def _headers(self) -> dict:
        now = int(time.time())
        payload = {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600,
            "jti": str(uuid.uuid4()),
            "sub": self.application_id,
        }
        token = pyjwt.encode(
            payload, self._key, algorithm="RS256", headers={"kid": self.application_id}
        )
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def start_auth(
        self, bank_name: str, country: str, psu_type: str = "personal"
    ) -> tuple[str, str, str]:
        state = str(uuid.uuid4())
        valid_until = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 180 * 24 * 3600)
        )
        body = {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": bank_name, "country": country},
            "state": state,
            "redirect_url": self.redirect_url,
            "psu_type": psu_type,
        }
        response = requests.post(
            f"{self.api_url}/auth", json=body, headers=self._headers(), timeout=self.timeout
        )
        response.raise_for_status()
        return state, valid_until, response.json()["url"]

    def complete_auth(self, code: str, state: str) -> dict:
        response = requests.post(
            f"{self.api_url}/sessions",
            json={"code": code, "state": state},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    # -- data ---------------------------------------------------------------

    def list_banks(self) -> list[dict]:
        """The ASPSPs Enable Banking accepts, so /connect can name one exactly."""
        response = self._get(f"{self.api_url}/aspsps")
        response.raise_for_status()
        return [
            {"name": bank.get("name"), "country": bank.get("country")}
            for bank in response.json().get("aspsps", [])
            if bank.get("name")
        ]

    def list_accounts(self, session_id: str) -> list[dict]:
        """Account objects from a session.

        The live payload carries uids in `accounts` and the account objects in
        `accounts_data`; older shapes only have one of the two.
        """
        response = self._get(f"{self.api_url}/sessions/{session_id}")
        response.raise_for_status()
        data = response.json()
        candidates = data.get("accounts_data") or data.get("accounts") or []
        return [account for account in candidates if isinstance(account, dict)]

    def fetch_account_details(self, account_uid: str) -> dict:
        """The account's own identification, which its session listing omits.

        The session carries uids and little else, so this is the only place the
        account's own IBAN comes from. The transfer matcher compares it against
        the counterparty account the bank printed on each leg.
        """
        response = self._get(f"{self.api_url}/accounts/{account_uid}/details")
        response.raise_for_status()
        return response.json()

    def fetch_balances(self, account_uid: str) -> dict:
        response = self._get(f"{self.api_url}/accounts/{account_uid}/balances")
        response.raise_for_status()
        return response.json()

    def fetch_transactions(
        self, account_uid: str, date_from: dt.date, date_to: dt.date | None = None
    ) -> list[dict]:
        end_date = date_to or dt.date.today()
        url = f"{self.api_url}/accounts/{account_uid}/transactions"
        transactions: list[dict] = []
        window_start = date_from

        # ASPSPs reject broad ranges, so query inclusive 30-day windows. A
        # continuation key is only valid while the original date params repeat.
        while window_start <= end_date:
            window_end = min(window_start + dt.timedelta(days=_WINDOW_DAYS - 1), end_date)
            period_params = {
                "date_from": window_start.isoformat(),
                "date_to": window_end.isoformat(),
            }
            continuation_key = None
            first_page = True

            while True:
                if not first_page:
                    time.sleep(_PAGE_DELAY_SECONDS)
                params = dict(period_params)
                if continuation_key:
                    params["continuation_key"] = continuation_key
                response = self._get(url, params)
                response.raise_for_status()
                data = response.json()
                transactions.extend(data.get("transactions", []))
                continuation_key = data.get("continuation_key")
                first_page = False
                if not continuation_key:
                    break

            window_start = window_end + dt.timedelta(days=1)

        return transactions

    # -- internals ----------------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        """GET with 429 backoff; 401/403 means the consent is no longer valid."""
        response = None
        for attempt in range(_RATE_LIMIT_ATTEMPTS):
            response = requests.get(
                url, headers=self._headers(), params=params, timeout=self.timeout
            )
            if response.status_code == 429:
                wait = min(_RATE_LIMIT_BASE_SECONDS * 2**attempt, 60)
                log.warning("Enable Banking rate limited, retrying in %ds", wait)
                time.sleep(wait)
                continue
            if response.status_code == 401:
                raise ConsentExpiredError(
                    "Enable Banking rejected the request as unauthenticated: the session, "
                    "consent or JWT is no longer valid"
                )
            if response.status_code == 403:
                raise ConsentExpiredError(
                    "Enable Banking denied access: the consent was revoked or the "
                    "application lacks the required permission"
                )
            return response
        return response
