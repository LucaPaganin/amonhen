#!/usr/bin/env bash
# Rehearse a release on a copy of the live ledger, before the NAS runs it for real.
#
# Takes a fresh snapshot of the live ledger (or reuses one), makes two copies of
# it, and runs the same read-only commands on both: the image the NAS runs now on
# one copy, the new image on the other. The new image migrates its copy on the
# way, as it would migrate the live file. Then it compares what the two answered
# and checks the migrated file: its schema version, its integrity, its foreign keys.
#
# What keeps it harmless:
#   - every container runs with --network none: no bank, no model, nothing outside;
#   - the copies carry no private.pem, so a bank call could not even be signed;
#   - only read-only commands and GET requests, on the copies, never the live file;
#   - the answers are compared by sha256 inside the scratch volume and never printed,
#     so whoever runs this (a person, or an agent whose transcript leaves the NAS)
#     sees "identico" / "DIVERSO", not a balance, a name or an IBAN;
#   - the scratch volume holds a copy of the real ledger and is removed on exit,
#     on success and on failure alike, unless --keep asks to inspect it.
#
# Run it from the compose directory on the NAS (or pass --dir). Exit status 0 means
# every answer matched and the migrated file is sound; 1 means something differs.
#
# Usage: tools/rehearse_release.sh NEW_TAG [--old TAG] [--dir DIR] [--image REPO]
#                                  [--snapshot NAME] [--api] [--keep]
#   NEW_TAG          the release to rehearse, already published by CI (e.g. v1.17.0)
#   --old TAG        the release the NAS runs now (default: AMONHEN_TAG in DIR/.env)
#   --dir DIR        the compose directory (default: the current one)
#   --image REPO     the image repository (default: ghcr.io/lucapaganin/amonhen)
#   --snapshot NAME  reuse backups/NAME instead of taking a fresh snapshot
#   --api            also compare the GET routes of the two servers
#   --keep           keep the scratch volume, to look at the answers by hand
set -euo pipefail

new=""
old=""
dir="$PWD"
image="ghcr.io/lucapaganin/amonhen"
snapshot=""
api=0
keep=0

while [ $# -gt 0 ]; do
  case "$1" in
    --old) old="$2"; shift 2 ;;
    --dir) dir="$2"; shift 2 ;;
    --image) image="$2"; shift 2 ;;
    --snapshot) snapshot="$2"; shift 2 ;;
    --api) api=1; shift ;;
    --keep) keep=1; shift ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) [ -z "$new" ] || { echo "one release at a time: $new and $1" >&2; exit 2; }; new="$1"; shift ;;
  esac
done
[ -n "$new" ] || { echo "which release? tools/rehearse_release.sh NEW_TAG (see --help)" >&2; exit 2; }

cd "$dir"
if [ -z "$old" ]; then
  # A .env saved with Windows line endings ends the value with \r, which docker
  # compose tolerates and an image reference does not ("invalid reference format").
  old=$(sed -n 's/^AMONHEN_TAG=//p' .env 2>/dev/null | tr -d '"\r' | tail -1)
  [ -n "$old" ] || { echo "no AMONHEN_TAG in $dir/.env: pass --old" >&2; exit 2; }
fi
[ "$old" != "$new" ] || { echo "the NAS already runs $new" >&2; exit 2; }

volume="amonhen-rehearsal-$$"
containers=()
failed=0

cleanup() {
  for c in "${containers[@]}"; do docker rm -f "$c" >/dev/null 2>&1 || true; done
  if [ "$keep" = 1 ]; then
    echo
    echo "Kept $volume. The answers are in /r/out/{old,new}; to look at them:"
    echo "  docker run --rm -it --network none -v $volume:/r $image:$old bash"
    echo "It holds a copy of the real ledger: docker volume rm $volume when done."
  else
    docker volume rm -f "$volume" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

step() { printf '\n== %s\n' "$*"; }

# A container on the scratch volume, cut off from every network.
scratch() { docker run --rm --network none -v "$volume:/r" "$@"; }

for tag in "$old" "$new"; do
  docker image inspect "$image:$tag" >/dev/null 2>&1 || docker pull -q "$image:$tag" >/dev/null
done

step "Snapshot"
if [ -z "$snapshot" ]; then
  docker compose exec -T amonhen python -m amonhen backup --dest /backups --keep 14 >/dev/null
  # Snapshot folders are named by the moment they were taken, so they sort by time.
  snapshot=$(docker run --rm --network none -v "$PWD/backups:/backups:ro" "$image:$old" \
    sh -c 'ls -1 /backups | sort | tail -1')
  echo "taken now: backups/$snapshot"
else
  echo "reused: backups/$snapshot"
fi

step "Two copies, without the private key"
docker volume create "$volume" >/dev/null
docker run --rm --network none --user 0:0 -v "$PWD/backups:/backups:ro" -v "$volume:/r" "$image:$old" sh -c '
  set -e
  [ -f "/backups/$1/amonhen.db" ] || { echo "no amonhen.db in backups/$1" >&2; exit 1; }
  for side in old new; do
    mkdir -p "/r/$side" "/r/out/$side"
    cp "/backups/$1/amonhen.db" "/r/$side/"
    [ ! -f "/backups/$1/accounts.json" ] || cp "/backups/$1/accounts.json" "/r/$side/"
  done
  chown -R 10001:10001 /r
  chmod -R go-rwx /r' sh "$snapshot"
# What fetches a GET route from inside a server's container, and writes the answer
# where the comparison reads it; an error is an answer too, so it is written as one.
scratch -i "$image:$old" sh -c 'cat > /r/fetch.py' <<'PY'
import sys, urllib.error, urllib.request
path, out = sys.argv[1], sys.argv[2]
try:
    body = urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=60).read()
