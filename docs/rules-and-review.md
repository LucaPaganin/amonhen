# Rules, the review queue, proposals and the model

Part of what `CLAUDE.md` says before changing code. A rule that changes changes here, in the same change as the code.

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
- **A rule's cost is one read of every movement, so that read has to be cheap.**
  `_movement_rows` asks each movement for its balancing legs and its pair, and a
  rule write runs it once per action. Without `postings_transaction` and
  `transfer_links_leg_b` each of its subqueries read the whole table, and saving a
  rule took twelve seconds with 2,600 movements, on the PC and on the NAS alike.
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
- **Anomalies are deterministic and explainable.** Robust z-score on MAD per
  category, with a p95 fallback when MAD is zero, and every anomaly carries the
  sentence the UI shows. No model is involved (desiderata 5.7).
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
  Income and `PDNG` rows are not review work, so its list filters to `BOOK`
  and negative amounts; the credits have a block of their own (below). A row that reaches the backlog has already escaped the
  transfer matcher, because linking a pair moves a leg's posting to the clearing
  account; what is left to test is the classifier. So each row carries
  `review_state`: `proposed` when its merchant has a pending suggestion (a
  decision is already waiting in the block above) and `unhandled` when nothing
  claimed it, which the chip *Senza proposta* filters on. `state`,
  `account_id` and `search` narrow the page and never the counts — the chips are
  the real backlog, so a filter cannot make the work look small. Widening the
  queue beyond settled outflows is a product decision, not a bug fix.
- **A credit is asked about in its own block.** `ledger.CREDITS_WHERE` is settled
  money in on `Uncategorized` from `settings.CREDITS_REVIEW_FROM` on (2026-08-01
  by default, 2025-08-01 on the NAS through `AMONHEN_CREDITS_REVIEW_FROM`),
  no transfer leg, no split; `/api/review` answers it as `credits` and
  `credits_total`, outside the list's filters. The badge counts them with the
  proposals and the transfers: it left them out while they were 94 daily interests, and
  a credit nobody can see from the bar is a credit nobody answers. `CreditCard.tsx` asks the type, and the type
  picks the categories it offers: `income`, `contribution`, or neither for a
  refund. What it writes is an ordinary `set_category`, so nothing new is stored.
  The deposit's daily interest leaves by a category rule towards an `income`
  category, which the rules already apply to credits (`_movement_rows` has no sign)
  and which moves no figure, because a credit in the bucket already counts as
  income in the charts. That rule is data, not code: it is not seeded. A credit
  decided by hand, wrongly too, is found in **Movimenti** by its category; on
  purpose there is no second view for it.
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
- **A rule's kind is in its pattern, not in a column.** A pattern written between slashes is a regular expression (section 5.5), matched with `re.search(..., re.IGNORECASE)` against the same collapsed, lower-cased description the plain rules compare, compiled once per source through an `lru_cache` because a sync runs the whole book against every description. `Rule.expression` and `rule_pattern()` are the only readers of the slashes, so the store, the API and the CLI carry no new field. The longest pattern wins, counted on what it says (the text, or the expression inside the slashes), so an expression that names a family is longer than the words it replaces while a broader one steals nothing from a narrower text; `set_rule` refuses an expression that does not compile (`ValueError`, which the app's handler turns into a 422), so a rule that could never match is never stored.
