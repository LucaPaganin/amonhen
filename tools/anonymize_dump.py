"""Anonymize raw Enable Banking dumps into committed parsing fixtures.

Phase 0 produces raw JSON dumps on disk (personal data, gitignored). This tool
turns them into fixtures safe to commit: structure, sign, status and merchant
text are preserved, while account ids, IBANs, party names, references, dates and
amount magnitudes are replaced deterministically.

Amounts are randomized per transaction, so relationships that depend on exact
values (pending -> booked amount equality, opposite transfer legs) are not
preserved: tests covering those use synthetic data.

Usage:
    uv run python tools/anonymize_dump.py dumps mytestfineco.json
"""
import argparse
import datetime
import decimal
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SALT_FILE = REPO_ROOT / "dumps" / ".anonymize-salt"

SYNTHETIC_NAMES = (
    "Alice Verdi", "Bruno Neri", "Carla Gialli", "Dario Blu", "Elena Rosa",
    "Fulvio Grigi", "Giorgia Viola", "Ivan Marroni", "Livia Azzurra", "Mario Rossi",
    "Nadia Beige", "Oscar Argento", "Paola Corallo", "Quirino Verde", "Rita Turchese",
    "Sandro Indaco", "Teresa Ambra", "Ugo Porpora", "Vera Lilla", "Walter Ciano",
)

_CARD_NUMBER = re.compile(r"(\*{3,}\s*)(\d+)")
_DIGITS = re.compile(r"(?<![\d/])\d{4,}(?![\d/])")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_ORD_BEN = re.compile(r"(Ord:\s*)(.+?)(\s+Ben:)")
_TEXT_DATE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")

DATE_KEYS = {"booking_date", "value_date", "transaction_date", "date_from", "date_to", "start_sync_date"}
TOKEN_KEYS = {
    "transaction_id", "entry_reference", "reference_number", "identification_hash",
    "identification_hashes", "session_id", "account_uid", "uid", "organisation_id",
    "private_id", "psu_id_hash", "contract_identification",
}
IBAN_KEYS = {"iban", "other"}
AMOUNT_KEYS = {"amount", "instructed_amount"}
TEXT_KEYS = {
    "note", "remittance_information", "remittance_information_unstructured", "additional_information",
    "description",
}
TEXT_NODE_KEYS = {"contact_details", "postal_address"}
DROP_KEYS = {
    "balance_after_transaction", "session_expiry", "valid_until", "created", "authorized", "access",
}


