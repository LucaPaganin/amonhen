# CLAUDE.md — AmonHen (repo folder: bank-connector)

## Project

`amonhen` is a personal finance monitoring system that unifies every
connected bank account into one reconciled double-entry ledger, so spending
and runway can be computed instead of guessed. It replaces the old
Enable Banking → Actual Budget connector that used to live in this repo; that
path (actualpy client, rule patches, `state.json`, Flask server, scheduler)
was removed in the phase 1 cutover and is gone from the branch.

The product definition is `desiderata-monitoring-finanziario.md` (Italian):
read the sections a slice touches **before** implementing it, and §9 for the
order of work and the status of each phase. Keep it true in the same change —
a decision that adds, removes or changes a requirement edits the spec alongside
the code, bumps its version line and says what changed. A spec that trails the
code is worse than none, because the next slice implements the old product.

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
`validate`.

## Architecture in one line

`sync`/`import` → normalizers (`providers/`, `adapters/`) → `IncomingTransaction`
→ `Ledger.record` (dedup + pending→booked) → postings in SQLite →
`transfers.link_transfers` → `spend_between` / `balance` / `check_balance`.

## File map

|File|Role|
|---|---|
|`amonhen/settings.py`|Paths and tunables, each overridable via `AMONHEN_<NAME>`; loads `.env` first|
|`amonhen/models.py`|`Account`, `Posting`, `IncomingTransaction`, decimal helpers|
|`amonhen/db.py`|Schema for accounts, transactions, postings, transfer_links, rules, budgets, merchant_suggestions, account_balances, settings, assistant_readings, budget_proposals|
|`amonhen/dedup.py`|`content_hash` fallback identity (whitespace/case normalized)|
|`amonhen/ledger.py`|`Ledger`: accounts, `record`, invariants, spend/balance queries|
|`amonhen/config.py`|Reads `accounts.json`: Enable Banking credentials, accounts, and the `passthrough` declarations|
|`amonhen/sync.py`|`SyncService`: per-account fetch → normalize → ledger, then links transfers|
|`amonhen/transfers.py`|Transfer candidate graph, weights, link review state|
|`amonhen/matching.py`|Exact maximum-weight bipartite matching (Hungarian)|
|`amonhen/merchants.py`|Merchant normalization, the rules on the description and their application|
|`amonhen/metrics.py`|Burn, episodic accrual, runway, savings flow, and the dashboard series|
|`amonhen/anomalies.py`|Deterministic, explained spending outliers|
|`amonhen/classifier.py`|Char n-gram logistic proposals for uncovered merchants|
|`amonhen/llm.py`|The one place a chat-completion request is built, sent and parsed|
|`amonhen/suggestions.py`|Optional LLM proposals for merchants never seen|
|`amonhen/assistant.py`|Desiderata 5.9: a reading of the numbers already computed, and the guards on it|
|`amonhen/api.py`|FastAPI surface (transactions, review, categories, rules, budgets, anomalies, suggestions, assistant, dashboard series) and PWA host|
|`amonhen/providers/enable_banking.py`|EB HTTP client (JWT, windows, pagination, 429 backoff, balances)|
|`amonhen/providers/eb_normalize.py`|Raw EB payload → `Account` / `IncomingTransaction` (pure)|
|`amonhen/adapters/csv_adapter.py`|CSV import with a `CsvProfile` per bank layout|
|`amonhen/adapters/ofx_adapter.py`|OFX 1.x SGML and 2.x XML import|
|`amonhen/cli.py`|Argument parsing and the command implementations|
|`web/`|React PWA source (recharts for the dashboard charts); the five sections are declared once in `web/src/components/Navigation.tsx`; built to `web/dist`, served by the API|
|`tools/dump_raw.py`|Dumps raw EB payloads to disk, for regenerating fixtures|
|`tools/anonymize_dump.py`|Turns raw dumps into committed fixtures|
|`tests/fixtures/enable_banking/`|Anonymized real payloads used by provider tests|
|`tests/fixtures/imports/`|Synthetic CSV/OFX fixtures|

## Module map

