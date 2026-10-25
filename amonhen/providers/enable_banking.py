"""Enable Banking HTTP client.

One class, one responsibility: talk to the Enable Banking API. Authentication
is an RS256 JWT signed per request with a one-hour expiry.
"""
import datetime as dt
import logging
import time
import uuid
from dataclasses import dataclass, field
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
# Inclusive window width; ASPSPs reject broader transaction ranges. An account
# can ask for a narrower one (`max_window_days` in accounts.json).
_WINDOW_DAYS = 30
# What a bank answers when the range itself is what it refuses: the window is
# halved on these before the period gives up on it.
_RANGE_REFUSALS = (400, 422)


class ConsentExpiredError(RuntimeError):
    """Enable Banking rejected a request because the consent/session expired."""


@dataclass
class FetchedWindow:
    """One window of a period, and what the bank answered for it.

    `error` is None when the window was read to its last page; otherwise the
    window's movements are not in `transactions` at all, because half a window
    of pages is not a window the ledger can trust as covered. An empty window
    that succeeded is an answer too — the bank said there is nothing there, or
    that it serves nothing that old — and the caller shows it as such.
    """

    date_from: dt.date
    date_to: dt.date
    transactions: list[dict] = field(default_factory=list)
    error: str | None = None


def refusal_detail(response: requests.Response) -> str:
    """The provider's own words about a refusal, when it says any.

    A wrong application ID is the first-setup mistake that looks like this, and
    "Application does not exist" is worth more to the person reading it than the
    status code it arrived with.
    """
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        for key in ("message", "detail", "error", "error_description"):
            if isinstance(body.get(key), str):
                return body[key]
    return response.text[:200]


def refusal_code(response: requests.Response) -> str:
    """Enable Banking's machine-readable reason, empty when it gives none.

    `error` is the fixed half of a refusal where `message` is prose the provider
    may reword, so a caller that has to react to one reason reads it here
    instead of matching text.
    """
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        return body["error"]
    return ""


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
        self,
        account_uid: str,
        date_from: dt.date,
        date_to: dt.date | None = None,
        window_days: int = _WINDOW_DAYS,
    ) -> list[dict]:
        """Every movement in the range, or the first error any window raised."""
        end_date = date_to or dt.date.today()
        transactions: list[dict] = []
        window_start = date_from
        # ASPSPs reject broad ranges, so query inclusive windows of whole days.
        while window_start <= end_date:
            window_end = min(window_start + dt.timedelta(days=window_days - 1), end_date)
            transactions.extend(self._fetch_window(account_uid, window_start, window_end))
            window_start = window_end + dt.timedelta(days=1)
        return transactions

    def fetch_transaction_windows(
        self,
        account_uid: str,
        date_from: dt.date,
        date_to: dt.date,
        window_days: int = _WINDOW_DAYS,
    ) -> list[FetchedWindow]:
        """The range window by window, each with its own outcome.

        A window the bank refuses as a range (`_RANGE_REFUSALS`) is retried at
        half the width from the same day, down to one day; the narrower width
        then holds for the rest of the period, since it is the bank's limit and
        not the window's. When even one day is refused, the window as it was
        first asked is reported failed and the next one starts at full width
        again, so a bank that refuses everything costs a handful of calls per
        window rather than one per day. Any other failure is the window's own
        and is reported without halving. A dead consent is not a window's
        failure: it raises, because every other window would fail the same way.

        Windows are whole days on purpose: the ledger numbers identical
        movements of one day inside a batch, and a day split across two batches
        would number them differently on the next run.
        """
        windows: list[FetchedWindow] = []
        width = max(1, window_days)
        window_start = date_from
        asked_end: dt.date | None = None
        while window_start <= date_to:
            window_end = min(window_start + dt.timedelta(days=width - 1), date_to)
            asked_end = asked_end or window_end
            try:
                transactions = self._fetch_window(account_uid, window_start, window_end)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in _RANGE_REFUSALS and width > 1:
                    width = max(1, width // 2)
                    log.info(
                        "the bank refused %s..%s, retrying %d-day windows",
                        window_start, window_end, width,
                    )
                    continue
                windows.append(
                    FetchedWindow(window_start, asked_end, error=_window_error(exc))
                )
                window_start = asked_end + dt.timedelta(days=1)
                width = max(1, window_days)
                asked_end = None
                continue
            except requests.RequestException as exc:
                windows.append(FetchedWindow(window_start, window_end, error=str(exc)))
            else:
                windows.append(FetchedWindow(window_start, window_end, transactions))
            window_start = window_end + dt.timedelta(days=1)
            asked_end = None
        return windows

    def _fetch_window(
        self, account_uid: str, window_start: dt.date, window_end: dt.date
    ) -> list[dict]:
        """One window, every page. A continuation key is only valid while the
        original date params repeat."""
        url = f"{self.api_url}/accounts/{account_uid}/transactions"
        period_params = {
            "date_from": window_start.isoformat(),
            "date_to": window_end.isoformat(),
        }
        transactions: list[dict] = []
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
                    f"consent or JWT is no longer valid ({refusal_detail(response)})"
                )
            if response.status_code == 403:
                raise ConsentExpiredError(
                    "Enable Banking denied access: the consent was revoked or the "
                    f"application lacks the required permission ({refusal_detail(response)})"
                )
            return response
        return response


def _window_error(exc: requests.HTTPError) -> str:
    """A refused window in the bank's own words, with the status it came with."""
    response = exc.response
    if response is None:
        return str(exc)
    return f"{response.status_code} {refusal_detail(response)}".strip()