class Anonymizer:
    """Deterministic pseudonymizer for one fixture run."""

    def __init__(self, salt: str, own_names: list[str]) -> None:
        self.salt = salt
        self.names: dict[str, str] = {
            name.strip().lower(): "Titolare Conto" for name in own_names if name.strip()
        }
        self._name_index = len(self.names)
        self.date_shift = datetime.timedelta(0)

    def digest(self, value: str, length: int = 16) -> str:
        return hashlib.sha256(f"{self.salt}:{value}".encode()).hexdigest()[:length]

    def token(self, value: str) -> str:
        return f"anon-{self.digest(value)}"

    def name(self, value: str) -> str:
        key = value.strip().lower()
        if key not in self.names:
            self.names[key] = SYNTHETIC_NAMES[self._name_index % len(SYNTHETIC_NAMES)]
            self._name_index += 1
        return self.names[key]

    def iban(self, value: str) -> str:
        body = self.digest(value, 24).upper()
        return (value[:2] + digits_only(body))[: max(len(value), 16)]

    def amount_factor(self, key: str) -> decimal.Decimal:
        raw = int(self.digest(key, 8), 16)
        return decimal.Decimal("0.2") + decimal.Decimal(raw % 700) / 1000

    def date(self, value: str | None) -> str | None:
        if not value:
            return value
        return (datetime.date.fromisoformat(value[:10]) + self.date_shift).isoformat()

    def shift_for(self, bank: str) -> datetime.timedelta:
        """Whole-week shift, so weekdays survive and the offset stays stable."""
        weeks = int(self.digest(f"date:{bank}", 4), 16) % 40 + 1
        return datetime.timedelta(days=-7 * weeks)

    def register_names(self, node: object) -> None:
        """Collect every party name first, so remittance text can be scrubbed too."""
        if isinstance(node, list):
            for item in node:
                self.register_names(item)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key == "name" and isinstance(value, str) and value:
                    self.name(value)
                elif isinstance(value, (dict, list)):
                    self.register_names(value)

    def token_map(self) -> dict[str, str]:
        """Real name tokens (surname, first name) map to their fake counterpart.

        Party names also appear inside remittance text in different orders and
        casings ("MARIO ROSSI", "ROSSI MARIO"), so replacing whole names is
        not enough; tokens shorter than three letters are left alone so legal
        suffixes like "S.r.l." survive.
        """
        mapping: dict[str, str] = {}
        for real, fake in self.names.items():
            real_tokens = [t for t in re.split(r"[^A-Za-z]+", real) if len(t) >= 3]
            fake_tokens = [t for t in re.split(r"[^A-Za-z]+", fake) if len(t) >= 3]
            for index, token in enumerate(real_tokens):
                replacement = fake_tokens[min(index, len(fake_tokens) - 1)] if fake_tokens else fake
                mapping.setdefault(token.lower(), replacement)
        return mapping

    def text(self, value: str) -> str:
        for real, fake in self.names.items():
            if real in value.lower():
                value = re.sub(re.escape(real), fake, value, flags=re.I)
        for token, fake in self.token_map().items():
            value = re.sub(rf"\b{re.escape(token)}\b", fake, value, flags=re.I)
        value = _ORD_BEN.sub(lambda m: m.group(1) + self.name(m.group(2)) + m.group(3), value)
        value = _IBAN.sub(lambda m: self.iban(m.group(0)), value)
        value = _UUID.sub(lambda m: self.token(m.group(0)), value)
        value = _CARD_NUMBER.sub(lambda m: m.group(1) + random_digits(m.group(2), self.salt), value)
        value = _TEXT_DATE.sub(self._shift_text_date, value)
        return _DIGITS.sub(lambda m: random_digits(m.group(0), self.salt), value)

    def _shift_text_date(self, match: re.Match[str]) -> str:
        day, month, year = (int(part) for part in match.group(0).split("/"))
        if year < 100:
            year += 2000
        shifted = self.date(f"{year:04d}-{month:02d}-{day:02d}") or ""
        return "/".join(reversed(shifted.split("-"))) if shifted else match.group(0)

    def anonymize(self, node: object, amount_key: str | None = None) -> object:
        if isinstance(node, list):
            return [self.anonymize(item, amount_key=amount_key) for item in node]
        if not isinstance(node, dict):
            return node

        result: dict[str, object] = {}
        for key, value in node.items():
            if key in DATE_KEYS and isinstance(value, str):
                result[key] = self.date(value)
            elif key in TOKEN_KEYS and isinstance(value, str) and value:
                result[key] = self.token(value)
            elif key in IBAN_KEYS and isinstance(value, str) and value:
                result[key] = self.iban(value)
            elif key == "name" and isinstance(value, str) and value:
                result[key] = self.name(value)
            elif key == "identification" and isinstance(value, str) and value:
                result[key] = random_digits(value, self.salt)
            elif key in DROP_KEYS:
                result[key] = None
            elif key in AMOUNT_KEYS and isinstance(value, str):
                factor = self.amount_factor(amount_key or value)
                result[key] = str((decimal.Decimal(value) * factor).quantize(decimal.Decimal("0.01")))
            elif key in TEXT_KEYS:
                result[key] = self.anonymize_text_node(value)
            elif key in TEXT_NODE_KEYS:
                result[key] = self.anonymize_text_node(value)
            elif isinstance(value, (dict, list)):
                result[key] = self.anonymize(value, amount_key=amount_key)
            else:
                result[key] = value
        return result

    def anonymize_text_node(self, node: object) -> object:
        if isinstance(node, dict):
            return {key: self.anonymize_text_node(value) for key, value in node.items()}
        if isinstance(node, list):
            return [self.anonymize_text_node(item) for item in node]
        if isinstance(node, str):
            return self.text(node)
        return node


def digits_only(value: str) -> str:
    return "".join(str(int(c, 16) % 10) for c in value)


def random_digits(value: str, seed: str) -> str:
    digest = hashlib.sha256(f"{seed}:digits:{value}".encode()).hexdigest()
    return digits_only(digest[: len(value)])


def load_salt(path: Path) -> str:
    """Salt for every pseudonym, kept out of the repository.

    A committed salt would make the transform reversible: amounts are a
    deterministic function of it, so a reader could divide it back out and
    recover the real figures. The salt lives in a gitignored file, created on
    first use; `AMONHEN_ANON_SALT` overrides it for a one-off run.
    """
    from_environment = os.getenv("AMONHEN_ANON_SALT")
    if from_environment:
        return from_environment
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_hex(16)
    path.write_text(salt, encoding="utf-8")
    return salt


