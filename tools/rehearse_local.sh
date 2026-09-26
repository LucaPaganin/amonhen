#!/usr/bin/env bash
# Rehearse Amonhen's first start in containers, before the NAS runs it for real.
#
# What it proves, in the order it proves it: the image builds from this checkout,
# the container cannot write into a configuration folder the host made (and can
# after the chown the NAS note prescribes), the app answers, the wizard writes
# accounts.json and private.pem into that folder as the container's own user, the
# sync fills the ledger from a stand-in bank, `amonhen backup` takes a snapshot,
# and restoring it puts the app back on the same movements.
#
# Run it inside WSL: only there does a bind mount carry the POSIX ownership the
# NAS has, which is what the second and third checks read. See the README.
#
# Usage: tools/rehearse_local.sh [--target DIR] [--port 8000] [--force]
set -euo pipefail

target="${HOME}/amonhen-rehearsal"
port=8000
force=0
failed=0

while [ $# -gt 0 ]; do
  case "$1" in
    --target) target="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --force) force=1; shift ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! docker info >/dev/null 2>&1; then
  echo "The Docker engine is not answering. Start Docker Desktop and switch on" >&2
  echo "Settings -> Resources -> WSL Integration for this distribution." >&2
  exit 1
fi

# A local app on the same port would not be stopped, it would be shadowed:
# Windows lets the container publish 127.0.0.1:<port> while something else holds
# 0.0.0.0:<port>, and the browser's loopback then answers from the container — a
# fresh wizard drawn over a running, configured app, which reads as lost data.
# On Linux the second bind is refused instead, which is why this guard is here
# only for Docker Desktop, and only when it can ask Windows.
if command -v netstat.exe >/dev/null 2>&1; then
  # `grep -c`, not `-q`: `-q` closes the pipe the moment it matches, netstat.exe
  # then dies of SIGPIPE, and `set -o pipefail` reads that as "no match" — a guard
  # that never fires is worse than none.
  busy="$(netstat.exe -ano 2>/dev/null | grep -cE ":${port} .*LISTENING" || true)"
  if [ "${busy:-0}" -gt 0 ]; then
    echo "port ${port} is already listening on this machine: pass --port <a free one>." >&2
    exit 1
  fi
fi

if [ -d "$target" ] && [ -n "$(ls -A "$target" 2>/dev/null)" ]; then
  if [ "$force" -ne 1 ]; then
    echo "$target is not empty: remove it, or pass --force to write into it." >&2
    exit 1
  fi
  rm -rf "$target"
fi

echo "— copying $repo to $target/src"
mkdir -p "$target/src" "$target/deploy/config" "$target/deploy/backups"
# ext4 is where a bind mount behaves like the NAS one. `.env` stays behind: it
# holds the operator's own keys and this rehearsal has its own.
tar -C "$repo" \
  --exclude=.git --exclude=.venv --exclude=node_modules --exclude=web/node_modules \
  --exclude=web/dist --exclude=dumps --exclude=actual-cache --exclude=.pytest_cache \
  --exclude=.ruff_cache --exclude=__pycache__ --exclude=backups --exclude=.env \
  --exclude='mytest*' \
  -cf - . | tar -C "$target/src" -xf -

echo "— writing $target/deploy"
cp "$repo/docker-compose.yaml" "$target/deploy/docker-compose.yaml"

cat > "$target/deploy/docker-compose.override.yaml" <<EOF
# The base file, with the two things a rehearsal changes: the image is built here
# instead of pulled, the stub answers instead of Enable Banking, and the port is
# the one that was asked for.
services:
  amonhen:
    # !override, not another list entry: compose concatenates multi-value keys
    # (ports among them), so without the tag the base 8000 would stay published.
    # Needs Compose 2.24.4 or later.
    ports: !override
      - "127.0.0.1:${port}:8000"
    build:
      context: ${target}/src
  # The stand-in bank. The app reaches it by service name, so it publishes no
  # port and needs no host.docker.internal.
  eb-stub:
    image: python:3.13-slim
    container_name: amonhen-eb-stub
    restart: "no"
    command: ["python", "/stub/eb_stub.py", "--port", "9001"]
    volumes:
      - ${target}/src/tools/eb_stub.py:/stub/eb_stub.py:ro
      - ${target}/src/tests/fixtures/enable_banking:/fixtures:ro
