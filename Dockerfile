# syntax=docker/dockerfile:1
# The tag matters: uv.lock is revision 3, which older uv binaries refuse to
# read. Keep this at the version that wrote the lock (see `uv --version`).
FROM ghcr.io/astral-sh/uv:0.9.6 AS uv

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
# package-lock.json is optional: fall back to a plain install until it exists.
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
# Install exactly the production dependency set before copying application code.
RUN uv sync --frozen --no-dev --no-install-project \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin amonhen \
    && install --directory --owner=amonhen --group=amonhen /data \
    && install --directory --owner=amonhen --group=amonhen /config

COPY amonhen ./amonhen
COPY --from=web /web/dist ./web/dist

USER amonhen
EXPOSE 8000

# The image's own defaults. compose overrides both with the same values, but a
# bare `docker run` must not fall back to /app — that directory belongs to root,
# so the process would die with "unable to open database file".
ENV AMONHEN_DB_PATH=/data/amonhen.db \
    AMONHEN_CONFIG_FILE=/config/accounts.json

# /api/health answers without touching the ledger or accounts.json, so it says
# whether the process is up and nothing else. curl is not in the slim image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

# compose overrides the cadence with the value from .env; this is the default.
CMD ["uv", "run", "--no-sync", "python", "-m", "amonhen", "serve", "--sync-interval-hours", "6"]