|Module|Public surface|
|---|---|
|`settings`|`ROOT`, `DB_PATH`, `CONFIG_FILE`, `EB_API`, `SYNC_INTERVAL_HOURS`, `UNCATEGORIZED`|
|`models`|`Account`, `Posting`, `IncomingTransaction`, `parse_decimal`, `format_decimal`|
|`db`|`connect`, `initialize`, `open_ledger_db`|
|`ledger`|`Ledger`, `BalanceCheck`, `PENDING_WINDOW_DAYS`, `TRANSFER_CLEARING`|
|`dedup`|`content_hash`, `normalize_description`|
|`config`|`MonitorConfig`, `ConfiguredAccount`, `load_config`|
|`sync`|`SyncService`, `SyncResult`, `AccountSyncResult`|
|`transfers`|`link_transfers`, `link_own_account_transfers`, `pair_candidates`, `transfer_amount_total`|
|`matching`|`max_weight_matching`|
|`merchants`|`merchant_name`, `rule_key`, `matching_rule`, `Rule`, `RuleBook`, `categorize`, `rule_usage`|
|`metrics`|`compute_metrics`, `Metrics`, `LedgerScope`, `spend_by_category`, `monthly_flows`, `net_worth_series`, `latest_balances`|
|`anomalies`|`detect_anomalies`, `Anomaly`|
|`classifier`|`CharNgramClassifier`, `propose_categories`, `apply_proposals`|
|`suggestions`|`LlmConfig`, `llm_config`, `unseen_merchants`, `propose_for_unseen`|
|`api`|`create_app`|
|`providers`|`EnableBankingClient`, `ConsentExpiredError`, `normalize_transaction`, `normalize_account`, `iban_of`|
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
  the money counts as spending again.
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
  `Ledger.anchor_opening` so the CLI and the app share one implementation. The
  Conti section of the PWA is their only writer; budgets stay
  `PUT /api/budgets/{category_id}`.
- **Metrics read spending, not category postings.** `metrics.py` filters to
  transactions whose account posting is negative, exactly like
  `Ledger.spend_between`; without that filter an incoming salary's negative
  category posting nets against a month's spending and the burn turns
  negative. Windows are clipped to the months the ledger actually covers and
  the shortfall is reported through `partial` / `episodic_partial` rather than
  padding past months with zeros.
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
  `source`, and only `POST /api/suggestions/decision` with `{"merchant": …,
  "decision": "accept"}` turns it into a rule whose pattern is that merchant
  name (the merchant travels in the body, because names contain slashes).
  `propose_categories` and
  `propose_for_unseen` write nothing to `transactions`. This is desiderata 5.5
  step 4 and section 8: discrete, confirmable labels, never numbers, never in
  the sync path.
- **The LLM feature is off unless configured.** `AMONHEN_LLM_URL` and
  `AMONHEN_LLM_MODEL` must both be set; the API answers 503 with the reason
  otherwise. The endpoint is treated as OpenAI-compatible chat completions and
  the answer is validated against the closed category list before it is stored.
- **Anomalies are deterministic and explainable.** Robust z-score on MAD per
  category, with a p95 fallback when MAD is zero, and every anomaly carries the
  sentence the UI shows. No model is involved (desiderata 5.7).
- **Budgets are monthly and per category.** One amount per category, applied to
  every month; `budget_status` reports the current month's spend against it,
  counting outflows only, like `spend_between`.
- **Net worth is observed, never reconstructed.** `account_balances` holds what
  a bank reported for an account on a date: `sync` writes the balance Enable
  Banking returns for every reachable account, `balances` does it on demand,
  `anchor` writes the declared one. `net_worth_series` sums the last known
  balance per tracked (`type = 'real'`) account, and an account only counts from
  its first observation, so the curve starts where the data starts — no
  back-fill and no interpolation. The newest row is also what the 5.4 assertion
  in `SyncService.run` compares the ledger against, so one sync records and
  checks in the same pass.
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
  own number, never by row order. An account nobody declared a balance for stays
  `unverified`: silence is not agreement, and it is the state FinecoBank sits in
  while its consent is expired.
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
  `own_accounts` in `accounts.json` declares the labels the bank prints on those
  transfers, and `link_own_account_transfers` moves each matching leg's category
  side to a virtual account named after the label: out of `spend_between`, out
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
  row gained `opening_balance`).
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
- **PSD2 returns only ~90 days regardless of the requested range** (verified:
  asking for 2026-01-01 returned rows from 2026-06-14). Deep history exists
  only through `import`, which is why the 6- and 24-month metrics depend on
  backfill, and why import is a prerequisite rather than an extra.
- **A consent can be dead even when the session looks authorized.** The Fineco
  session metadata still said `AUTHORIZED` while `/transactions` returned
  401/403, and its session listing still answered with four uids. Sync reports
  the error and continues with the other accounts, and the import path stays the
  recovery when the bank cannot be reached at all. Renewing means the browser
  flow again (`/connect?bank=FinecoBank&country=IT`), and it only completes when
  three URLs agree: the address the browser reaches, `redirect_url` in
  `accounts.json`, and the callback registered in the Enable Banking dashboard.
  The live file still points at `<tailnet>:3000/callback`, the port of the Flask
  app this one replaced, where nothing listens — which is why a renewal cannot
  finish today. Tailscale serves it as
  `https://<node>.<tailnet>.ts.net/callback` (`tailscale serve --bg
  localhost:8000`).
