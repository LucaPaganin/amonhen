# CLAUDE.md — AmonHen

## Project

`amonhen` is a personal finance monitoring system that unifies every
connected bank account into one reconciled double-entry ledger, so spending
and runway can be computed instead of guessed. It replaces the old
Enable Banking → Actual Budget connector that used to live in this repo; that
path (actualpy client, rule patches, `state.json`, Flask server, scheduler)
was removed in the phase 1 cutover and is gone from the branch.

The product definition is `desiderata-monitoring-finanziario.md` (Italian):
read the sections a slice touches **before** implementing it, and section 9 for the
order of work and the status of each phase. Keep it true in the same change —
a decision that adds, removes or changes a requirement edits the spec alongside
the code, bumps its version line and says what changed. A spec that trails the
code is worse than none, because the next slice implements the old product.

A section of the spec is written as a word, never with the section sign:
"sezione 5.12" in Italian, "section 5.12" in English — in replies, the spec,
`CLAUDE.md`, the README, the backlog, commit messages and comments alike. The
person reading asked for it.

## Stack

- Python 3.13+, `uv` for package management
- `sqlite3` from the standard library for the ledger — no ORM
- `requests`, `PyJWT[crypto]`, `cryptography` for the Enable Banking client
- `pytest` + `responses` for tests
- No Flask, no actualpy, no scheduler library: the sync loop is a `time.sleep`
  loop and the HTTP API arrives with phase 2 (FastAPI + React PWA)

## Entry point

```bash
uv run python -m amonhen <command>
uv run amonhen <command>              # the same entry point, as an installed script
```

Global options come **before** the subcommand: `uv run amonhen --db <path> validate`
(`--db` is how you point a command at a copy of the ledger).

Commands: `sync`, `daemon`, `serve`, `import`, `accounts`, `account-add`,
`spend`, `balances`, `anchor`, `balance-check`, `categorize`, `rules`,
`rule-add`, `rule-remove`, `category-add`, `category-rename`, `metrics`, `category-flags`, `account-flags`,
`split`, `set`, `budget`, `budgets`, `anomalies`, `suggest`, `llm-suggest`,
`validate`, `backup`.

## Architecture in one line

`sync`/`import` → normalizers (`providers/`, `adapters/`) → `IncomingTransaction`
→ `Ledger.record` (dedup + pending→booked) → postings in SQLite →
`merchants.apply_transfer_rules` → `transfers.link_transfers` → `spend_between` / `balance` / `check_balance`.

## File map

