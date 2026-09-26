"""A stand-in for Enable Banking, so the first setup can be walked end to end.

Walking the wizard for real needs a consent at a bank and a dashboard account at
Enable Banking. This answers the same routes from the anonymized fixtures already
in the repository, which is enough to see the first setup through: the client
asks for the banks, the browser is sent to a callback that carries a made-up
code, and the movements the ledger then holds are the fixture ones.

It signs nothing and verifies nothing: the JWT the client sends is ignored. A
rehearsal therefore covers the wizard, the writes and the sync, and says nothing
about whether the credentials work — the real consent path is the only thing that
does.

Usage:
    python tools/eb_stub.py --fixtures tests/fixtures/enable_banking --port 9001
"""
import argparse
import decimal
import hashlib
import json
import urllib.parse
from dataclasses import dataclass
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_FIXTURES = "/fixtures"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 9001
DEFAULT_COUNTRY = "IT"
SESSION_ID = "stub-session"
CALLBACK_CODE = "stub-code"


@dataclass(frozen=True)
class StubAccount:
    uid: str
    bank: str
    name: str
    iban: str
    transactions: tuple[dict, ...]

    def balance(self, *, settled: bool = False) -> decimal.Decimal:
        """The fixture's movements, signed the way the client reads them.

        `settled` leaves the pending rows out, which is the difference between the
        two figures a bank reports: the booked one and the available one. Summing
        everything for both would make the booked figure disagree with the booked
        movements by exactly the pending sum.
        """
        total = decimal.Decimal(0)
        for raw in self.transactions:
            if settled and str(raw.get("status") or "BOOK") != "BOOK":
                continue
            amount = raw.get("transaction_amount") or {}
            value = decimal.Decimal(str(amount.get("amount") or "0"))
            total += -abs(value) if raw.get("credit_debit_indicator") == "DBIT" else abs(value)
        return total

    def last_day(self) -> str:
        days = sorted(
            str(raw.get("booking_date") or raw.get("value_date") or "") for raw in self.transactions
        )
        return days[-1] if days else date.today().isoformat()

    def within(self, start: str, end: str) -> list[dict]:
        return [
            raw
            for raw in self.transactions
            if start <= str(raw.get("booking_date") or raw.get("value_date") or "") <= end
        ]


class Stub:
    """The fixtures, plus the two things a session needs remembered."""

    def __init__(self, accounts: list[StubAccount]) -> None:
        self.accounts = accounts
        self.bank: str | None = None
        self.session: dict | None = None

    def banks(self) -> list[str]:
        return sorted({account.bank for account in self.accounts})

    def account(self, uid: str) -> StubAccount | None:
        return next((account for account in self.accounts if account.uid == uid), None)

    def authorize(self, body: dict) -> dict:
        """The ASPSP the wizard picked, and where the bank would send the browser.

        The real endpoint answers with an address at the bank; here the answer is
        the client's own redirect URL with a code attached, so the browser lands
        on `/callback` and the rest of the flow is the real one.
        """
        self.bank = ((body.get("aspsp") or {}).get("name") or "").strip() or None
        redirect = str(body.get("redirect_url") or "")
        if not redirect:
            raise ValueError("the request named no redirect_url")
        separator = "&" if "?" in redirect else "?"
        state = urllib.parse.quote(str(body.get("state") or ""))
        return {"url": f"{redirect}{separator}code={CALLBACK_CODE}&state={state}"}

    def start_session(self) -> dict:
        """A session over the accounts of the bank that was chosen."""
        chosen = [
            account for account in self.accounts if self.bank is None or account.bank == self.bank
        ]
        self.session = {
            "session_id": SESSION_ID,
            "accounts": [account.uid for account in chosen],
            "accounts_data": [
                {
                    "uid": account.uid,
                    "name": account.name,
                    "currency": "EUR",
                    "account_id": {"iban": account.iban},
                }
                for account in chosen
            ],
        }
        return self.session


