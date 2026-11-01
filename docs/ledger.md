# The ledger: what a movement is, and what the balances mean

Part of what `CLAUDE.md` says before changing code. A rule that changes changes here, in the same change as the code.

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
- **A category is renamed with what names it.** `Ledger.rename_category` (`name` in
  `PATCH /api/categories/{id}`, `category-rename`, the name field in its row) also
  rewrites `rules.target` and the two proposal tables: a posting holds the id, they
  hold the text, and a rule left on the old name would recreate it at the next
  `categorize` and pull its movements back. The review bucket keeps its name.
- **`Ledger.category(name)` refuses a name owned by a real or virtual
  account**, and an empty name. Without that, a rule or picker could post to
  something that is not a category and fail halfway through the ledger write.
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
- **A bank's balance counts only if its type is on the list.** Fineco declares `FWAV`,
  what it expects the account to hold on a coming date, and `balance_kind` used to read
  any unknown type as available: it failed the 5.4 check (a red on an account that was
  fine) and put the future into `net_worth_series` and `latest_balances`. Now
  `ledger.BANK_BALANCE_TYPES` is the list section 5.4 names, and
  `COUNTED_SOURCES_SQL` is the one filter `declarations` and both series read: every
  `manual:`/`anchor:` row, and of the `eb:` rows only those types. The sync still
  records everything. `FORECAST_SOURCES_SQL` rows feed `Ledger.overdraft_forecast`:
  below zero it is `forecast` on the account row, a line in Conti that changes neither
  the balance nor the verification. Any other `eb:` type is
  `Ledger.unrecognized_balances`: a warning at every sync and `unrecognized_balances`
  on the account row, a line in Conti that stays until the type is added to the list,
  which means reading what it is. `balance_kind` raises on such a row rather than
  guess. `bank_balance_source` writes the tag in upper case, so the SQL lists and the
  stored rows cannot disagree on the spelling.
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
- **A broker holds its cash here, and nothing else.** The portfolio is not tracked
  (section 5.8), so Scalable is a real account with its liquidity alone.
  `Ledger.record_valuation` is for a real, `investment`, hand-added account: it writes
  `value − balance(date)` as a `BOOK` movement described "Aggiornamento liquidità",
  `content_hash = valuation:<account>:<date>` (a second one that day deletes and
  replaces it), against the virtual account `Investimenti`, and records the figure as
  `manual:available`. The hash prefix is how it stays out of the way:
  `transfers._candidates`, `pair_candidates` and `merchants._movement_rows` skip
  `valuation:%`; income already skips any transaction with a virtual posting. `source`
  stays `import` because the column has a CHECK. It is written by hand (*Aggiorna la
  liquidità* in Conti, which replaces *Dichiara saldo* on that account). A monthly plan
  that leaves a bank goes straight to `Investimenti` with a transfer rule. The readers
  of Scalable's PDF statements and the market value were both removed: do not bring
  them back without the product deciding otherwise.