|File|Role|
|---|---|
|`amonhen/settings.py`|Paths and tunables, each overridable via `AMONHEN_<NAME>`; loads `.env` first|
|`amonhen/models.py`|`Account`, `Posting`, `IncomingTransaction`, decimal helpers|
|`amonhen/db.py`|Schema for accounts, transactions, postings, transfer_links, rules, tags, transaction_tags, budgets, budget_months, budget_items, merchant_suggestions, account_balances, settings, held_transactions|
|`amonhen/dedup.py`|`content_hash` fallback identity (whitespace/case normalized)|
|`amonhen/ledger.py`|`Ledger`: accounts, `record`, invariants, spend/balance queries|
|`amonhen/config.py`|Reads **and writes** `accounts.json`: Enable Banking credentials, accounts and the `passthrough` declarations; `setup_state` answers the first-setup screen for a file that does not exist yet|
|`amonhen/sync.py`|`SyncService`: per-account fetch → normalize → ledger, then links transfers; `run_period` is one account over a chosen period, window by window; `SyncBusy` is the process-wide guard on one run at a time|
|`amonhen/transfers.py`|Transfer candidate graph, weights, link review state|
|`amonhen/matching.py`|Exact maximum-weight bipartite matching (Hungarian)|
|`amonhen/merchants.py`|Merchant normalization, the rules on the description and their application|
|`amonhen/metrics.py`|Burn, episodic accrual, runway, the month against its usual pace, the dashboard series, and the statistics per category|
|`amonhen/budgets.py`|Desiderata 5.12: a ceiling per category and month (a default from a month on, a month's own override) and the expenses planned inside it|
|`amonhen/anomalies.py`|Deterministic, explained spending outliers|
|`amonhen/classifier.py`|Char n-gram logistic proposals for uncovered merchants|
|`amonhen/llm.py`|The one place a chat-completion request is built, sent and parsed|
|`amonhen/suggestions.py`|Optional LLM proposals for merchants never seen|
|`amonhen/api.py`|FastAPI surface (transactions, review, categories, rules, budgets, anomalies, suggestions, statistics, dashboard series, first setup) and PWA host; `/callback` answers 303 to `/?setup=1`|
|`amonhen/backup.py`|`make_snapshot`: a dated snapshot of the living ledger (SQLite's backup API, not a file copy) plus the configuration it needs, a manifest, and the retention that keeps it bounded|
|`amonhen/providers/enable_banking.py`|EB HTTP client (JWT, windows, pagination, 429 backoff, balances)|
|`amonhen/providers/eb_normalize.py`|Raw EB payload → `Account` / `IncomingTransaction` (pure)|
|`amonhen/adapters/csv_adapter.py`|CSV import with a `CsvProfile` per bank layout|
|`amonhen/csv_import.py`|The mapping the import screen sends, as a `CsvProfile` built at runtime|
|`amonhen/adapters/ofx_adapter.py`|OFX 1.x SGML and 2.x XML import|
|`amonhen/cli.py`|Argument parsing and the command implementations|
|`web/src/components/CreditCard.tsx`|One credit of *Accrediti da chiarire*: the type, then the category, and the rule on request|
|`web/src/components/OpeningRecalc.tsx`|Re-deriving an account's opening behind a preview of what it moves, closed at the foot of the account's panel (Conti and the wizard's *Saldi e verifica*)|
|`web/src/screens/Guide.tsx`|Desiderata 5.14: a card per concept, the only place the pages explain; `components/Help.tsx` is the `?` that opens one|
|`web/src/screens/Statistics.tsx`|Desiderata 5.15: each category over the last complete months, the median and the mean, and its months on request|
|`web/src/components/TagEditor.tsx`|The tags of one movement, in its sheet; `useTags.ts` is the list every screen reads|
|`web/src/components/VirtualAccounts.tsx`|The virtual accounts under **Conti**: what each holds, how many movements put it there, and the movements on request (`/api/virtual-accounts`, `/api/transactions?virtual_account_id=`)|
|`web/src/components/PeriodRange.tsx`|A period of two dates, handed over only when valid: the dashboard's *Personalizzato* and Movimenti's *Periodo*|
|`web/src/components/PeriodSync.tsx`|The period sync in an account's panel under **Conti**: the dates, a line per window, the preview, and the held probable duplicates with *Scrivi* / *Scarta*|
|`web/`|React PWA source (recharts for the dashboard charts); the sections are declared once in `web/src/components/Navigation.tsx`, and five go in the bar, the others under *Gestione* in the drawer and the rail, the same list on phone and PC; the first-setup wizard (desiderata 5.10) is one of them — `Configurazione`, `inBar: false`; built to `web/dist`, served by the API|
|`tools/dump_raw.py`|Dumps raw EB payloads to disk, for regenerating fixtures|
|`tools/anonymize_dump.py`|Turns raw dumps into committed fixtures|
|`tools/eb_stub.py`|A stand-in for Enable Banking that serves the anonymized fixtures, so the first setup can be walked without a real consent (signs and verifies nothing)|
|`tools/rehearse_local.sh`|Rehearses the first start in containers inside WSL: builds from the checkout, proves the `/config` ownership the NAS needs, walks the wizard against the stub, then the snapshot and the restore|
|`tests/fixtures/enable_banking/`|Anonymized real payloads used by provider tests|
|`tests/fixtures/imports/`|Synthetic CSV/OFX fixtures|

## Module map

|Module|Public surface|
|---|---|
|`settings`|`ROOT`, `DB_PATH`, `CONFIG_FILE`, `EB_API`, `SYNC_INTERVAL_HOURS`, `UNCATEGORIZED`, `CREDITS_REVIEW_FROM`, `TRANSFER_MAX_GAP_DAYS`, `MANUAL_PAIR_MAX_GAP_DAYS`|
|`models`|`Account`, `Posting`, `IncomingTransaction`, `parse_decimal`, `format_decimal`|
|`db`|`connect`, `initialize`, `open_ledger_db`, `LedgerConnection`, `deferred_commits`|
|`ledger`|`Ledger` (with `preview_batch`, `probable_duplicate`, `held_transactions`, `decide_held`, `mirror_transfer`, `mirror_of`, `set_computed_balance`, `unrecognized_balances`, `opening_from`, `anchor_opening`, `record_valuation`, `tag`, `tags`, `set_tag_flag`, `delete_tag`, `tags_of`, `add_tag`, `set_tags`, `remove_tag`), `BalanceCheck`, `DeletedTotal`, `Deletion`, `PENDING_WINDOW_DAYS`, `COUNTED_SOURCES_SQL`, `UNRECOGNIZED_SOURCES_SQL`, `bank_balance_source`, `TRANSFER_CLEARING`, `VALUATION_PREFIX`, `INVESTMENTS_ACCOUNT`, `CREDITS_WHERE`, `RARE_SQL`, `ESSENTIAL_SQL`, `SPENDING_SQL`, `CONTRIBUTION_SQL`|
|`dedup`|`content_hash`, `normalize_description`|
|`config`|`MonitorConfig`, `ConfiguredAccount` (with `max_window_days`), `Passthrough`, `load_config`, `setup_state`, `save_credentials`, `save_account`, `rename_account`, `remove_account`|
|`sync`|`SyncService` (with `settle`, `due_in`), `sync_limit`, `SyncResult`, `AccountSyncResult`, `SyncBusy`, `PeriodInvalid`, `PeriodSyncResult`, `WindowReport`, `PeriodMovement`|
|`transfers`|`link_transfers`, `link_passthrough_legs`, `pair_candidates`, `transfer_amount_total`|
|`matching`|`max_weight_matching`|
|`merchants`|`merchant_name`, `rule_key`, `matching_rule`, `Rule`, `Movement`, `RuleBook`, `ACTIONS`, `categorize`, `apply_transfer_rules`, `apply_rule_changes`, `rule_usage`, `preview`, `deleting_rule`|
|`metrics`|`compute_metrics`, `Metrics`, `LedgerScope`, `month_reading`, `MonthReading`, `MonthCategory`, `spending_statistics`, `SpendingStatistics`, `CategoryStatistics`, `SeriesStatistics`, `usual_spending`, `spend_by_category`, `monthly_flows`, `net_worth_series`, `latest_balances`|
|`budgets`|`budget_status`, `set_default`, `set_month_override`, `ItemFields`, `add_item`, `update_item`, `delete_item`, `get_item`, `copy_items`, `fitting`, `move_day`, `month_of`, `month_bounds`, `parse_month`, `PRIORITIES`|
|`anomalies`|`detect_anomalies`, `Anomaly`|
|`classifier`|`CharNgramClassifier`, `propose_categories`, `apply_proposals`|
|`suggestions`|`LlmConfig`, `llm_config`, `unseen_merchants`, `propose_for_unseen`|
|`api`|`create_app`|
|`backup`|`Snapshot`, `make_snapshot`|
|`providers`|`EnableBankingClient` (`fetch_transaction_windows` → `FetchedWindow`), `session_accounts`, `ConsentExpiredError`, `RateLimitedError`, `normalize_transaction`, `normalize_account`, `iban_of`|
|`adapters`|`parse_export`, `parse_csv`, `parse_ofx`, `CsvProfile`, `REVOLUT`, `FINECO`, `ACTUAL`|
|`cli`|`main`, `build_parser`|

## Read this before you touch that

The rules that used to fill this file live in `docs/`, one page per subject, moved there
word for word. Read the page before changing what it covers, and keep it true in the same
change, like the spec.

|Touching|Read|
|---|---|
|Movements, notes, deletions, balances, the opening, the 5.4 check, net worth, WAL, the broker|`docs/ledger.md`|
|Pairing, giroconti, `passthrough`, mirrors|`docs/transfers.md`|
|Rules, Da confermare, proposals, the classifier, the LLM, anomalies|`docs/rules-and-review.md`|
|Sync, periods, held duplicates, consents, `accounts.json`, the key, CSV import|`docs/sync-and-banks.md`|
|Metrics, `LedgerScope`, the dashboard, the statistics, contributions, budgets|`docs/metrics-and-budgets.md`|
|Anything in `web/`|`docs/frontend.md`|
|The image, snapshots, `.env`|`docs/operations.md`|

## Non-obvious things to know before changing code

- **Dedup is two-tier and both tiers matter.** `external_id` (provider
  `entry_reference`/`transaction_id`, or a bank export's own reference) is
  checked first; otherwise `content_hash(account, date, amount, description)`
  decides. The hash is the only discriminator in the overlap zone between PSD2
  sync and file import, which is why `normalize_description` collapses
  whitespace and case.
- **The content hash is not a uniqueness constraint.** Real data contains
  identical transactions on the same day (four €250 top-ups, in the live
  Revolut account). When a hash match exists but both rows carry different
  provider ids, the new row is inserted with a suffixed hash so the base hash
  stays usable for the import path. Rows without provider ids are collapsed.
  Do not reintroduce a `UNIQUE` index on `content_hash`.
- **Pending → booked is a promotion, not an insert.** A booked row matching a
  pending row on (account, amount, ±3 days) updates the pending row in place,
  and a pending row arriving after its booked twin is ignored. The `PDNG`
  vs `BOOK` distinction must survive.
- **Transfers are excluded from spending by construction.** A transfer leg's
  balancing posting goes to the `Transfer clearing` virtual account instead of
  a category account, so `spend_between` never sees it. Candidates are equal
  magnitude, opposite sign, different real accounts, at most
  `settings.TRANSFER_MAX_GAP_DAYS` apart (2; a pairing by hand reaches
  `MANUAL_PAIR_MAX_GAP_DAYS`, 7).
  What corroborates a pair is the IBAN each bank printed on its own leg: a leg
  naming the *other* account is evidence, and a leg naming any other account
  contradicts the pair — an amount coincidence is exactly what the matcher
  exists to refuse, and two credits of the same amount on the same day used to
  be a coin flip. When an account's own IBAN is unknown the pair falls back to
  counting who named a counterparty at all, and the method records it
  (`…-unverified`). Ambiguity inside that graph is resolved exactly by
  `max_weight_matching`, never greedily: a locally best pair can block a larger
  total.
- **No call to the model starts by itself.** `/api/llm-suggest` is reached from a
  press in the queue and from the `llm-suggest` command; there is no effect, timer or
  background loop that asks in someone's place.
- **The mortgage instalment is gone on purpose.** It used to be a `settings`
  row feeding the runway denominator; it is not a concept any more
  (`compute_metrics` takes no such argument, there is no `/api/settings`
  endpoint, and `initialize` deletes a leftover `mortgage_monthly` key). A
  mortgage payment is a movement like any other, so if it should count it
  belongs in a category. Do not reintroduce a fixed monthly cost that is not a
  movement.
- **`API_VERSION` in `api.py` and `REQUIRED_API_VERSION` in `web/src/App.tsx`
  move together.** The API serves `web/dist` from disk on every request while the
  Python process keeps running its old code, so a new bundle against an old
  server is a normal state; without the handshake the app rendered nothing at all
  when a payload was missing a key. Bump both whenever a response shape changes: the app then says the server is stale instead of
  crashing. What each version changed is in the comment above `API_VERSION`.
- **The API has no authentication** because it is served behind Tailscale and
  never exposed publicly. Do not add a public ingress without adding auth.
- **Spending is net of refunds, and `ledger.SPENDING_SQL` is the only definition.**
  Money out counts; money in counts when it sits on a category that is not `income`
  and is not `Uncategorized`, and its opposite posting takes the spending down in
  the month it arrived. `spend_between`, `compute_metrics`, `month_reading`, the
  charts and the budgets read that fragment, so a reading can be negative. Nothing
  pairs a refund with a spend, and nothing lists who still owes what. A credit left
  in `Uncategorized` counts as nothing here and as income in the charts, as it
  always did. `income` is a category flag: `_add_income_flag` sets it once, on the
  categories that held only credits, because an unmarked category counts its
  credits as refunds and the first start would otherwise net every salary. A new
  income category has to be marked by hand. The anomalies, the queue and the
  proposals stay on outflows.
- **PSD2 returns only ~90 days regardless of the requested range** (verified:
  asking for 2026-01-01 returned rows from 2026-06-14). Deep history exists
  only through `import`, which is why the 6- and 24-month metrics depend on
  backfill, and why import is a prerequisite rather than an extra.
- **Fixtures are anonymized real payloads.** Never commit raw dumps under
  `dumps/` (gitignored) or add real names, IBANs or amounts to
  `tests/fixtures/`. Regenerate with `tools/anonymize_dump.py`.

## Working on this checkout

- **The ledger worth testing against is a copy, and it is not in the repo.** The
  real ledger lives outside version control: `dumps/` and `mytest*` are
  gitignored. Copy it before a destructive experiment, point the command at the
  copy with the global `--db` (`uv run amonhen --db dumps/verify.db serve …`),
  delete the copy when done. **The configuration needs a copy too**: `--db` moves
  the ledger only, and the app writes `accounts.json` — deleting an account, the
  setup wizard, the OAuth callback — so a server on a copied ledger still edits the
  real configuration. Serve with `AMONHEN_CONFIG_FILE` pointing at a copy whose
  `pem_path` is absolute (relative, it resolves next to the copy and the app opens
  on the wizard). A UI walk of the account deletion once took a real entry out of
  the checkout's `accounts.json`; it had to be rebuilt from `dumps/`. `amonhen.db` in the repo root is an **empty shell**,
  so a command that finds nothing is usually pointed at it. Never commit raw
  dumps, or real names, IBANs and amounts — `tools/anonymize_dump.py` turns a
  dump into a fixture and needs `dumps/.anonymize-salt`, which is deliberately
  outside the repo.
- **The API serves `web/dist` from disk on every request, the Python process
  keeps its old code.** A rebuilt bundle therefore needs no restart, a Python
  change does: `npm --prefix web run build`, then restart. The handshake
  (`API_VERSION` / `REQUIRED_API_VERSION`) is what makes the app say the server
  is stale instead of rendering nothing.
- **The suite keeps its own configuration.** `tests/fixtures/config/minimal.json`
  is what the API and CLI tests point their app at, and `.env` is never read by a
  test: the defaults are the operator's `accounts.json` and `.env`, neither of
  which is in version control, so a test that read them would pass only on the
  machine that happens to have one. Eleven of them did, until the first CI run on
  a clean checkout found it. Run the suite from a tree without those files
  (`git archive HEAD | tar -x -C /tmp/x`) when touching anything that reads the
  configuration.
- **Verifying UI work means running it.** Start the server on a copy, drive a
  real browser tab and read the DOM; for anything visual, screenshot it and have
  a vision model describe the image. "The component renders this" is not
  evidence that the screen shows it.

## Ledger schema

One SQLite file (`amonhen.db`, overridable with `AMONHEN_DB_PATH`), fifteen tables. The
ledger's shape is the first four, and **a transaction has no category column**: the
category lives on a posting, which is what makes an internal transfer not spending
by construction.

|Table|Columns|Holds|
|---|---|---|
|`accounts`|17|One row per real account, virtual account (transfer clearing, an investment destination) and category — `type` is what separates them. `episodic` / `essential` are the flags the metrics read; `income` says money in on a category is income, not a refund; `contribution` that it covers every expense; `description` is what a category is about, in a person's words; `investment` marks the broker, whose cash is declared by hand; `reimport_deleted` decides whether the next sync writes back the movements deleted from this account; `computed_balance` makes the net worth read the account from its postings instead of a declaration|
|`transactions`|17|One row per movement: `account_id`, `date`, `amount` (signed text, cents-exact), `description`, `status` (`BOOK` / `PDNG`), `external_id`, `content_hash` (the dedup key), `source` (`psd2` / `import`), `source_file`, `raw_payload` (the bank's payload verbatim), `counterparty`, `counterparty_account`, `currency`, `created_at`, `notes` (local, written by a person, never by an ingest path), `mirror_of` (the movement this row is the other half of, written by a transfer rule towards an account added by hand)|
|`postings`|5|The double-entry legs: `transaction_id`, `account_id`, `amount`, `note`. A spend is one leg on the real account and one on a category account; a transfer is one leg on each real account, or on the virtual clearing account when only one side is in the ledger; a split is several category legs on one transaction|
|`deleted_transactions`|19|A movement a person deleted, copied whole: the identity the ledger dedupes by, the bank's payload, the note, the tags a person wrote, when it went and when it came back. It is what keeps the next sync from writing the movement in again|
|`transfer_links`|5|A pairing, proposed or confirmed: the two legs, `confidence`, `method`, `confirmed_by_human`|
|`rules`|8|`id`; `key` (the text lower-cased, or the expression as typed — case is part of an expression, `\D` is not `\d`); `pattern` (what a person typed: a text, or `/an expression/`); `action` (`category` / `delete` / `transfer` / `tag`); `target` (the category, the destination or the tag, NULL for a deletion); `account_id`, `amount_min`, `amount_max` (the conditions, sizes without sign). One rule per text and conditions, and for a tag rule per tag too: the unique index `rules_identity` is created by `_allow_tag_rules`, and `_generalize_rules` rebuilt the old `key, pattern, category` table|
|`tags`|4|A free label: `name`, and the same `episodic` / `essential` flags a category has|
|`transaction_tags`|3|Which movement carries which tag, and `by_rule`, who put it there|
|`account_balances`|4|What a bank declared, one row per `(account, date, source)`: the available and booked figures coexist so the 5.4 assertion can check each|
|`budgets`|4|A category's default ceiling from `from_month` (YYYY-MM) on; a NULL `amount` removes it from that month|
|`budget_months`|4|One month's own ceiling for a category, over the default|
|`budget_items`|9|An expense planned inside a category's ceiling for one month: description, amount, optional date, priority, note|
|`merchant_suggestions`|5|A merchant → category proposal with its `source` and `decision` (`pending` / `accepted` / `dismissed`)|
|`held_transactions`|11|A movement a period sync did not write because it looks like one the other ingest path wrote under a different description: the movement as it arrived, its occurrence, the row it resembles (`twin_id`), and the `decision` (`pending` / `written` / `discarded`). One row per `(account_id, key)`|
|`settings`|2|Key/value odds and ends|

Three shapes wrap the same movement: `IncomingTransaction` (`models.py`, 13 fields)
is what a source reports before the ledger assigns ids, the balancing posting and
the hash — a note is not part of what a source reports, which is why the class
does not carry one; the row above is what is stored; `Transaction`
(`web/src/types.ts`, 16 keys) is what the API returns — `category` is the posting's category (null when
there are several), `merchant` is the normalized name, and `review_state` /
`proposed_category` exist only in the queue.

## Common tasks

|Task|Where to look|
|---|---|
|Change what the product must do|The spec (`desiderata-monitoring-finanziario.md`) first, then the code — section 9 holds the order of work and the status of each phase|
|Change the sync cadence|`AMONHEN_SYNC_INTERVAL_HOURS` or `daemon --interval-hours`|
|Sync one account over a past period, or fill a gap|The account's panel in **Conti**, *Sincronizza un periodo* (preview first) — or `uv run amonhen sync --account <name> --from YYYY-MM-DD --to YYYY-MM-DD [--preview]`. Then decide the held probable duplicates in the same panel. A bank that refuses 30-day ranges gets `max_window_days` in its `accounts.json` entry|
|A bank refuses with 429|The body is in the logs (`Enable Banking rate limited (…)`), the account in **Conti** says so, and the other accounts carry on: see `docs/sync-and-banks.md`. Every press of *Sincronizza* spends the quota, a restart does not|
|Ask the banks for data now|The **Sincronizza** button in the app's top bar (`POST /api/sync`), or `uv run amonhen sync`|
|Mark a movement without touching what the bank said|The note field in the movement sheet (`PUT /api/transactions/{id}/notes`) — the only field of a movement the app writes|
|Track an account no bank exposes (the Revolut deposit)|**Conti**: add it by hand, then a transfer rule in **Categorie e regole** with the text the bank prints and the account as *Verso* — the rule writes the other half of every transfer on it. Declare today's balance and *Ricalcola il saldo iniziale* (it previews the opening first), then turn on *Saldo dai movimenti* so the net worth reads it; correct interest with a movement. CLI: `account-flags <name> --computed-balance`|
|Undo a deletion|The trash under the account in Conti (`POST /api/deleted/{id}/restore`), or the account's `reimport_deleted` flag for all of them at the next sync|
|Deploy a new image to the NAS|Follow README, *Updating safely*: rehearse any migration on a copy of a recent snapshot, tag `v*` and let CI publish, snapshot right before, pin `AMONHEN_TAG`, then `docker compose pull && docker compose up -d` and verify. A schema change is one-way, so its rollback restores the snapshot as well as the tag|
|Back up the ledger, or go back to a snapshot|`uv run amonhen backup --dest <dir> [--keep N]` writes `<dir>/<2026-09-26T101500Z>/`; restoring means stopping the app, removing `amonhen.db-wal`/`-shm`, copying that folder's `amonhen.db` over the live one, and `chown 10001:10001` inside the container (README, *Backup and restore*)|
|Rehearse the first start before the NAS does|`tools/rehearse_local.sh` inside WSL: it builds from the checkout, serves `tools/eb_stub.py` as the bank, and prints what to walk in the browser|
|Map a bank's CSV layout|The **Importa** section of the app: choose the file, then the columns — or add a `CsvProfile` in `adapters/csv_adapter.py` plus a synthetic fixture when the layout must be a named profile|
|Reset an account|Delete its rows / the database file, then `sync` and `import` again|
|Re-derive the opening balance|`uv run amonhen balances` then `uv run amonhen anchor`|
|Check duplicates or gaps|`uv run amonhen validate`, `uv run amonhen balance-check`|
|Inspect the ledger|`sqlite3 amonhen.db` — accounts, transactions, postings, transfer_links (see *Ledger schema* above)|
|See the balances behind the net worth|`sqlite3 amonhen.db "select * from account_balances"` — written by `sync`, `balances` and `anchor`|
|Plan a month|The **Budget** section: a category's ceiling (*Da questo mese in poi* or *Solo questo mese*), then *Aggiungi voce* — from scratch or from a past movement — or *Copia dal mese prima*; `uv run amonhen budget <category> <amount> [--from YYYY-MM]` sets a default from the command line|
|See what a category usually takes|**Statistiche**: the median and the mean over 6, 12 or 24 complete months; the **Budget** row says *di solito*, the median of the six before that month|
|Change a dashboard chart|The series in `metrics.py`, then the panel in `web/src/screens/Dashboard.tsx`; the API returns the sums, the client only draws them|
|Change a colour, a spacing or the type scale|The `:root` tokens in `web/src/styles.css`; the font and its licence are in `web/src/assets/`|
|Regenerate parsing fixtures|`uv run python tools/dump_raw.py` then `uv run python tools/anonymize_dump.py dumps`|
|Connect a new bank|**Configurazione** in the app (the drawer, or the rail above 1024), *Banca* step (`POST /api/setup/connect`, then the login happens at the bank) — or `http://<host>:8000/connect?bank=Revolut&country=IT`, the same route for a script. Then `uv run amonhen sync`, unless the wizard's *Primo sync* step already did it|
|First setup on a fresh install|The app opens on the wizard by itself while `/api/setup` answers `configured: false` — *Credenziali* (application id, PEM key, redirect URL, holder: the URL it shows is what goes into the Enable Banking dashboard), *Banca*, *Conti*, *Primo sync*, *Saldi e verifica*. `PUT /api/setup/credentials` creates `accounts.json` and `private.pem`, so there is nothing to write by hand|
|Add or change a categorization rule|The **Categorie e regole** section of the app — under the category it assigns, or *Nuova regola* for a rule with conditions or one that deletes or records a transfer (the sheet previews what it takes) — or `uv run amonhen rule-add "addebito sdd" "Bollette"` (the text the description contains, or `/an expression/`); `uv run amonhen rule-remove "addebito sdd"` releases its movements|
|Add or flag a tag, or tag movements|The block *Tag* in **Categorie e regole**, the movement's sheet, *Seleziona* in **Movimenti**, or a rule whose action is *Mette un tag*|
|Explain a concept, or change how a figure is computed|The card in `web/src/screens/Guide.tsx`, in the same change|
|Clear up a credit|**Da confermare**, *Accrediti da chiarire*: the type, the category, *Crea una regola* when it repeats|
|Rename a category|Open its row in **Categorie e regole** and change the name — or `uv run amonhen category-rename <name> <new name>`|
|Add a category|The same section, *Nuova categoria* (or the picker on a movement, or a proposal's select) — `POST /api/categories`. A category categorizes nothing by itself|
|Run the UI locally|`uv run amonhen serve` and `npm --prefix web run dev` (Vite proxies `/api`)|
|Build the PWA|`npm --prefix web run build` — the API serves `web/dist`|

## What this system deliberately does NOT have

If asked to add any of these, push back first — the desiderata excludes them
on purpose (sections 3 and 8):

- AI in the synchronous sync path, or anywhere it produces numbers
- Natural-language queries over the ledger; hand-written SQL wins
- Generative anomaly detection where a robust statistic exists
- Broker API integration, TWR/IRR, spending forecasts, budget optimization. The
  long-term plan (section 5.16) is not an exception: its projections are arithmetic on
  scenarios a person writes, its portfolio is declared by hand, and it shows the
  consequences of a split without proposing one
- A model inside the plan: the periodic portfolio review happens outside the app, on a
  snapshot (section 8), and tax parameters are data a person writes with their source
- Multi-user, multi-currency, sharing
- Native app (the UI is a PWA)
- Balance-only providers (Binance, Coinbase, eToro)

## Reference for deeper questions

- `desiderata-monitoring-finanziario.md` — the product definition and roadmap.
- `../bridge-bank/` — the original full implementation; useful for Enable
  Banking field semantics and transaction parsing edge cases.
- `../bridge-bank/docs/` — longer explanations of the same concepts.