def load_accounts(directory: Path) -> list[StubAccount]:
    """Every fixture in the directory, in file order, with an identity of its own.

    A fixture the anonymizer left without a uid still needs one: it is what the
    session names the account by, and what the next request comes back with.
    """
    accounts: list[StubAccount] = []
    for index, path in enumerate(sorted(directory.glob("*.json"))):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        raw = fixture.get("account") or {}
        uid = str(raw.get("account_uid") or f"stub-uid-{index + 1}")
        accounts.append(
            StubAccount(
                uid=uid,
                bank=str(raw.get("bank_name") or "Unknown"),
                name=str(raw.get("label") or raw.get("bank_name") or uid),
                iban=synthetic_iban(uid),
                transactions=tuple(fixture.get("transactions") or ()),
            )
        )
    return accounts


def synthetic_iban(uid: str) -> str:
    """An IBAN shaped like one, stable for the uid: nothing checks its checksum."""
    digits = int(hashlib.sha256(uid.encode("utf-8")).hexdigest(), 16) % 10**24
    return f"IT00{digits:024d}"


def handler_for(stub: Stub) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            self._answer("GET")

        def do_POST(self) -> None:
            self._answer("POST")

        def _answer(self, method: str) -> None:
            parsed = urllib.parse.urlparse(self.path)
            query = {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items()}
            body = self._body() if method == "POST" else {}
            print(f"{method} {parsed.path} {query or body}", flush=True)
            try:
                status, payload = route(stub, method, parsed.path, query, body)
            except ValueError as exc:
                status, payload = 400, {"message": str(exc)}
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length == 0:
                return {}
            try:
                body = json.loads(self.rfile.read(length))
            except ValueError as exc:
                raise ValueError(f"the body is not JSON: {exc}") from exc
            return body if isinstance(body, dict) else {}

        def log_message(self, format: str, *args) -> None:
            """One line per request, printed by us, and no second copy on stderr."""

    return Handler


def route(
    stub: Stub, method: str, path: str, query: dict[str, str], body: dict
) -> tuple[int, dict]:
    """What the client asks Enable Banking for, answered from the fixtures."""
    parts = [segment for segment in path.split("/") if segment]

    if method == "GET" and parts == ["aspsps"]:
        return 200, {
            "aspsps": [
                {"name": name, "country": DEFAULT_COUNTRY} for name in stub.banks()
            ]
        }

    if method == "POST" and parts == ["auth"]:
        return 200, stub.authorize(body)

    if method == "POST" and parts == ["sessions"]:
        return 200, stub.start_session()

    if method == "GET" and parts[:1] == ["sessions"]:
        if stub.session is None:
            return 404, {"message": "no session has been started"}
        return 200, stub.session

    if len(parts) == 3 and parts[0] == "accounts":
        account = stub.account(parts[1])
        if account is None:
            return 404, {"message": f"unknown account {parts[1]}"}
        if parts[2] == "details":
            return 200, {
                "uid": account.uid,
                "name": account.name,
                "currency": "EUR",
                "account_id": {"iban": account.iban},
            }
        if parts[2] == "balances":
            return 200, {"balances": [_balance(account, kind) for kind in ("CLBD", "ITAV")]}
        if parts[2] == "transactions":
            start = query.get("date_from") or "0001-01-01"
            end = query.get("date_to") or date.today().isoformat()
            return 200, {"transactions": account.within(start, end), "continuation_key": None}

    return 404, {"message": f"no such route: {method} {path}"}


def _balance(account: StubAccount, kind: str) -> dict:
    """One of the two figures: the booked total, or the one pending rows move."""
    amount = account.balance(settled=True) if kind == "CLBD" else account.balance()
    return {
        "balance_type": kind,
        "reference_date": account.last_day(),
        "balance_amount": {"amount": str(amount), "currency": "EUR"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", default=DEFAULT_FIXTURES, help="fixture directory")
    parser.add_argument("--host", default=DEFAULT_HOST, help="interface to listen on")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    accounts = load_accounts(Path(args.fixtures))
    if not accounts:
        raise SystemExit(f"no fixtures in {args.fixtures}")
    print(f"{len(accounts)} account(s): {', '.join(account.uid for account in accounts)}", flush=True)

    server = ThreadingHTTPServer((args.host, args.port), handler_for(Stub(accounts)))
    print(f"listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