EOF

cat > "$target/deploy/.env" <<EOF
# A local tag: the image is built from this checkout and the registry is untouched.
AMONHEN_TAG=rehearsal
AMONHEN_EB_API=http://eb-stub:9001
# No clock-driven sync: the wizard asks for the accounts, and the run stays
# deterministic. No AMONHEN_LLM_*: the assistant stays off.
AMONHEN_SYNC_INTERVAL_HOURS=0
EOF

echo "— generating $target/test-key.pem"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$target/test-key.pem" 2>/dev/null

cd "$target/deploy"
echo "— building the image and starting the containers"
docker compose up -d --build

echo "— /config belongs to the host user, so the container must not be able to write in it"
if refusal="$(docker compose exec -T amonhen sh -c 'touch /config/.probe' 2>&1)"; then
  echo "   !! the write succeeded before the chown. On a Windows path Docker Desktop"
  echo "   !! makes up the ownership, so this check proves nothing here: rerun from"
  echo "   !! WSL. The other checks still run."
  failed=1
elif [ "${refusal#*Permission denied}" != "$refusal" ]; then
  echo "   refused, as it should be"
else
  # A container that is not running refuses too, and that is not the refusal this
  # check exists to see: say which one it was instead of reading it as proof.
  echo "   !! the probe could not run, so nothing is proved either way:" >&2
  echo "   !! $refusal" >&2
  failed=1
fi

echo "— chown through the image, so no host password is needed"
docker compose run --rm --no-deps --user root --entrypoint chown amonhen 10001:10001 /config /backups
if docker compose exec -T amonhen sh -c 'touch /config/.probe && rm /config/.probe'; then
  echo "   the same write is allowed now"
else
  echo "   !! the container still cannot write in /config: the wizard will fail" >&2
  failed=1
fi

echo "— waiting for the app to answer"
status=missing
for _ in $(seq 1 40); do
  status="$(docker inspect --format '{{.State.Health.Status}}' amonhen 2>/dev/null || echo missing)"
  [ "$status" = "healthy" ] && break
  sleep 3
done
if [ "$status" = "healthy" ]; then
  echo "   healthy"
  curl -s "http://127.0.0.1:${port}/api/health" || true
  echo
else
  # The walkthrough below needs an app that answers: without one this run proved
  # none of the checks it printed, and the exit code has to say so.
  echo "   !! the app never became healthy (state: $status), so the checks below" >&2
  echo "   !! have nothing to answer. Logs: docker compose logs amonhen" >&2
  failed=1
fi

cat <<TEXT

Walk these, in order, at http://localhost:${port} on a phone-sized window (390x844):

  1. Credenziali  — any Application ID, your name, the key from ${target}/test-key.pem,
                    redirect URL http://localhost:${port}/callback.
                    Then: docker compose exec -T amonhen stat -c '%u:%g %n' /config/accounts.json /config/private.pem
                    must print 10001 10001.
  2. Banca        — country IT, the list holds Fineco and Revolut; pick Fineco. The
                    browser lands on /callback?code=stub-code&... and comes back.
  3. Conti        — name it Fineco, movements from 2025-01-01 (the fixtures are dated
                    2025; a later start date returns nothing).
  4. Primo sync   — it reports what it wrote; the stub's log shows the movements it served.
  5. Saldi        — declare the CLBD figure the stub printed and the account turns verified.

Then the part that matters, from ${target}/deploy:

  docker compose exec -T amonhen python -m amonhen backup --dest /backups
  ls -l ${target}/deploy/backups/*/            # amonhen.db, accounts.json, private.pem, manifest.json

  docker compose stop amonhen
  docker compose run --rm --no-deps --user root --entrypoint sh amonhen \\
    -c 'cp /backups/<stamp>/amonhen.db /data/amonhen.db && chown 10001:10001 /data/amonhen.db'
  docker compose up -d amonhen
  # /api/health answers again and the dashboard shows the same movements.

When you are done:

  cd ${target}/deploy
  # The container's own user owns what the wizard, the snapshot and the chown
  # wrote, so take those out from inside the image: a plain rm on the host
  # cannot, and would leave the folder behind.
  docker compose run --rm --no-deps --user root --entrypoint sh amonhen -c 'rm -rf /config/* /backups/*'
  docker compose down -v
  rm -rf ${target}
TEXT

exit "$failed"