except urllib.error.HTTPError as exc:
    body = f"HTTP {exc.code}\n".encode() + exc.read()
with open(out, "wb") as handle:
    handle.write(body)
PY
echo "done"

# Run one read-only command with one image on its own copy; its output and its exit
# status go into the volume, never to this terminal.
cli() {  # cli <tag> <old|new> <name> <command...>
  local tag="$1" side="$2" name="$3"; shift 3
  scratch -e "AMONHEN_DB_PATH=/r/$side/amonhen.db" -e "AMONHEN_CONFIG_FILE=/r/$side/accounts.json" \
    "$image:$tag" sh -c 'out="/r/out/$1/$2"; shift 2
      python -m amonhen "$@" > "$out.txt" 2>&1; echo $? > "$out.code"' sh "$side" "$name" "$@"
}

# Compare one answer of the two sides by its sha256, inside the volume.
compare() {  # compare <name> <ext...>
  local name="$1"; shift
  local ext sums a b shown=""
  for ext in "$@"; do
    sums=$(scratch "$image:$old" sh -c 'sha256sum "/r/out/old/$1" "/r/out/new/$1" | cut -d" " -f1' sh "$name.$ext")
    a=$(echo "$sums" | sed -n 1p); b=$(echo "$sums" | sed -n 2p)
    if [ "$a" != "$b" ]; then
      printf '  %-34s DIVERSO (%s)\n' "$name" "$ext"; failed=1; return
    fi
    # The fingerprint shown is the answer's own, the first file compared, not the
    # exit status that follows it: two answers that only share "0" must not look alike.
    [ -n "$shown" ] || shown="$a"
  done
  printf '  %-34s identico  %s\n' "$name" "${shown:0:12}"
}

step "The same commands, $old against $new"
commands=(validate accounts metrics budgets spend rules anomalies)
for command in "${commands[@]}"; do
  cli "$old" old "$command" "$command"
  cli "$new" new "$command" "$command"
  compare "$command" txt code
done

step "The migrated file"
# -i: the program comes on stdin, and without it Docker hands python an empty one
# that "succeeds" having checked nothing.
scratch -i -e "AMONHEN_DB_PATH=/r/new/amonhen.db" "$image:$new" python - <<'PY' || failed=1
import sqlite3, sys
conn = sqlite3.connect("/r/new/amonhen.db")
version = conn.execute("PRAGMA user_version").fetchone()[0]
integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
orphans = len(conn.execute("PRAGMA foreign_key_check").fetchall())
try:
    from amonhen.db import MIGRATIONS
    expected = len(MIGRATIONS)
except ImportError:  # a release from before the migrations were counted
    expected = None
ok = integrity == "ok" and orphans == 0 and (expected is None or version == expected)
print(f"  schema version {version}" + ("" if expected is None else f" (the code expects {expected})"))
print(f"  integrity_check {integrity}, foreign_key_check {orphans} row(s)")
sys.exit(0 if ok else 1)
PY

if [ "$api" = 1 ]; then
  step "The GET routes, $old against $new"
  for side in old new; do
    tag=$old; [ "$side" = new ] && tag=$new
    name="amonhen-rehearsal-$side-$$"
    # No sync loop, no network: the server answers its own loopback and nothing else.
    docker run -d --name "$name" --network none -v "$volume:/r" \
      -e "AMONHEN_DB_PATH=/r/$side/amonhen.db" -e "AMONHEN_CONFIG_FILE=/r/$side/accounts.json" \
      "$image:$tag" python -m amonhen serve --sync-interval-hours 0 >/dev/null
    containers+=("$name")
  done
  for side in old new; do
    up=0
    for _ in $(seq 1 60); do
      if docker exec "amonhen-rehearsal-$side-$$" python -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" \
        >/dev/null 2>&1; then up=1; break; fi
      sleep 1
    done
    [ "$up" = 1 ] || { echo "  the $side server did not answer" >&2; failed=1; exit 1; }
  done
  routes=(/api/accounts /api/virtual-accounts /api/categories /api/tags /api/rules
          /api/month /api/metrics /api/statistics /api/spending /api/flows /api/networth
          /api/budgets /api/anomalies /api/review /api/suggestions /api/deleted
          /api/sync/held "/api/transactions?limit=500" /api/transfers/labels)
  for route in "${routes[@]}"; do
    name=$(echo "$route" | sed 's|^/api/||; s|[/?=&]|_|g')
    for side in old new; do
      docker exec "amonhen-rehearsal-$side-$$" python /r/fetch.py "$route" "/r/out/$side/api_$name.json"
    done
    compare "api_$name" json
  done
  # The release is the one place the two servers should differ: say which they are.
  for side in old new; do
    docker exec "amonhen-rehearsal-$side-$$" python -c \
      "import json, urllib.request; h = json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health')); print('  $side: version', h['version'], '- api', h['api_version'])"
  done
fi

step "Result"
if [ "$failed" = 0 ]; then
  echo "  $new answers like $old on a copy of the ledger, and the migrated file is sound."
else
  echo "  something differs: rerun with --keep and compare /r/out/old with /r/out/new by hand."
  echo "  Do not deploy $new until the difference is understood."
fi
exit "$failed"
