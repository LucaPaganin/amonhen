# Images, snapshots and the environment

Part of what `CLAUDE.md` says before changing code. A rule that changes changes here, in the same change as the code.

- **A snapshot is taken with SQLite's API, never by copying the file, and it is
  not a backup until it leaves the machine.** `amonhen backup` runs
  `Connection.backup` against the living database because the server may be
  writing while the cron runs, and a torn file copy that looks like a backup is
  the failure worth designing out; it writes a hidden `.partial` folder and renames
  it only at the end, so a run that dies leaves nothing that retention would count.
  The snapshot carries `accounts.json` and the key `pem_path` names, because a
  ledger without the configuration that names its sessions is not restorable, and
  the count it refuses on is zero accounts — `sqlite3.connect` creates an empty
  database, so a wrong `--db` would otherwise snapshot one and report success. What
  it does **not** do is get itself off the NAS: the folder is on the same disks as
  the ledger, and pointing the NAS's own backup tool at `backups/` is what makes it
  survive a disk.
- **The image builds here now, and the build has to run inside WSL.** The Linux
  engine is Docker Desktop's and its WSL integration is what makes `docker build`
  and a bind mount behave like the NAS: `tools/rehearse_local.sh` builds the image
  from the checkout, serves Enable Banking from `tools/eb_stub.py`, and walks the
  wizard, the snapshot and the restore. Run it from a WSL shell and not from a
  Windows one — on a Windows path Docker Desktop makes up the bind-mount
  ownership, so the check that a `/config` owned by someone else is *refused*
  stops meaning anything. The image the NAS pulls is still CI's:
  `.github/workflows/image.yml` on a `v*` tag, linux/amd64, after `pytest` and the
  bundle build pass, published as `ghcr.io/lucapaganin/amonhen:<tag>` and `:latest`
  — the lower-case name has to match `image:` in `docker-compose.yaml`, or the NAS
  pulls nothing. Keep the `uv` image tag in the Dockerfile at the version that
  wrote `uv.lock`: the lock is revision 3 and older uv binaries refuse to read it.
- **`.env` is loaded at import, and the shell wins.** `settings._load_env_file` reads
  the `KEY=VALUE` lines before any tunable is read, so `uv run amonhen serve` and
  docker compose see the same file — the class of bug where the key is in `.env` and
  the process is not. A variable already in the environment is left alone, and the
  parsing is ours because `python-dotenv` only arrives as a transitive extra of
  `uvicorn[standard]`.