- **`accounts.json` is read at startup per command** and still carries the
  Enable Banking credentials and account list. The `actual` section is gone.
  The `/connect` and `/callback` endpoints write into it (so the container mounts
  it writable), and every other reader only reads it. `save_account` keys on the
  account **uid**: a session id changes at every authorization while the uid does
  not, so a renewed consent *refreshes* the entry in place — keeping `notes`,
  which is the name the ledger knows the account by, and `start_sync_date`, which
  is the history it already imported — and only an account never seen before is
  added. Keying on the (session, uid) pair appended a second entry for the same
  account, which the ledger, matching by name, then merged into one account and
  re-imported the history under.
- **Fixtures are anonymized real payloads.** Never commit raw dumps under
  `dumps/` (gitignored) or add real names, IBANs or amounts to
  `tests/fixtures/`. Regenerate with `tools/anonymize_dump.py`.

## Working on this checkout

- **The ledger worth testing against is a copy, and it is not in the repo.** The
  real ledger lives outside version control: `dumps/` and `mytest*` are
  gitignored. Copy it before a destructive experiment, point the command at the
  copy with the global `--db` (`uv run amonhen --db dumps/verify.db serve …`),
  delete the copy when done. `amonhen.db` in the repo root is an **empty shell**,
  so a command that finds nothing is usually pointed at it. Never commit raw
  dumps, or real names, IBANs and amounts — `tools/anonymize_dump.py` turns a
  dump into a fixture and needs `dumps/.anonymize-salt`, which is deliberately
  outside the repo.
- **The API serves `web/dist` from disk on every request, the Python process
  keeps its old code.** A rebuilt bundle therefore needs no restart, a Python
  change does: `npm --prefix web run build`, then restart. The handshake
  (`API_VERSION` / `REQUIRED_API_VERSION`) is what makes the app say the server
  is stale instead of rendering nothing.
- **The Docker image cannot be built on this machine.** The Docker CLI and
  compose are installed but the Linux engine is not running, so `docker build`
  has never been exercised here: the recipe in README ("On the NAS") is verified
  only down to the commands the image runs (`uv sync --frozen --no-dev
  --no-install-project` and `npm run build`, both of which do run locally). Keep
  the `uv` image tag at the version that wrote `uv.lock`: the lock is revision 3
  and older uv binaries refuse to read it.
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
- **The queue's predicate is one constant.** `ledger.UNCATEGORIZED_WHERE` is settled
  outflows still on `Uncategorized` with no transfer leg; `/api/review` counts its rows
  with it and `merchants.uncovered_spending` measures a proposal's stake with the same
  fragment, so the figure on a proposal cannot contradict the list under it. A proposal
  is per merchant, so a stake is a total, a count and a span — never one amount.

## Common tasks

|Task|Where to look|
|---|---|
|Change what the product must do|The spec (`desiderata-monitoring-finanziario.md`) first, then the code — §9 holds the order of work and the status of each phase|
|Change the sync cadence|`AMONHEN_SYNC_INTERVAL_HOURS` or `daemon --interval-hours`|
|Add a bank's CSV layout|Add a `CsvProfile` in `adapters/csv_adapter.py` plus a synthetic fixture|
|Reset an account|Delete its rows / the database file, then `sync` and `import` again|
|Re-derive the opening balance|`uv run amonhen balances` then `uv run amonhen anchor`|
|Check duplicates or gaps|`uv run amonhen validate`, `uv run amonhen balance-check`|
|Inspect the ledger|`sqlite3 amonhen.db` — accounts, transactions, postings, transfer_links|
|See the balances behind the net worth|`sqlite3 amonhen.db "select * from account_balances"` — written by `sync`, `balances` and `anchor`|
|Change a dashboard chart|The series in `metrics.py`, then the panel in `web/src/screens/Dashboard.tsx`; the API returns the sums, the client only draws them|
|Regenerate parsing fixtures|`uv run python tools/dump_raw.py` then `uv run python tools/anonymize_dump.py dumps`|
|Connect a new bank|Open `http://<host>:8000/connect?bank=Revolut&country=IT`, complete the bank login, then `uv run amonhen sync`|
|Add or change a categorization rule|The **Regole** section of the app, or `uv run amonhen rule-add "addebito sdd" "Bollette"` (the text the description contains); `uv run amonhen rule-remove "addebito sdd"` releases its movements|
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
