# Metrics, the dashboard and the budgets

Part of what `CLAUDE.md` says before changing code. A rule that changes changes here, in the same change as the code.

- **A reading is filtered by a `LedgerScope`, and its filters are not
  equal.** `accounts` narrows everything that belongs to an account: spending by
  the account that paid it (a category posting has no account of its own, so
  `_spending_scope` tests the real side of the same transaction), liquidity and
  the net worth series. `categories` and `tags` narrow spending alone —
  income is not categorized, and what the accounts are worth is not a category's
  business. The period is deliberately *not* part of the scope: `compute_metrics`
  takes no period, because the 6- and 24-month windows are what those metrics are,
  and the dashboard cards say which window they used. The charts do take a period
  (`from`/`to`, defaulting to the last twelve months), applied in SQL — never
  summed in the browser. They are days, not months: `monthly_flows` cuts its first
  and last month to them and marks a cut month `partial`, or the bars would show a
  different period from the donut beside them. Every filtered endpoint echoes what it applied in
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
  own, **Budget**: `PUT /api/budgets/{category_id}?month=` is the default from that month,
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
  `essential_monthly` and `discretionary_monthly` stay as they are in
  `metrics.py` and the API; a person reads *Spesa mensile tipica*, *Riserva per spese
  rare*, *Spesa mensile attesa*, *Mesi di autonomia*, *Spesa irrinunciabile* and *Spesa
  tagliabile*, and the flags read *Spesa rara* and *Irrinunciabile*. The dashboard cards
  and the spec use those words — no "burn" or "runway" anywhere a person reads.
- **Rare and essential are one question, asked of a movement.** A movement is rare
  when its category is `episodic` or one of its tags is; `essential` the same way.
  `ledger.RARE_SQL` and `ledger.ESSENTIAL_SQL` are the only definition, and every
  reading uses them, so a tag is not a second concept of rare: on screen the two share
  one control (`LabelRow` in `CategoryRules.tsx`). It holds for the whole movement,
  rare wins over essential, and rare leaves the typical spending, the month's reading
  and the anomalies for the reserve, which is always a 24th. A tag a person wrote is
  kept by the tombstone like a note (`deleted_transactions.tags`, `_written_tags`);
  `by_rule` is what lets removing a rule take back only what the rule wrote. A `tag`
  rule is the one action that adds instead of competing: every matching one applies,
  splits and transfer legs included (`merchants._apply_tags`). `investment` marks
  the broker: a real account added by hand whose balance is declared.
- **A budget is a ceiling per category and month, and it has a history.**
  `budgets` holds a default per `(category_id, from_month)`: the default of a
  month is the row with the greatest `from_month` up to it, and a NULL amount
  removes it from then on. `set_default` writes from a month on and deletes the
  later rows — "from this month on" must not let an older change resurface —
  and never touches the months before, which is the whole reason the table has a
  month: one amount for every month rewrote the past each time it changed.
  `budget_months` is one month's own ceiling, which wins over the default. A
  ledger written before months existed is rebuilt by `_date_budgets`, each old
  amount becoming a default from `0000-00`, before every month. The `budget`
  command writes a default from the current month. Spending is still per category — `SPENDING_SQL`, like
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
- **An item can wait for its category, and items without a ceiling are the
  budget.** `budget_items.category_id` is nullable (`db._unassigned_budget_items`
  rebuilt the table). An item written without one gets what `propose_category`
  finds — the category rules with no account and no size condition, matched on
  the description alone — or stays in the month's `unassigned`, outside every
  total but its own. `budget_status` takes the override, else the default, else
  the sum of the items, and says which in `source` (`override` / `default` /
  `items`); with `items` everything fits by construction, and a ceiling a person
  writes is never moved by the items.
- **A month answers whole, and its total has its own usual.** `budget_month` is
  what `/api/budgets` and every budget write return: `categories`, `unassigned`,
  `window` and `total`. `metrics.usual_reading` keeps each category's months
  (zeros included) so `total.budgeted_usual` reads the budgeted categories as one
  series — medians do not add — beside `total.usual`, the whole spending. A row's
  `usual` is the median and `usual_mean` the mean; `?months=` picks 3 to 24
  complete months (the screen offers 3, 6 and 12, 6 by default). The screen's two
  views, the median/mean choice and the hidden empty categories are per-viewer
  preferences in `localStorage`.
- **The statistics read as the budgets do.** `spending_statistics` (`/api/statistics`,
  desiderata section 5.15) takes the last complete months and `_category_months` counts them
  net of refunds, gross of contributions, rare spending inside: the figures exist to be
  read beside a ceiling. A month with no spending is a zero, the total has its own series, and
  `usual_spending` is the same reading as a median of the six months before the one on
  screen, which is the `usual` of a budget row. The period chips are windows of complete
  months and not dates: a statistic of half a month would be a different number.
- **The dashboard answers two questions, and the client never sums.** `month_reading`
  (`/api/month`) is what was spent so far this month against the same day of the
  complete months before (their median, up to six, cut at each month's last day),
  rare spending on a line of its own, and each category that spent something this
  month with its own usual, the largest first (the row says the distance in words). Below it Liquidità and Mesi di autonomia, three anomalies at most,
  on a PC two charts (`useWide`: a phone does not even fetch them), and the other
  metrics behind *Dettagli*. `spend_by_category` still answers `/api/spending`, with
  no reader in the app since the pie went. `monthly_flows` pairs income (money into a real account, with
  the legs of a linked transfer excluded) with expenses (the same category
  postings the burn uses), clipped to the months the ledger covers with the
  current one flagged `partial`; `net_worth_series` is the balance series above.
  A new chart means a new series in `metrics.py`, not arithmetic in React, and a
  filter means a parameter on that series.
- **A contribution takes the total down, and no category.** Money in towards every
  expense — what the joint account receives — sits on a category flagged `contribution`
  (`ledger.CONTRIBUTION_SQL`). A refund takes down its category; a contribution covers
  everything the account it reached pays. It is inside `SPENDING_SQL`, so
  the charts' expenses are net of it, and `metrics._monthly_net` takes it off essential,
  cuttable and rare by one share, per account and month: received over everything the
  account spent, capped at all of it, the other accounts untouched. So `recurring_burn`,
  `episodic_accrual`, `expected_burn` and the runway are net of it. The share has to be
  one: reducing the rare spending by a share computed on the rest alone counts the same
  euro twice (on a month of 635 normal, 506 rare and 550 received, 988 of relief). What
  an account received beyond what it spent covers nothing, because the others stay
  whole. `month_reading` keeps `spent` and `usual` gross, so the comparison does not depend on the day somebody pays in (`contributions`
  and `net` are its own line). It leaves `spend_by_category` and the budgets too. The
  flag stands alone: `set_category_flag`
  clears the others when it turns on and clears it when one of them does, and it refuses
  the review bucket, where every waiting outflow would read as money received. The
  medians of the kinds and of the total do not add up, and were not meant to.
