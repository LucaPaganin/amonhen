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
`rule-add`, `rule-remove`, `category-add`, `metrics`, `category-flags`, `account-flags`,
`split`, `set`, `budget`, `budgets`, `anomalies`, `suggest`, `llm-suggest`,
`validate`, `backup`.

## Architecture in one line

`sync`/`import` → normalizers (`providers/`, `adapters/`) → `IncomingTransaction`
→ `Ledger.record` (dedup + pending→booked) → postings in SQLite →
`transfers.link_transfers` → `spend_between` / `balance` / `check_balance`.

## File map

|File|Role|
|---|---|
|`amonhen/settings.py`|Paths and tunables, each overridable via `AMONHEN_<NAME>`; loads `.env` first|
|`amonhen/models.py`|`Account`, `Posting`, `IncomingTransaction`, decimal helpers|
|`amonhen/db.py`|Schema for accounts, transactions, postings, transfer_links, rules, budgets, budget_months, budget_items, merchant_suggestions, account_balances, settings, assistant_readings, budget_proposals, held_transactions|
|`amonhen/dedup.py`|`content_hash` fallback identity (whitespace/case normalized)|
|`amonhen/ledger.py`|`Ledger`: accounts, `record`, invariants, spend/balance queries|
|`amonhen/config.py`|Reads **and writes** `accounts.json`: Enable Banking credentials, accounts and the `passthrough` declarations; `setup_state` answers the first-setup screen for a file that does not exist yet|
|`amonhen/sync.py`|`SyncService`: per-account fetch → normalize → ledger, then links transfers; `run_period` is one account over a chosen period, window by window; `SyncBusy` is the process-wide guard on one run at a time|
|`amonhen/transfers.py`|Transfer candidate graph, weights, link review state|
|`amonhen/matching.py`|Exact maximum-weight bipartite matching (Hungarian)|
|`amonhen/merchants.py`|Merchant normalization, the rules on the description and their application|
|`amonhen/metrics.py`|Burn, episodic accrual, runway, savings flow, and the dashboard series|
|`amonhen/budgets.py`|Desiderata 5.12: a ceiling per category and month (a default from a month on, a month's own override) and the expenses planned inside it|
|`amonhen/anomalies.py`|Deterministic, explained spending outliers|
|`amonhen/classifier.py`|Char n-gram logistic proposals for uncovered merchants|
|`amonhen/llm.py`|The one place a chat-completion request is built, sent and parsed|
|`amonhen/suggestions.py`|Optional LLM proposals for merchants never seen|
|`amonhen/assistant.py`|Desiderata 5.9: a reading of the numbers already computed, and the guards on it|
|`amonhen/api.py`|FastAPI surface (transactions, review, categories, rules, budgets, anomalies, suggestions, assistant, dashboard series, first setup) and PWA host; `/callback` answers 303 to `/?setup=1`|
|`amonhen/backup.py`|`make_snapshot`: a dated snapshot of the living ledger (SQLite's backup API, not a file copy) plus the configuration it needs, a manifest, and the retention that keeps it bounded|
|`amonhen/providers/enable_banking.py`|EB HTTP client (JWT, windows, pagination, 429 backoff, balances)|
|`amonhen/providers/eb_normalize.py`|Raw EB payload → `Account` / `IncomingTransaction` (pure)|
|`amonhen/adapters/csv_adapter.py`|CSV import with a `CsvProfile` per bank layout|
|`amonhen/csv_import.py`|The mapping the import screen sends, as a `CsvProfile` built at runtime|
|`amonhen/adapters/ofx_adapter.py`|OFX 1.x SGML and 2.x XML import|
|`amonhen/cli.py`|Argument parsing and the command implementations|
|`web/src/components/OpeningRecalc.tsx`|Re-deriving an account's opening behind a preview of what it moves, closed at the foot of the account's panel (Conti and the wizard's *Saldi e verifica*)|
|`web/src/components/PeriodSync.tsx`|The period sync in an account's panel under **Conti**: the dates, a line per window, the preview, and the held probable duplicates with *Scrivi* / *Scarta*|
|`web/`|React PWA source (recharts for the dashboard charts); the sections are declared once in `web/src/components/Navigation.tsx`, and the first-setup wizard (desiderata 5.10) is one of them — `Configurazione`, `inBar: false`; built to `web/dist`, served by the API|
|`tools/dump_raw.py`|Dumps raw EB payloads to disk, for regenerating fixtures|
|`tools/anonymize_dump.py`|Turns raw dumps into committed fixtures|
|`tools/eb_stub.py`|A stand-in for Enable Banking that serves the anonymized fixtures, so the first setup can be walked without a real consent (signs and verifies nothing)|
|`tools/rehearse_local.sh`|Rehearses the first start in containers inside WSL: builds from the checkout, proves the `/config` ownership the NAS needs, walks the wizard against the stub, then the snapshot and the restore|
|`tests/fixtures/enable_banking/`|Anonymized real payloads used by provider tests|
|`tests/fixtures/imports/`|Synthetic CSV/OFX fixtures|

## Module map

|Module|Public surface|
|---|---|
|`settings`|`ROOT`, `DB_PATH`, `CONFIG_FILE`, `EB_API`, `SYNC_INTERVAL_HOURS`, `UNCATEGORIZED`|
|`models`|`Account`, `Posting`, `IncomingTransaction`, `parse_decimal`, `format_decimal`|
|`db`|`connect`, `initialize`, `open_ledger_db`, `LedgerConnection`, `deferred_commits`|
|`ledger`|`Ledger` (with `preview_batch`, `probable_duplicate`, `held_transactions`, `decide_held`, `mirror_transfer`, `mirror_of`, `set_computed_balance`, `opening_from`, `anchor_opening`), `BalanceCheck`, `DeletedTotal`, `Deletion`, `PENDING_WINDOW_DAYS`, `TRANSFER_CLEARING`|
|`dedup`|`content_hash`, `normalize_description`|
|`config`|`MonitorConfig`, `ConfiguredAccount` (with `max_window_days`), `Passthrough`, `load_config`, `setup_state`, `save_credentials`, `save_account`, `rename_account`, `remove_account`|
|`sync`|`SyncService`, `SyncResult`, `AccountSyncResult`, `SyncBusy`, `PeriodInvalid`, `PeriodSyncResult`, `WindowReport`, `PeriodMovement`|
|`transfers`|`link_transfers`, `link_passthrough_legs`, `pair_candidates`, `transfer_amount_total`|
|`matching`|`max_weight_matching`|
|`merchants`|`merchant_name`, `rule_key`, `matching_rule`, `Rule`, `Movement`, `RuleBook`, `ACTIONS`, `categorize`, `apply_rule_changes`, `rule_usage`, `preview`, `deleting_rule`|
|`metrics`|`compute_metrics`, `Metrics`, `LedgerScope`, `spend_by_category`, `monthly_flows`, `net_worth_series`, `latest_balances`|
|`budgets`|`budget_status`, `set_default`, `set_month_override`, `ItemFields`, `add_item`, `update_item`, `delete_item`, `get_item`, `copy_items`, `fitting`, `move_day`, `month_of`, `month_bounds`, `parse_month`, `PRIORITIES`|
|`anomalies`|`detect_anomalies`, `Anomaly`|
|`classifier`|`CharNgramClassifier`, `propose_categories`, `apply_proposals`|
|`suggestions`|`LlmConfig`, `llm_config`, `unseen_merchants`, `propose_for_unseen`|
|`api`|`create_app`|
|`backup`|`Snapshot`, `make_snapshot`|
|`providers`|`EnableBankingClient` (`fetch_transaction_windows` → `FetchedWindow`), `ConsentExpiredError`, `normalize_transaction`, `normalize_account`, `iban_of`|
|`adapters`|`parse_export`, `parse_csv`, `parse_ofx`, `CsvProfile`, `REVOLUT`, `FINECO`, `ACTUAL`|
|`cli`|`main`, `build_parser`|

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
- **A note is local, and that is why the sync cannot lose it.** `transactions.notes`
  is written by `PUT /api/transactions/{id}/notes` — the only field of a movement a
  person may rewrite, since amount, date and description are what the bank said and
  the 5.4 assertion compares that statement with the ledger — and by
  `_mark_restored`, which only ever hands a movement that has just been recreated
  the note its tombstone kept. Nothing in `record`, `_promote`, `_insert` or
  `_replace_postings` names the column, so a note survives the promotion that
  rewrites the row it hangs on and the whole re-import of a period. `search` reads it with the description and the
  counterparty: marking a movement is only useful if the mark can be found again.
- **Deleting is a write with a memory.** `DELETE /api/transactions/{id}` copies
  the row — identity, payload, note, status, and when it went — into
  `deleted_transactions` and removes it in one transaction. The tombstone's `key`
  is the bank's own `external_id` when the row had one, otherwise its
  `content_hash` **verbatim**, suffixes for repeated identical content included;
  `record` reads it after the dedup lookups, so a movement the ledger already
  holds is a duplicate whatever somebody deleted once, and only a row that is
  really absent can be suppressed. `_tombstone` recognises the movement in three
  ways, each one a relation the ledger already has: the same provider id, the
  same content from the *other* ingest path (an export carries no id, and the
  content hash is the only discriminator in that overlap), or the settled twin of
  a deleted pending movement — other status, same amount, within
  `PENDING_WINDOW_DAYS`. Never on content alone for a same-status row: four
  identical top-ups on one day are four movements, and deleting one must not
  swallow a surviving twin. `restore_deleted` writes through `record` with
  `restoring=True`, which lifts the tombstone's veto and nothing else, so a
  movement the ledger already holds comes back as a duplicate instead of a second
  row. Deleting a leg of a transfer rejects the link first — `transfer_links`
  cascades, and the other leg would otherwise stay posted to the clearing account
  with nothing on the row explaining why.
- **A deleted movement can come back, per account and one at a time.** The account
  flag `reimport_deleted` (off by default, set from the Conti panel) decides what
  the *next sync* does: on, `record` writes the movement in from the tombstone
  with its note and marks `restored_at` (`reimported` in the sync's actions); off,
  the movement is counted as `suppressed`. `POST /api/deleted/{id}/restore` is the
  same return for one movement, right now: it rebuilds the row from the payload the
  tombstone kept, hands it the note the tombstone held, and refuses a second time
  with 409. What comes back is the movement and its note, not its category: the
  restored row is on `Uncategorized` until the next `categorize` — which every sync
  runs — or a person decides, because a category is a decision about money, not a
  field of the bank's payload. `deleted_transactions()` is the
  trash the Conti panel shows, and it lists `restored_at IS NULL` only.
- **A period is a sync of one account, and it moves no cursor.** `SyncService.run_period`
  (`amonhen sync --account --from --to [--preview]`, `POST /api/sync/period`, the
  *Sincronizza un periodo* action in an account's panel) checks the period before the
  lock and the bank — `PeriodInvalid`, a 422 — and then takes the same lock as `run`.
  `EnableBankingClient.fetch_transaction_windows` answers one `FetchedWindow` per window
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
- **Transfers are excluded from spending by construction.** A transfer leg's
  balancing posting goes to the `Transfer clearing` virtual account instead of
  a category account, so `spend_between` never sees it. Candidates are equal
  magnitude, opposite sign, different real accounts, at most two days apart.
  What corroborates a pair is the IBAN each bank printed on its own leg: a leg
  naming the *other* account is evidence, and a leg naming any other account
  contradicts the pair — an amount coincidence is exactly what the matcher
  exists to refuse, and two credits of the same amount on the same day used to
  be a coin flip. When an account's own IBAN is unknown the pair falls back to
  counting who named a counterparty at all, and the method records it
  (`…-unverified`). Ambiguity inside that graph is resolved exactly by
  `max_weight_matching`, never greedily: a locally best pair can block a larger
  total.
- **An account's own IBAN comes from `GET /accounts/{uid}/details`.** A session
  lists uids and little else, so `normalize_account` cannot fill it from there;
  `SyncService._account_record` reads the details once per run and fills
  `accounts.iban` when it is empty (`iban_of` reads either payload shape).
  Best-effort: an expired consent leaves the IBAN null and the matcher simply
  cannot corroborate — the live state of FinecoBank, whose legs name no
  counterparty either, so nothing is lost.
- **A link carries a review state.** `transfer_links.confirmed_by_human` is
  0 for unreviewed, 1 for confirmed and -1 for rejected. `_candidates` skips
  any leg that already has a link row, so a rejected pair is never proposed
  again, and rejecting restores the `Uncategorized` category on both legs so
  the money counts as spending again. That "no" is the matcher's business
  only: for everything else a rejected leg is free — the rules
  (`_movement_rows`' `linked`), a manual pairing (`pair_candidates`), an own
  transfer (`mark_passthrough`, `link_passthrough_legs`). A leg can then hold
  its rejected row and a live one, and `transfer_link` returns the live one;
  `mark_transfer_pair` reuses a row only for the same two legs. Before this,
  correcting a wrong pair by hand re-confirmed the pair just rejected, and a
  deposit transfer the matcher had mistaken for a payment never reached its
  transfer rule — which happens with exports, whose legs name no counterparty.
- **A transfer is visible and manageable, because it used to be invisible.** A
  row's payload carries `transfer` — `kind` (`pair`/`own`), the account the other
  half sits on, `state` (`proposed` when `confirmed_by_human = 0`, else
  `confirmed`) and the other leg's id — replacing the old `is_transfer` flag: a
  leg with no category and a movement nobody had decided about rendered the same,
  and the `Transfer clearing` account is an implementation detail that never
  leaves the ledger. `?transfer=true|false` narrows `/api/transactions`, and
  `POST /api/transfers/pair|own|unlink` with `GET /api/transfers/labels` is the
  management surface behind the Movimenti sheet. `mark_transfer_pair` enforces
  the matcher's own guards — two real accounts, different ones, equal and
  opposite amounts, no split to lose — and reuses the row of a rejected pair:
  re-linking re-clears both legs, because a rejection left them on
  `Uncategorized` and flipping only the flag would have counted them as spending
  while the ledger claimed a confirmed transfer. `unlink_transfer` rejects rather
  than deletes the row, for the reason above, and `pair_candidates` offers a
  manual pairing nothing but the pairs the matcher would have accepted.
  `mark_own_transfer` is the single-movement version of `own_accounts`: the
  label it takes becomes the virtual account, so the leg leaves the burn and the
  income series at once (the income query already skips any transaction with a
  virtual posting), and unlinking it reports when a configured label will put it
  back at the next sync.
- **A rule is a text the description contains.** `merchant_name` still reduces
  the bank's wording to the merchant for the *proposals* — the classifier and the
  LLM ask by merchant — but the rules match the raw description, so a pattern can
  hold text the normalization drops (`addebito sdd`) and one rule covers a whole
  family of descriptions. `matching_rule` picks the longest matching pattern,
  alphabetically between two of the same length, and returns None when none
  matches: an unmatched movement stays in `Uncategorized` and in the review queue
  rather than being guessed. The `merchants` table was the normalization cache
  *and* the rule store; both jobs are gone — nothing read the cache, and the
  rules are the `rules` table keyed by `rule_key` (trimmed, spaces collapsed,
  lower case). `categorize` never touches a split (several category postings) or
  a transfer leg (none). It runs inside `SyncService.run`, so the scheduled sync
  in the server process categorizes too.
- **A reading is filtered by a `LedgerScope`, and the three filters are not
  equal.** `accounts` narrows everything that belongs to an account: spending by
  the account that paid it (a category posting has no account of its own, so
  `_spending_scope` tests the real side of the same transaction), liquidity, the
  savings flow and the net worth series. `categories` narrows spending alone —
  income is not categorized, and what the accounts are worth is not a category's
  business. The period is deliberately *not* part of the scope: `compute_metrics`
  takes no period, because the 6- and 24-month windows are what those metrics are,
  and the dashboard cards say which window they used. The charts do take a period
  (`from`/`to`, defaulting to the last twelve months), applied in SQL — never
  summed in the browser — and every filtered endpoint echoes what it applied in
  `applied`, so the client cannot show one window while the server read another.
- **Accounts and budgets are managed from the app, not only from the command
  line.** `POST /api/accounts` adds a real account by hand (the broker, or a bank
  that is not connected here) and refuses a name already in the ledger instead of
  quietly reusing it; `PUT /api/accounts/{id}/declaration` records a figure a
  person read off the bank as `manual:available` or `manual:booked`, the same tag
  a hand-typed `--declared` carries; `PUT /api/accounts/{id}/opening` derives the
  opening from a declaration, which is the `anchor` path and now lives in
  `Ledger.anchor_opening` so the CLI and the app share one implementation.
  `DELETE /api/accounts/{id}` is `Ledger.delete_account`: a real account goes with
  its movements, trash, declared balances and the rules narrowed to it, the other
  leg of each pair it took part in is rejected back to the queue, and a connected
  account is also removed from `accounts.json` (matched by name) — otherwise the
  next sync would recreate it and import its history again. Nothing is kept to
  restore; the app asks for the name typed back. The
  Conti section of the PWA is their only writer. Budgets have a section of their
  own, **Budget**, in the bottom bar where Conti used to be (Conti moved to the
  menu): `PUT /api/budgets/{category_id}?month=` is the default from that month,
  `PUT …/override?month=` the month's own ceiling, `POST /api/budgets/{id}/copy`
  the copy from another month, and `POST|PUT|DELETE /api/budget-items` the items.
  Every one of them answers with the whole month, because a default or a moved
  item changes more than the row that was touched.
- **Metrics read spending, not category postings.** `metrics.py` filters to
  transactions whose account posting is negative, exactly like
  `Ledger.spend_between`; without that filter an incoming salary's negative
  category posting nets against a month's spending and the burn turns
  negative. Windows are clipped to the months the ledger actually covers and
  the shortfall is reported through `partial` / `episodic_partial` rather than
  padding past months with zeros.
- **A metric is called in the code what it was called first, and on screen what it
  measures.** `recurring_burn`, `episodic_accrual`, `expected_burn`, `runway_months`,
  `essential_monthly`, `discretionary_monthly` and `savings_flow` stay as they are in
  `metrics.py` and the API; a person reads *Spesa mensile tipica*, *Riserva per spese
  rare*, *Spesa mensile attesa*, *Mesi di autonomia*, *Spesa irrinunciabile*, *Spesa
  tagliabile* and *Investito*, and the category flags read *Spesa rara* and
  *Irrinunciabile*. The dashboard cards, the assistant's packet keys and its prompt,
  and the spec use those words — no "burn" or "runway" anywhere a person reads.
- **Episodic and essential are category flags, not per-transaction ones.** A
  rare event is modelled by putting it in an `episodic` category, which the
  accrual then spreads over 24 months; `essential` marks the part of spending
  that could not be cut. `investment` marks a real account whose inflows are
  savings flow rather than spending.
- **Rebuilding the queue is the server's job.** The review hook removes a row
  optimistically and then refetches `/api/review`; it never adjusts the totals
  itself, because the same `categorize` function is used from the Movements
  screen where the row was not in the queue, and rejecting a transfer restores
  a leg the client cannot predict.
- **Proposals are never applied on their own.** The classifier and the LLM both
  write a `merchant -> category` row into `merchant_suggestions` with a
  `source`, and only `POST /api/suggestions/decision` decides one — always with
  the merchant in the body, because names contain slashes. `accept` assigns the
  chosen category to the movements the queue was holding for that merchant, one
  by one, as the person's own decision, and writes **no rule**: a rule is a
  statement about the movements the bank has not printed yet, so it is written
  only when the request carries `rule` with the text to use, and that text is the
  rule (`merchants.accept_merchant`). The queue's checkbox is off by default and
  its dialog edits that text; the single-movement sheet has the same checkbox.
  Because what a ruleless acceptance writes is a person's decision,
  `_apply_rules` leaves it alone: a later rule that assigns a *different*
  category cannot claim the movement. A rule that assigns the same category does
  adopt it — that is what the rule's `count` means — and deleting that rule puts
  the movement back in the queue, which is the rules machinery working as
  documented. `propose_categories` and `propose_for_unseen` write nothing to
  `transactions`. This is desiderata 5.5 step 4 and section 8: discrete,
  confirmable labels, never numbers, never in the sync path.
- **The LLM feature is off unless configured.** `AMONHEN_LLM_URL` and
  `AMONHEN_LLM_MODEL` must both be set; the API answers 503 with the reason
  otherwise. The endpoint is treated as OpenAI-compatible chat completions and
  the answer is validated against the closed category list before it is stored.
- **No call to the model starts by itself.** `/api/assistant/ask` and
  `/api/llm-suggest` are reached from a click or a submit in the app, and from the
  `llm-suggest` command; there is no effect, timer or background loop that asks in
  someone's place. The entry point from a budget row composes the question and
  shows it with the button that asks it (`AssistantScreen`, the *Domanda pronta*
  panel) instead of asking on mount, and in **Assistente** the button that sent the
  request names the model while it is in flight. A question whose data fingerprint
  matches a stored reading returns that reading and spends no call, and a call that
  fails leaves the composed question in its panel to be tried again.
- **Anomalies are deterministic and explainable.** Robust z-score on MAD per
  category, with a p95 fallback when MAD is zero, and every anomaly carries the
  sentence the UI shows. No model is involved (desiderata 5.7).
- **A budget is a ceiling per category and month, and it has a history.**
  `budgets` holds a default per `(category_id, from_month)`: the default of a
  month is the row with the greatest `from_month` up to it, and a NULL amount
  removes it from then on. `set_default` writes from a month on and deletes the
  later rows — "from this month on" must not let an older change resurface —
  and never touches the months before, which is the whole reason the table has a
  month: one amount for every month rewrote the past each time it changed.
  `budget_months` is one month's own ceiling, which wins over the default. A
  ledger written before months existed is rebuilt by `_date_budgets`, each old
  amount becoming a default from `0000-00`, before every month. The assistant's
  accepted proposal and the `budget` command both write a default from the
  current month. Spending is still per category — settled outflows, like
  `spend_between` — and an item never learns whether it was paid.
- **Items sit inside the ceiling, and the priority orders without cutting.**
  `budget_items` are expenses planned for one category and month (description,
  positive amount, optional date inside the month, `essential` / `important` /
  `deferrable`, note). `budget_status` reads them by priority, then date with
  undated last, then id, and `fitting` marks each one as fitting while the
  running total stays within the ceiling (`None` without a ceiling); `planned`,
  `free` and `over_plan` are computed there too, so the screen never sums. The
  system never proposes what to drop (desiderata section 3). `copy_items` moves the day
  into the target month (clipped to its last day) and skips an item the target
  already holds with the same description and amount, so a second press copies
  nothing. Prefilling from a past movement is the client's: it fills the form,
  and nothing is written until the person saves.
- **Net worth is observed, never reconstructed.** `account_balances` holds what
  a bank reported for an account on a date: `sync` writes the balance Enable
  Banking returns for every reachable account, `balances` does it on demand,
  `anchor` writes the declared one. `net_worth_series` sums the last known
  balance per tracked (`type = 'real'`) account, and an account only counts from
  its first observation, so the curve starts where the data starts — no
  back-fill and no interpolation. The newest row is also what the 5.4 assertion
  in `SyncService.run` compares the ledger against, so one sync records and
  checks in the same pass. The one exception is an account with
  `computed_balance` set: no bank reports it, so `net_worth_series` adds its
  `Ledger.balance` at each observed date (from its `opening_date` on, the dates
  stay the observed ones) and `latest_balances` reports it as of today; a
  declaration on it is left out of the series and stays the 5.4 check. Liquidity
  in `compute_metrics` already used `Ledger.balance` for every real account.
- **The 5.4 assertion is visible, and "no declared balance" is not a pass.**
  The bank declares two figures for the same date and they differ by the pending
  movements, so each declaration is asserted against the computed balance that
  means the same: `available` (everything, matching `ITAV`/`CLAV`) and `booked`
  (settled only, matching `ITBD`/`CLBD`), mapped by `balance_kind` from the
  `eb:<TYPE>` source tag. `Ledger.declared_checks` keeps the newest declaration
  per kind and is the one place both the sync's check and `/api/accounts` →
  `verification` read, so the log and the Conti panel cannot disagree; a failing
  check names its kind, which is what tells a pending-movement difference from
  duplicates and gaps. `account_balances` is keyed by
  `(account_id, date, source)`: it used to be `(account_id, date)`, so the
  second figure of a sync overwrote the first and the two halves could never
  coexist — `_widen_balance_key` rebuilds the table for a ledger written before
  that, keeping the rows. A tie on the date is broken in favour of the bank's
  own number, never by row order. Between two figures a person wrote there is no
  tie to break: a `manual:` or `anchor:` declaration replaces the other hand-written
  one of the same kind and date, or a corrected figure lost to the anchor written
  earlier that day and the re-anchor used the stale one. An account nobody declared a balance for stays
  `unverified`: silence is not agreement, and it is the state FinecoBank sits in
  while its consent is expired. A fourth state sits beside `verified`,
  `mismatch` and `unverified`: `suppressed`, when the difference is exactly what
  a person deleted on that account by hand. `BalanceCheck.suppressed` is the
  signed sum of the account's tombstones up to the declaration date that the
  figure being checked would have counted — both statuses for `available`, only
  `BOOK` for `booked`, never a row with `restored_at`, which is in the ledger
  again — and `explained` is `difference == suppressed` with at least one
  deletion. The sync's own assertion skips the explained checks (it logs them at
  info and reports nothing), because a red nobody can clear teaches people to
  ignore the one line that matters; a difference the tombstones do not explain
  is still reported.
- **The dashboard charts read three aggregations; the client never sums.**
  `spend_by_category` adds up to `spend_between` by construction and keeps
  `Uncategorized` as a slice, so the pie cannot look smaller than the money that
  actually left; `monthly_flows` pairs income (money into a real account, with
  the legs of a linked transfer excluded) with expenses (the same category
  postings the burn uses), clipped to the months the ledger covers with the
  current one flagged `partial`; `net_worth_series` is the balance series above.
  A new chart means a new series in `metrics.py`, not arithmetic in React, and a
  filter means a parameter on that series.
- **The mortgage instalment is gone on purpose.** It used to be a `settings`
  row feeding the runway denominator; it is not a concept any more
  (`compute_metrics` takes no such argument, there is no `/api/settings`
  endpoint, and `initialize` deletes a leftover `mortgage_monthly` key). A
  mortgage payment is a movement like any other, so if it should count it
  belongs in a category. Do not reintroduce a fixed monthly cost that is not a
  movement.
- **`Ledger.category(name)` refuses a name owned by a real or virtual
  account**, and an empty name. Without that, a rule or picker could post to
  something that is not a category and fail halfway through the ledger write.
- **Money moved to an own account that is not connected is not spending.**
  Enable Banking exposes a Revolut deposit account only through a consent that
  covers it, so a leg to it has no counterpart here and the pairing can never
  see it — on the live ledger that single line was the largest part of the burn.
  `passthrough` in `accounts.json` declares the labels the bank prints on those
  transactions and where the money is recorded (`destination`), and
  `link_passthrough_legs` moves each matching leg's category
  side to that virtual account: out of `spend_between`, out
  of the review queue, still on the books (`Ledger.transfer_target` returns that
  name, which the API reports as the leg's `transfer.target`; the same thing can
  be recorded for one movement by hand, see above). It runs after
  `link_transfers` in both the sync and the import, so a real pair between two
  tracked accounts always wins, and it drops any pending proposal for those
  merchants because nothing would ever categorize them. Income excludes any
  transaction with a virtual posting for the same reason.
- **`API_VERSION` in `api.py` and `REQUIRED_API_VERSION` in `web/src/App.tsx`
  move together.** The API serves `web/dist` from disk on every request while the
  Python process keeps running its old code, so a new bundle against an old
  server is a normal state; without the handshake the app rendered nothing at all
  when a payload was missing a key. Bump both whenever a response shape changes:
  the app then says the server is stale instead of crashing. `/api/rules` moved
  from `merchant`/`released` to `pattern`/`held` in 5, and a transaction's
  `is_transfer` became the `transfer` object in 6, and in 7 the dashboard reads
  took `from`/`to`/`accounts`/`categories` and answer with `applied`
  (`/api/spending` lost its `month`, `/api/flows` its `months`, and an account
  row gained `opening_balance`). 18 is the first setup: `/api/setup` and the four
  writes around it, and `/callback` answering a 303 into the app instead of the
  JSON document nobody saw. 19 is the CSV import: `/api/import/csv` and its
  preview, routes an older server does not have. 21 is the budget planned by
  month: a budget row gained `default`, `override`, `planned`, `free`,
  `over_plan` and `items`, and the budget writes answer with the month's list.
  22 is the general rule: a rule row gained `id`, `action`, `target`,
  `account_id`/`account` and `amount_min`/`amount_max`, removal takes an `id`, and
  `/api/rules/preview`, `DELETE /api/accounts/{id}`,
  `POST /api/transactions/delete` and `POST /api/transactions/category` are new.
  23 is the period sync: `POST /api/sync/period`, `GET /api/sync/held` and
  `POST /api/sync/held/{id}/write|discard`, and an account row gained `connected`.
  24 is `version` in `/api/health`. 25 is the account added by hand that a transfer
  rule writes the other half on: an account row gained `computed_balance`, a
  transaction's `transfer` gained `by_rule`, and `/api/transfers/labels` gained
  `accounts`. 26 is the movements behind a proposal: a suggestion's `stake` gained
  `items` (id, date, amount, description, account of each movement a yes decides).
  27 is the opening shown before it is written: `POST /api/accounts/{id}/opening/preview`
  (current, proposed, `change`), and a sync's account row gained `anchored`.
- **The release is on screen.** The foot of the drawer and of the rail says
  `AmonHen <bundle>`, and `· server <version>` beside it when the two differ. The
  image gets the tag as the `AMONHEN_VERSION` build-arg (`image.yml`; the build
  context has no `.git`), which becomes `VITE_APP_VERSION` in the bundle and
  `AMONHEN_VERSION` for the server; `settings.VERSION` falls back to `git describe
  --tags --always --dirty` in a checkout, and a bundle built there says `dev`.
- **A rule is a text the description contains, and writing one rewrites the
  ledger.** `rules.key` is the text as it is matched — `rule_key` trims,
  collapses runs of spaces and lower cases it, so a text typed by a human still
  reaches descriptions that only ever have single ones — and `rules.pattern`
  keeps what was typed, for the list. `RuleBook.set_rule` applies the change
  immediately: `_apply_rules(ledger, before, after)` walks every movement holding
  exactly one category and gives it the category of the rule that decides it
  now, where "the rules' work" is a movement waiting in `Uncategorized` or one
  whose category is a category a rule matching its description assigns it — a
  category no matching rule would assign is a person's decision and stays. That
  ownership test is by *any* matching rule and not by the winner alone, which is
  what keeps the migration honest: a legacy key that a longer text from another
  merchant now shadows still held its movement, so the movement follows the new
  winner instead of sitting on a category no rule claims (with the rule's weight
  reading zero and its removal releasing nothing). That one function is also the
  takeover path (a new, longer pattern moves what a broader rule held) and the
  release path (a removed rule's movements fall to the broader rule that still
  matches, or back to the
  queue). `set_rule` also dismisses every pending proposal the pattern answers,
  which is what keeps the queue from asking about movements the rule has already
  decided. `rule_usage` counts what a rule decides — winner and category agree —
  and the section's count column is what makes a rule that matches nothing
  visible. `POST /api/rules` is an upsert of `{pattern, category}`,
  `POST /api/rules/remove` answers with `{pattern, held}`, and neither takes the
  text in the path: texts contain slashes. A rule cannot point at
  `Uncategorized`: it would take movements out of the queue while categorizing
  nothing.
- **The review queue is settled outflows only, and says what each row survived.**
  Income and `PDNG` rows are not review work, so `/api/review` filters to `BOOK`
  and negative amounts. A row that reaches the backlog has already escaped the
  transfer matcher, because linking a pair moves a leg's posting to the clearing
  account; what is left to test is the classifier. So each row carries
  `review_state`: `proposed` when its merchant has a pending suggestion (a
  decision is already waiting in the block above) and `unhandled` when nothing
  claimed it, which the UI flags in amber as the genuine manual work. `state`,
  `account_id` and `search` narrow the page and never the counts — the chips are
  the real backlog, so a filter cannot make the work look small. Widening the
  queue beyond settled outflows is a product decision, not a bug fix.
- **`serve` can run the sync loop in-process.** One process means one writer for
  the SQLite file; the container uses that instead of a second service sharing
  the volume. The loop opens its own connection per run, so nothing is shared
  across threads.
- **The API has no authentication** because it is served behind Tailscale and
  never exposed publicly. Do not add a public ingress without adding auth.
- **`spend_between` counts outflows only.** Incoming money does not net against
  spending, and refunds are not modelled yet (phase 3).
- **Balance semantics.** `opening_balance` is the balance *before*
  `opening_date`, and `balance()` adds only postings strictly after it.
  `anchor` derives the opening from a declared balance so the section 5.4
  invariant has a baseline; it is idempotent because it uses `movement()`,
  which ignores the opening boundary. `movement(settled=True)` is the same sum
  with the pending movements left out, so an opening derived from the bank's
  *booked* figure does not swallow the pending sum — from the *available* one it
  would be wrong to leave them out. A hand-typed `--declared` has no `eb:` tag
  to say which figure it is, so it carries the word (`manual:booked`) and the
  recorded row is tagged `anchor:<kind>`, both read by the same `balance_kind`.
- **The opening is a fixed point, and re-deriving it hides a difference.** An
  anchor makes the 5.4 check agree by construction: whatever the ledger is
  missing or holds twice goes into the opening. Revolut subtracts a card
  authorization from the available figure without exposing it as pending, so an
  anchor taken from that figure folded two tolls into the opening and counted
  them again when they settled. Hence: `SyncService._anchor_first_opening`
  anchors a connected account once, while `opening_date` is NULL, from the
  bank's own figure — booked over available — and never again; the app's
  *Ricalcola il saldo iniziale* is closed at the foot of the account's panel and
  shows `POST /api/accounts/{id}/opening/preview` (`Ledger.opening_from`, the
  unwritten half of `anchor_opening`) before it writes; a red check shows the gap
  and the latest movements instead of a re-anchor button. Do not put the anchor
  back beside the check.
- **PSD2 returns only ~90 days regardless of the requested range** (verified:
  asking for 2026-01-01 returned rows from 2026-06-14). Deep history exists
  only through `import`, which is why the 6- and 24-month metrics depend on
  backfill, and why import is a prerequisite rather than an extra.
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
- **The ledger is in WAL mode, and a batch is one transaction.** On the NAS's btrfs
  every commit is a flush, and the ledger commits once per movement (`with
  self.conn:` throughout `ledger.py`): the first live sync took five and a half
  minutes for 750 movements, and every page opened meanwhile answered 500 with
  `database is locked`. `db.connect` opens the file with `journal_mode = WAL` and
  `synchronous = NORMAL`, so readers never wait on the writer, and returns a
  `LedgerConnection`, whose `deferred_commits()` makes the inner `with conn:`
  blocks neither commit nor roll back until the outermost one ends.
  `record_batch` runs inside it — the sync, `amonhen import` and the app's CSV
  import all reach it — so a batch commits once and a failure writes none of it.
  The WAL files sit beside the ledger: a restore removes `-wal`/`-shm` with the
  copy, and the snapshot is switched back to the rollback journal so it is one file.
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

- **The assistant is guarded in code, not in its prompt.** Three rules live in
  `assistant.py`: every number in the prose must be one the packet contained
  (checked token by token, Italian separators and dates normalized first) or the
  reading is refused and recorded with no text; a proposal must name a merchant
  and a category that were in the packet, or a category with no budget and a
  positive amount; and nothing identifying leaves the process (IBANs are replaced
  by `[iban]`). The fingerprint that makes a repeated question free covers the
  figures and deliberately not `merchant_senza_categoria`, which changes because
  the assistant itself answered. Without `AMONHEN_LLM_URL` the section says it is
  off, and the day's calls are counted in `settings`.
- **A declared passthrough carries a direction and a destination.** `passthrough`
  in `accounts.json` maps one destination (the virtual account the other side is
  recorded into) to the texts the bank prints, and `incoming_only` makes a label
  match money arriving alone — a firm that reimburses also gets paid, and the
  same name must not take the payment out of the burn. Two alternatives were
  rejected on the live ledger: pairing a credit with the debit it compensates
  (no such pair exists) and a refund category (a category posting on a credit
  leaves it in income).

- **`.env` is loaded at import, and the shell wins.** `settings._load_env_file` reads
  the `KEY=VALUE` lines before any tunable is read, so `uv run amonhen serve` and
  docker compose see the same file — the class of bug where the key is in `.env` and
  the process is not. A variable already in the environment is left alone, and the
  parsing is ours because `python-dotenv` only arrives as a transitive extra of
  `uvicorn[standard]`.
- **The document is never cached; the assets always are.** The API serves `index.html`
  with `Cache-Control: no-cache` and `web/public/sw.js` caches only `/assets/*`, whose
  names come from their content. A cached document points at files a rebuild has
  replaced: the page loads a 404 script and comes up blank, which is also the one way
  an update can look like it never happened. `API_VERSION` catches the other
  direction — a stale bundle against a newer server.
- **A colour is named once, in `web/src/styles.css`.** The `:root` block holds the field's
  three glows, the three fill levels, the palette, the type scale, the radii and the two
  motion curves; a component reads a token. Nothing in the interface draws a line: a panel
  is a lighter fill, a control a lighter fill still, and a state is its own colour on a 15%
  tint of it, which is the ceiling — at 22% the money-out red and the transfer violet drop
  below 4.5 against that tint. Text colours are chosen against the lightest patch the glows
  can produce rather than against the base colour. With no outline the boundary of a control
  is its fill, and a subtle fill cannot reach the 3:1 WCAG 1.4.11 asks of a non-text cue, so
  the label inside the control and the brass focus ring are what carry it. The font is a
  Latin-subset Plus Jakarta Sans variable file in `web/src/assets/` rather than
  `web/public/`: Vite emits it into the hashed `/assets/` directory the service worker
  caches, so an offline start does not wait on the network, and the licence file ships beside
  it. Figures stay tabular — a face whose digits are proportional breaks every column of
  amounts. Two surfaces are painted by the browser rather than by the stylesheet, and
  both need care: a `select`'s drop-down is drawn from the control's own colour, so a
  translucent fill there composites over a light ground and yields a white menu with the
  app's near-white text (hence the opaque `--menu`, which the selects carrying
  `class="input"` need the rule to name explicitly, that class being more specific than a
  bare `select`), and a shadow on a filled control must carry no offset, or it reads as a
  smear detached below the button instead of a halo around it. The arrow and, where the
  engine allows it, the menu itself are the stylesheet's: `appearance: none` with a chevron
  image 16 px in from the right edge, and `::picker(select)` — `appearance: base-select`
  has to be declared on the picker as well, or the control alone styles and the menu stays
  the engine's own, square-cornered and highlighted in the platform's blue.
- **The desktop is a layer, not a second layout.** Everything the wide window gets lives in one
  section at the foot of `web/src/styles.css`, above 1024 px (and one step more above 1440), and
  the cap of the content column is the single token `--shell` — read by `.app__main` and the top
  bar (and, below 1024, the bottom bar) because they frame that column, while above 1024 the frame
  is the rail, whose width is its own token and is paid for by `.app`'s
  `padding-left`. Panels that share a row say so where they are written
  (`panel--pair`), and are not guessed from their contents or their
  neighbours: two charts drawn instead of three, or one of two lists missing, is enough to leave
  a panel half-wide beside an empty half. Below the threshold nothing at all may move, and that is
  verified by comparing every element's box at 390 and 768 against the previous build, not by eye.
- **The three shapes of the section list are one list.** `SECTIONS` in
  `web/src/components/Navigation.tsx` draws the rail (above 1024), the bottom bar (below) and the
  drawer — the item's look is declared once (`.navitem`), and the bar keeps the compact variant
  because a column 70 px wide has room for one short word and a wrap, not for a full name. Above
  1024 the rail's width is a token too (`--rail`), paid for by `.app`'s `padding-left`; the top bar
  and the toast are `fixed`, so they repeat the same measure by hand.
- **Two builds are compared on the same ledger, with no focus lying around.** A comparison at 390
  and 768 is only worth the words if both sides saw the same data — a sync clicked between the two
  captures moved a balance and changed four elements, which looked exactly like a regression. And
  before a pixel comparison, blur the active element: the focus ring a previous interaction left on
  a button is a state of the session, not of the bundle, and cost one round of chasing it.
- **A sheet docks right above 1024, and that is all that changed about it.** `.sheet` is a `<dialog>`
  in the top layer, so `showModal()`, `Esc`, the backdrop and the focus trap are the browser's and
  stay untouched; the desktop block only moves the panel (`align-items: stretch`,
  `justify-content: flex-end`, a `clamp(460px, 40%, 520px)` width, full height, rounded on the left)
  and swaps its entrance for `sheet-in-right`, which is the bottom sheet's 30px travel rotated a
  quarter turn. The drag handle is hidden because it promises a downward close. The page behind is
  locked with `body:has(dialog[open]) { overflow: hidden }` — and that lock stops wheels and
  fingers, **not** `window.scrollTo` or a `scrollTop` assignment, so verify it with a real wheel
  event: scripted scrolling "proves" a lock that is not there. The lock also takes the page's
  scrollbar away, and with it the width the page lays out in: the centred column moved half of
  that and a panel flush with the right edge moved all of it. The same block reserves the gutter
  (`html { scrollbar-gutter: stable }`), so the locked and unlocked states share one width.
- **A grid's columns are not shared with the grid below it.** The movements table's header and its
  rows are two separate grids, so any `auto` column is sized from its own contents: with `auto`, the
  header's "Categoria" (58 px) sat over nothing while the rows' pills reached 293. The columns are
  fixed in `rem` for that reason, and the numbers come from the worst cell measured in a month. The
  same trap is why the row keeps one markup for both shapes: `display: contents` on
  `.txn__body`/`.txn__meta` hands their children to the row's grid above 1024, while below they are
  the phone's lines — and the eight screenshots at 390 and 768 stay byte-identical.
- **A control written once can be placed twice.** In the review queue the category select, its
  confirm button and the new-category form live in one function (`proposalControls`) and render both
  inside the card (below 1024, where the card is the detail) and inside the docked pane (above, where
  the pane is); the stylesheet hides whichever the width does not need, so there is one implementation
  and one set of controls on screen at a time.
- **The app's CSV import is the command line's pipeline, with the mapping chosen on the file.** The
  browser sends the statement as text — JSON, capped at 8 MB, because the repo has no multipart — plus
  the columns a person picked; `amonhen/csv_import.py` turns that mapping into a `CsvProfile`, so a
  bank layout is data rather than a constant, and the rows go through the same `read_csv` →
  `record_batch` → `link_transfers` → `categorize` path as `amonhen import`. Idempotency is the
  content hash, so importing the same file twice writes nothing. One deliberate difference from
  `parse_csv`: a row that does not read is reported with its line (and the parser's own English
  sentence) instead of refusing the whole file.
- **The queue's predicate is one constant.** `ledger.UNCATEGORIZED_WHERE` is settled
  outflows still on `Uncategorized` with no transfer leg; `/api/review` counts its rows
  with it and `merchants.uncovered_spending` measures a proposal's stake with the same
  fragment, so the figure on a proposal cannot contradict the list under it. A proposal
  is per merchant, so a stake is a total, a count and a span — never one amount — and
  the movements under it (`Stake.items`), because a merchant's name alone is not
  something a person can say yes to: the day and the amount are what they recognise.

- **A rule does one of three things, under conditions.** `Rule.action` is
  `category`, `delete` or `transfer`; `account_id`, `amount_min` and `amount_max`
  narrow the text (amounts compare `abs(amount)`), and between two rules of the
  same text the one with more conditions wins (`matching_rule`'s key after the
  length). The same text and conditions are one rule: `set_rule` without an `id`
  updates that row. `apply_rule_changes(before, after)` is the one place rules
  touch movements, in one `deferred_commits` transaction and in the order the
  actions win — deletions (`delete_transaction`, so a tombstone, on every movement
  a deleting rule matches, splits and legs included), then transfers
  (`move_to_virtual_account` on a single-sided, unpaired movement, whatever its
  category; a leg a removed rule had recorded goes back to `Uncategorized`), then
  categories (the old `_apply_rules` semantics, unchanged). `categorize` is that
  same call with `before == after`, which is how a sync deletes a new movement a
  rule matches: it is written, then tombstoned in the same run, and the tombstone
  keeps it out from then on. A movement a deleting rule matches cannot be restored
  (`POST /api/deleted/{id}/restore` answers 409 naming the rule) — it would be back
  in the trash at the next sync. `reimport_deleted` and a deleting rule fight on
  every sync; the rule wins, at the cost of a reimport and a re-deletion each run.
  The `passthrough` declarations in `accounts.json` are untouched: a transfer
  rule is the app's way to say the same thing, and both may coexist.
  `/api/rules/preview` answers what a rule would take before it is written —
  the sheet (`web/src/components/RuleSheet.tsx`) shows it, and the save button of
  a deleting rule says how many it deletes. The same sheet opens from a movement
  (the picker's checkbox, after the category is chosen: the movement takes the
  category only when the rule is saved) and from **Categorie e regole**.
- **Movements are deleted and categorized in batches too.**
  `POST /api/transactions/delete` is `Ledger.delete_transactions`: each id as the
  single delete does it, in one transaction, and an id that is not in the ledger
  refuses the whole batch before anything is written. `POST
  /api/transactions/category` gives the chosen rows one category as a person's
  decision and skips transfer legs and splits, counting them. **Movimenti** has a
  *Seleziona* mode: a tap picks a row, *Seleziona tutti* takes the loaded page.
- **A transfer rule towards an account added by hand writes the other half.** The
  Revolut deposit is reachable only through a consent that does not cover it, so its
  transfers reach the ledger on the personal account alone. When a transfer rule's
  `target` names a real account with no `external_uid`, `_apply_transfers` calls
  `Ledger.mirror_transfer` instead of `move_to_virtual_account`: it inserts the
  opposite movement on that account (same date and description, `mirror_of` = the
  original's id, `content_hash` = `mirror:<id>` so an import can never dedup against
  it, `source` copied from the original) and links the two as a confirmed pair with
  `method = 'rule'`. The pair then behaves like any linked pair — out of spending,
  income and the queue — and the account's balance is its postings. Only `BOOK` rows
  are mirrored (a promotion rewrites a pending row's postings). `_movement_rows`
  leaves the mirror rows out, because they carry the description the rule matches,
  and reports `mirror_account` so a mirrored original stays the rule's to move or
  release; releasing or retargeting deletes the mirror with no tombstone
  (`drop_mirror`). `mirror_of` cascades, so deleting the original takes its mirror,
  and `delete_transaction` refuses a mirror alone (a page holding both deletes the
  original once); `unlink_transfer` refuses a `rule` pair; `delete_account` also
  removes the transfer rules that target the account, or the next sync would
  recreate it as a virtual one. `set_rule` refuses a connected account as target
  (its own half arrives from the bank) and a rule narrowed to the target itself.
  The opening of such an account is anchored from today's figure through the
  mirrors (`anchor_opening` dates it the day before the first one), so its history
  starts at the first transfer; interest the bank credits inside the account is
  invisible, and is corrected with a movement rather than by re-anchoring.
- **A rule's kind is in its pattern, not in a column.** A pattern written between slashes is a regular expression (section 5.5), matched with `re.search(..., re.IGNORECASE)` against the same collapsed, lower-cased description the plain rules compare, compiled once per source through an `lru_cache` because a sync runs the whole book against every description. `Rule.expression` and `rule_pattern()` are the only readers of the slashes, so the store, the API and the CLI carry no new field. The longest pattern wins, counted on what it says (the text, or the expression inside the slashes), so an expression that names a family is longer than the words it replaces while a broader one steals nothing from a narrower text; `set_rule` refuses an expression that does not compile (`ValueError`, which the app's handler turns into a 422), so a rule that could never match is never stored.

## Ledger schema

One SQLite file (`amonhen.db`, overridable with `AMONHEN_DB_PATH`), fifteen tables. The
ledger's shape is the first four, and **a transaction has no category column**: the
category lives on a posting, which is what makes an internal transfer not spending
by construction.

|Table|Columns|Holds|
|---|---|---|
|`accounts`|14|One row per real account, virtual account (transfer clearing, an investment destination) and category — `type` is what separates them. `episodic` / `essential` are the flags the metrics read; `investment` is what makes a transfer into an account savings instead of spending; `reimport_deleted` decides whether the next sync writes back the movements deleted from this account; `computed_balance` makes the net worth read the account from its postings instead of a declaration|
|`transactions`|17|One row per movement: `account_id`, `date`, `amount` (signed text, cents-exact), `description`, `status` (`BOOK` / `PDNG`), `external_id`, `content_hash` (the dedup key), `source` (`psd2` / `import`), `source_file`, `raw_payload` (the bank's payload verbatim), `counterparty`, `counterparty_account`, `currency`, `created_at`, `notes` (local, written by a person, never by an ingest path), `mirror_of` (the movement this row is the other half of, written by a transfer rule towards an account added by hand)|
|`postings`|5|The double-entry legs: `transaction_id`, `account_id`, `amount`, `note`. A spend is one leg on the real account and one on a category account; a transfer is one leg on each real account, or on the virtual clearing account when only one side is in the ledger; a split is several category legs on one transaction|
|`deleted_transactions`|18|A movement a person deleted, copied whole: the identity the ledger dedupes by, the bank's payload, the note, when it went and when it came back. It is what keeps the next sync from writing the movement in again|
|`transfer_links`|5|A pairing, proposed or confirmed: the two legs, `confidence`, `method`, `confirmed_by_human`|
|`rules`|8|`id`; `key` (the text lower-cased, or the expression as typed — case is part of an expression, `\D` is not `\d`); `pattern` (what a person typed: a text, or `/an expression/`); `action` (`category` / `delete` / `transfer`); `target` (the category or the destination, NULL for a deletion); `account_id`, `amount_min`, `amount_max` (the conditions, sizes without sign). One rule per text and conditions: the unique index `rules_identity` is created by `_generalize_rules`, which also rebuilt the old `key, pattern, category` table|
|`account_balances`|4|What a bank declared, one row per `(account, date, source)`: the available and booked figures coexist so the 5.4 assertion can check each|
|`budgets`|4|A category's default ceiling from `from_month` (YYYY-MM) on; a NULL `amount` removes it from that month|
|`budget_months`|4|One month's own ceiling for a category, over the default|
|`budget_items`|9|An expense planned inside a category's ceiling for one month: description, amount, optional date, priority, note|
|`merchant_suggestions`|5|A merchant → category proposal with its `source` and `decision` (`pending` / `accepted` / `dismissed`)|
|`held_transactions`|11|A movement a period sync did not write because it looks like one the other ingest path wrote under a different description: the movement as it arrived, its occurrence, the row it resembles (`twin_id`), and the `decision` (`pending` / `written` / `discarded`). One row per `(account_id, key)`|
|`budget_proposals`|5|The assistant's budget proposals, decided the same way|
|`assistant_readings`|7|A reading, the model that wrote it, the fingerprint of the data it read, and `refused` when a guard rejected it|
|`settings`|2|Key/value odds and ends|

Three shapes wrap the same movement: `IncomingTransaction` (`models.py`, 13 fields)
is what a source reports before the ledger assigns ids, the balancing posting and
the hash — a note is not part of what a source reports, which is why the class
does not carry one; the row above is what is stored; `Transaction`
(`web/src/types.ts`, 15 keys) is what the API returns — `category` is the posting's category (null when
there are several), `merchant` is the normalized name, and `review_state` /
`proposed_category` exist only in the queue.

## Common tasks

|Task|Where to look|
|---|---|
|Change what the product must do|The spec (`desiderata-monitoring-finanziario.md`) first, then the code — section 9 holds the order of work and the status of each phase|
|Change the sync cadence|`AMONHEN_SYNC_INTERVAL_HOURS` or `daemon --interval-hours`|
|Sync one account over a past period, or fill a gap|The account's panel in **Conti**, *Sincronizza un periodo* (preview first) — or `uv run amonhen sync --account <name> --from YYYY-MM-DD --to YYYY-MM-DD [--preview]`. Then decide the held probable duplicates in the same panel. A bank that refuses 30-day ranges gets `max_window_days` in its `accounts.json` entry|
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
|Change a dashboard chart|The series in `metrics.py`, then the panel in `web/src/screens/Dashboard.tsx`; the API returns the sums, the client only draws them|
|Change a colour, a spacing or the type scale|The `:root` tokens in `web/src/styles.css`; the font and its licence are in `web/src/assets/`|
|Regenerate parsing fixtures|`uv run python tools/dump_raw.py` then `uv run python tools/anonymize_dump.py dumps`|
|Connect a new bank|**Configurazione** in the app (the drawer, or the rail above 1024), *Banca* step (`POST /api/setup/connect`, then the login happens at the bank) — or `http://<host>:8000/connect?bank=Revolut&country=IT`, the same route for a script. Then `uv run amonhen sync`, unless the wizard's *Primo sync* step already did it|
|First setup on a fresh install|The app opens on the wizard by itself while `/api/setup` answers `configured: false` — *Credenziali* (application id, PEM key, redirect URL, holder: the URL it shows is what goes into the Enable Banking dashboard), *Banca*, *Conti*, *Primo sync*, *Saldi e verifica*. `PUT /api/setup/credentials` creates `accounts.json` and `private.pem`, so there is nothing to write by hand|
|Add or change a categorization rule|The **Categorie e regole** section of the app — under the category it assigns, or *Nuova regola* for a rule with conditions or one that deletes or records a transfer (the sheet previews what it takes) — or `uv run amonhen rule-add "addebito sdd" "Bollette"` (the text the description contains, or `/an expression/`); `uv run amonhen rule-remove "addebito sdd"` releases its movements|
|Add a category|The same section, *Nuova categoria* (or the picker on a movement, or a proposal's select) — `POST /api/categories`. A category categorizes nothing by itself|
|Run the UI locally|`uv run amonhen serve` and `npm --prefix web run dev` (Vite proxies `/api`)|
|Build the PWA|`npm --prefix web run build` — the API serves `web/dist`|

## What this system deliberately does NOT have

If asked to add any of these, push back first — the desiderata excludes them
on purpose (sections 3 and 8):

- AI in the synchronous sync path, or anywhere it produces numbers
- Natural-language queries over the ledger; hand-written SQL wins
- Generative anomaly detection where a robust statistic exists
- Broker API integration, TWR/IRR, forecasting, budget optimization
- Multi-user, multi-currency, sharing
- Native app (the UI is a PWA)
- Balance-only providers (Binance, Coinbase, eToro)

## Reference for deeper questions

- `desiderata-monitoring-finanziario.md` — the product definition and roadmap.
- `../bridge-bank/` — the original full implementation; useful for Enable
  Banking field semantics and transaction parsing edge cases.
- `../bridge-bank/docs/` — longer explanations of the same concepts.
