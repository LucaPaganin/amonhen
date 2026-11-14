# The sync, the banks and the configuration

Part of what `CLAUDE.md` says before changing code. A rule that changes changes here, in the same change as the code.

- **The sync speaks to a bank through a port, and only the composition root picks
  which.** `amonhen/ports/bank.py` is `BankProvider`: connected accounts, an account's
  details, movements (all or nothing, or window by window), declared balances, and three
  errors — `ConsentExpired`, `RateLimited`, `BankUnavailable` — all in the application's
  types: `IncomingTransaction`, `BankAccount`, `DeclaredBalance`, `FetchedWindow`.
  `SyncService` and the `balances` command import nothing from Enable Banking and nothing
  from `requests`. `amonhen/adapters/enable_banking/` is the one implementation: `client.py`
  speaks the HTTP API, `normalize.py` reads its JSON, and `provider.py`
  (`EnableBankingProvider`) implements the port and translates, errors included, keeping
  the provider's words because the app shows them. `amonhen/composition.py` is the only
  place a client or a provider is built: the API asks for `bank_factory` with `Depends`,
  the CLI calls `bank_provider`, and a provider lives for one run because `accounts.json`
  can change under a running server. The consent flow (`/connect`, `/callback`, the
  wizard's *Banca* step) is outside the port on purpose — it is the most provider-specific
  part, and a port drawn from one provider's redirects would be a guess — so those routes
  use the client from the composition root and still read its `requests` errors. Tests
  replace the bank at the same seams: `app.dependency_overrides[bank_factory]`,
  `cli.bank_provider`, or `tests/memory_bank.py`, which implements the port in memory.

- **A period is a sync of one account, and it moves no cursor.** `SyncService.run_period`
  (`amonhen sync --account --from --to [--preview]`, `POST /api/sync/period`, the
  *Sincronizza un periodo* action in an account's panel) checks the period before the
  lock and the bank — `PeriodInvalid`, a 422 — and then takes the same lock as `run`.
  `EnableBankingClient.fetch_transaction_windows` (through the port's `transaction_windows`)
  answers one `FetchedWindow` per window
  with its movements or its error: a 400/422 is read as the bank refusing the range and
  halves the width (down to one day, and the narrower width holds for the rest of the
  period), anything else fails that window alone, and a dead consent raises because
  every window would fail the same way. Each window is its own `record_batch`, so a
  failed one does not discard the others; windows are whole days because the batch
  numbers identical movements of one day (`:r2`), and a day split across two batches
  would number them differently. The incremental cursor is `MAX(date)` of the account
  and a past period adds nothing newer, so it does not move; `start_sync_date` is
  neither read nor written. `link_transfers` runs with `since` at the start of the
  period, not `_earliest_start`, so legs older than every `start_sync_date` still pair.
  `max_window_days` in an account's entry of `accounts.json` (default 30) also narrows
  the incremental sync's windows.
- **A probable duplicate of an import is held, not written.** `record` and its preview
  share one decision, `Ledger._plan`, so `preview_batch` cannot promise what the write
  does not do. With `record_batch(..., hold_probable=True)` — the period sync only — a
  movement the plan would *insert* but whose account, day and amount match a row from
  the other `source` goes to `held_transactions` with the row it resembles: the content
  hash contains the description, and a bank that words a movement differently in PSD2
  and in its export would otherwise get it twice. The held row keeps the movement as it
  arrived and its occurrence, keyed like the ledger would key it, so the same period run
  again holds nothing twice; `decide_held` writes it through `record` (the dedup and the
  tombstones still have their say) or discards it, once, and a discard is remembered
  (`discarded` in the period's actions). The normal sync does not hold: it covers the
  last days, where an export rarely overlaps, and holding there would stall the queue.
- **The sync has one guard and one button.** `SyncService.run` takes a
  process-wide lock and raises `SyncBusy` when another run holds it, which is what
  makes `POST /api/sync` and the scheduled loop of `serve` safe in one process;
  the CLI and the daemon are separate processes with their own copy, so the guard
  costs them nothing. The endpoint is synchronous on purpose — the caller asked
  for this run, and the answer is what it wrote — and it answers 503 with the
  reason when `accounts.json` or the key cannot be read, 409 when a run is already
  going.
- **`serve` can run the sync loop in-process.** One process means one writer for
  the SQLite file; the container uses that instead of a second service sharing
  the volume. The loop opens its own connection per run, so nothing is shared
  across threads.
- **A 429 ends the account, not the sync.** `EnableBankingClient._get` tries three
  times (5 and 10 seconds), obeys a `Retry-After` up to 60 and gives up at once on a
  longer one, then raises `RateLimitedError`, an `HTTPError` carrying the bank's words,
  which are also logged; the adapter hands it on as the port's `RateLimited`. It used to wait 75 seconds per call and sit through a third
  useless pause on a daily quota: two calls held the whole run for 2.5 minutes, with the
  rules unapplied behind them. `_sync_account` asks nothing else of that account, the
  period stops at the window it hit, and `sync_limit` (settings `sync:limited:<id>`,
  `sync:last_read:<id>`, cleared by the next read that works) is what Conti shows. The
  limit is presumed daily and PSD2's, not proven: read the logged body when one arrives.
- **A restart is not a sync.** `_sync_loop` counts the interval from `sync:last_run`,
  written when any full pass ends, the button's included and one that hit a limit too.
  When no pass is due it calls `SyncService.settle` and sleeps what is left, so a deploy
  spends no quota and a process stopped halfway still gets its rules applied. A pass that
  never ended writes no key: the next start runs one. `_account_record` reads a stored
  IBAN instead of calling `/details`, which is one read of the quota per sync.
- **A consent can be dead even when the session looks authorized.** The Fineco
  session metadata still said `AUTHORIZED` while `/transactions` returned
  401/403, and its session listing still answered with four uids. Sync reports
  the error and continues with the other accounts, and the import path stays the
  recovery when the bank cannot be reached at all. Renewing means the wizard
  again — **Configurazione** (the drawer, or the rail above 1024) starts at *Conti*, and *Banca* is one
  tap back (`POST /api/setup/connect`) — or
  `<that address>/connect?bank=FinecoBank&country=IT`, which is the same
  authorization at the URL level for a script or a bookmark. Either way it only
  completes when three URLs agree: the address the browser reaches, `redirect_url`
  in `accounts.json`, and the callback registered in the Enable Banking dashboard.
  The live file still points at `<tailnet>:3000/callback`, the port of the Flask
  app this one replaced, where nothing listens; the wizard's credentials step is
  what rewrites it, from the origin the browser is on, and registering the derived
  address in the dashboard stays manual. The step refuses an `http://` address there
  unless it is on localhost, which only the rehearsal against the stub bank needs —
  Enable Banking registers none. Tailscale serves it as
  `https://<node>.<tailnet>.ts.net/callback` (`tailscale serve --bg
  localhost:8000`). When the two disagree the app answers `Enable Banking refused
  the request: 400 Redirect URI not allowed` and names the address it sent
  (`_auth_refusal`, `refusal_code`); the registered half is readable with `GET
  /application`, whose `redirect_urls` is the whole allowlist — an application
  registered for an earlier deployment holds that earlier address and nothing
  else.
- **A session can list its accounts as bare uids, or none.** Revolut and Fineco
  send the objects in `accounts_data`; a session with the uids alone in `accounts`
  used to throw the whole consent away, and `session_accounts` now turns a bare uid
  into `{"uid": ...}`. An empty session is asked once more (`GET /sessions/{id}`)
  before it counts as empty, and then both answers go in the log whole, as a
  WARNING (`Enable Banking session for … shared no account`) — the server prints
  nothing below WARNING, which is why the first PayPal attempt left no trace. The
  `session_id` stays in `last_connect` so the session can be asked about again,
  and the *Conti* step says when the last authorization wrote nothing.
- **A bare bank code is the last thing a description falls back on.** PayPal leaves
  the remittance empty and codes every movement `PAYMENT`, with the shop or the
  person only in `creditor` / `debtor`: the description used to read `PAYMENT` on
  every row. `_description` now takes remittance, note, the code's own
  `description`, then the counterparty, and the bare `code` only after it. The rows
  written before are re-derived from their payload by `db._describe_bare_codes`
  (description and hash, a suffixed hash keeps its suffix); Revolut and Fineco
  always carry a remittance, and a copy of the live ledger had no row it touched.
- **`accounts.json` has two writers, and neither is the only one.** The OAuth
  callback appends and refreshes entries: `save_account` keys on the account
  **uid** — a session id changes at every authorization while the uid does not, so
  a renewed consent *refreshes* the entry in place, keeping `notes`, which is the
  name the ledger knows the account by, and `start_sync_date`, which is the history
  it already imported, and only an account never seen before is added. Keying on
  the (session, uid) pair appended a second entry for the same account, which the
  ledger, matching by name, then merged into one account and re-imported the
  history under. A session names none of its accounts, so the callback names a new
  one from its details (`_suggested_name`: the bank, `carta` for a card, the
  currency) and `save_account` numbers a name already in the file — one Fineco
  consent used to write four entries all called "FinecoBank". The ledger finds a
  connected account by `external_uid` before its name (`ensure_account`), so a
  rename in the setup screen renames the ledger row too (`Ledger.rename_account`,
  at once from `PATCH /api/setup/accounts/{uid}`, else at the next sync), and a
  name another account holds is refused rather than merged into it: looking by
  name first kept the first name for good and sent a renamed account's movements
  into whichever account had held that name. The setup screen writes credentials and curates the same entries
  (`save_credentials`, `rename_account`, `remove_account`, behind `/api/setup`),
  and the two go through `_read_document` / `_write_document`, which read the file
  as the document it is and write it back — so a key nobody in the app knows about,
  the hand-written `passthrough` declarations for one, survives every write, and
  hand-editing stays possible because each command still reads the file at
  startup. The `actual` keys the old connector left in the file are ignored, and
  a write does not remove them: nothing reads them and nothing tidies them.
- **The private key is written and never read back.** `save_credentials` writes the
  pasted PEM to `pem_path` — resolved relative to the configuration file,
  `./private.pem` by default, so the same file works in the checkout and behind
  the container's `/config` mount — and chmods it 0600, refusing a payload that
  does not load as a private key before anything is written. `setup_state` answers
  `key_loads`, whether the file on disk loads as one, and `load_config` hands the
  path to the Enable Banking client. No endpoint returns the key and nothing logs
  it: the file is the only copy.
- **The app's CSV import is the command line's pipeline, with the mapping chosen on the file.** The
  browser sends the statement as text — JSON, capped at 8 MB, because the repo has no multipart — plus
  the columns a person picked; `amonhen/csv_import.py` turns that mapping into a `CsvProfile`, so a
  bank layout is data rather than a constant, and the rows go through the same `read_csv` →
  `record_batch` → `settle_after_ingest` path as `amonhen import` and the sync. Idempotency is the
  content hash, so importing the same file twice writes nothing. One deliberate difference from
  `parse_csv`: a row that does not read is reported with its line (and the parser's own English
  sentence) instead of refusing the whole file. A description is passed through
  `repair_mojibake` (`adapters/csv_adapter.py`): Revolut's Italian statement writes UTF-8
  decoded as Windows-1252 ("PiÃ¹Me"), and only text that turns back into valid UTF-8 is
  changed. The repair moves the content hash, so the six rows imported before it were
  rewritten by hand on the live ledger (description and hash, suffix kept).