def load_dump(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {}, data
    return data.get("account") or {}, data.get("transactions", [])


def is_interesting(txn: dict) -> bool:
    if txn.get("status") != "BOOK":
        return True
    code = ((txn.get("bank_transaction_code") or {}).get("code") or "").upper()
    return any(token in code for token in ("TRANSFER", "SEPA", "ATM", "TOPUP", "FEE"))


def select(txns: list[dict], limit: int) -> list[dict]:
    """Keep every pending row plus unusual types, filling up to limit."""
    if len(txns) <= limit:
        return txns
    keep = [i for i, txn in enumerate(txns) if txn.get("status") != "BOOK"]
    for i, txn in enumerate(txns):
        if len(keep) >= limit:
            break
        if i not in keep and is_interesting(txn):
            keep.append(i)
    for i in range(len(txns)):
        if len(keep) >= limit:
            break
        if i not in keep:
            keep.append(i)
    return [txns[i] for i in sorted(set(keep))]


def bank_label(account: dict, path: Path) -> str:
    if account.get("bank_name"):
        return account["bank_name"]
    return re.sub(r"^(my)?test", "", path.stem).capitalize() or path.stem


def fixture_slug(account: dict, bank: str) -> str:
    hint = (account.get("notes") or "").strip()
    if hint.lower().startswith(bank.lower()):
        hint = hint[len(bank):].strip()
    return re.sub(r"[^a-z0-9]+", "_", f"{bank} {hint}".lower()).strip("_")


def build_fixture(path: Path, anonymizer: Anonymizer, limit: int) -> tuple[str, dict]:
    account, txns = load_dump(path)
    bank = bank_label(account, path)
    anonymizer.date_shift = anonymizer.shift_for(bank)
    anonymizer.register_names(txns)
    selected = select(txns, limit)

    dates = sorted(t.get("booking_date") or "" for t in selected if t.get("booking_date"))
    uid = account.get("account_uid") or account.get("uid")
    fixture = {
        "account": {
            "bank_name": bank,
            "account_uid": anonymizer.token(uid) if uid else None,
            "label": (account.get("notes") or None),
        },
        "source_file": path.name,
        "date_from": anonymizer.date(dates[0]) if dates else None,
        "date_to": anonymizer.date(dates[-1]) if dates else None,
        "count": len(selected),
        "transactions": [
            anonymizer.anonymize(txn, amount_key=f"{path.name}:{index}")
            for index, txn in enumerate(selected)
        ],
    }
    return fixture_slug(account, bank), fixture


def iter_dumps(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files += sorted((path / "accounts").glob("*.json"))
        elif path.is_file():
            files.append(path)
        else:
            sys.exit(f"not found: {path}")
    return files


def load_own_names(config_path: Path) -> list[str]:
    if not config_path.exists():
        return []
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return [n.strip() for n in (data.get("account_holder_name") or "").split(",") if n.strip()]


PROVENANCE = """# Enable Banking parsing fixtures

Anonymized from real Enable Banking dumps. Generated by
`tools/anonymize_dump.py`; do not edit by hand.

## Source

- `revolut_*`: raw dumps fetched from the live API on 2026-09-12, range
  2026-01-01 to 2026-09-12, including `PDNG` rows.
- `mytestfineco`: raw dump of the Fineco account from a previous session
  (2026-04-27 to 2026-05-16). The live fetch on 2026-09-12 returned 401/403:
  the Fineco consent is expired, which is also why the manual-export import path
  of the desiderata risk table exists.

## Anonymization

Preserved: JSON structure, `status`, `credit_debit_indicator`, currency,
`bank_transaction_code`, `merchant_category_code`, merchant text shape.

Replaced with values derived from a salt that is **not** in this repository
(`dumps/.anonymize-salt`, gitignored, or `AMONHEN_ANON_SALT`): account uids,
IBANs, party names, card identifiers, references, dates (whole-week shift) and
amount magnitudes.

Amounts and dates are therefore not recoverable from the repository alone. Do
not commit a salt, and do not regenerate these files with a salt that appears
anywhere in tracked files. Rules that depend on exact values (pending to booked
equality, opposite transfer legs, balance assertions) are NOT preserved by the
anonymization; tests that need those use synthetic data.

Names only mentioned inside free text, and values under keys the anonymizer
does not know, are copied through: review a regenerated fixture for personal
data before committing it.

Personal data must not be re-added to this directory.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dumps", nargs="+", help="Raw dump files or directories")
    parser.add_argument("--out", default="tests/fixtures/enable_banking", help="Fixture directory")
    parser.add_argument("--config", default=str(REPO_ROOT / "accounts.json"), help="accounts.json for own names")
    parser.add_argument("--limit", type=int, default=60, help="Max transactions per account")
    parser.add_argument(
        "--salt-file",
        default=str(DEFAULT_SALT_FILE),
        help="File holding the pseudonym salt; gitignored and created on first use",
    )
    args = parser.parse_args()

    anonymizer = Anonymizer(load_salt(Path(args.salt_file)), load_own_names(Path(args.config)))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in iter_dumps([Path(p) for p in args.dumps]):
        slug, fixture = build_fixture(path, anonymizer, args.limit)
        target = out_dir / f"{slug}.json"
        target.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{target}: {fixture['count']} transaction(s)")

    (out_dir / "PROVENANCE.md").write_text(PROVENANCE, encoding="utf-8")
    print(f"fixtures written to {out_dir}")


if __name__ == "__main__":
    main()
