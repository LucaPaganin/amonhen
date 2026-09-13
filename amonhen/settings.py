"""Project-wide constants and paths, each overridable via a AMONHEN_<NAME> env var."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(f"AMONHEN_{name}")
    return Path(raw) if raw else default


def _env_str(name: str, default: str) -> str:
    return os.getenv(f"AMONHEN_{name}", default)


# Ledger and configuration. The Enable Banking credentials live in the same
# accounts.json the connector used, minus the Actual Budget keys.
DB_PATH = _env_path("DB_PATH", ROOT / "amonhen.db")
CONFIG_FILE = _env_path("CONFIG_FILE", ROOT / "accounts.json")
EB_API = _env_str("EB_API", "https://api.enablebanking.com")
SYNC_INTERVAL_HOURS = int(_env_str("SYNC_INTERVAL_HOURS", "6"))

# HTTP API and PWA host (phase 2). The API has no authentication, so it binds
# to localhost by default; the container sets AMONHEN_HOST=0.0.0.0.
HOST = _env_str("HOST", "127.0.0.1")
PORT = int(_env_str("PORT", "8000"))

# Category account that names transactions which no rule has classified yet.
UNCATEGORIZED = _env_str("UNCATEGORIZED", "Uncategorized")

# Optional external LLM, used only to propose a category for merchants nobody
# has seen before. Without a URL the whole feature stays off.
LLM_URL = _env_str("LLM_URL", "")
LLM_API_KEY = _env_str("LLM_API_KEY", "")
LLM_MODEL = _env_str("LLM_MODEL", "")
