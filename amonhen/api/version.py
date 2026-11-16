"""The API version the PWA checks before it reads a payload.

`REQUIRED_API_VERSION` in `web/src/App.tsx` moves with it: bump both whenever a
response shape changes. What each version changed is in the comment below."""
from __future__ import annotations

# Before 20, and the three the paragraph below skips: `/api/rules` moved from
# `merchant`/`released` to `pattern`/`held` in 5; a transaction's `is_transfer`
# became the `transfer` object in 6; in 7 the dashboard reads took
# `from`/`to`/`accounts`/`categories` and answer with `applied` (`/api/spending`
# lost its `month`, `/api/flows` its `months`, an account row gained
# `opening_balance`). 18 is the first setup: `/api/setup` and the four writes
# around it, `/callback` answering a 303 into the app. 19 is the CSV import:
# `/api/import/csv` and its preview. 28 is the virtual accounts:
# `GET /api/virtual-accounts` and `virtual_account_id` on `/api/transactions`. 29 is
# the broker's value: `POST /api/accounts/{id}/valuation` and
# `POST /api/import/scalable[/preview]`; 30 took the Scalable routes away again.
# Bump when a response shape changes: the PWA compares this with the version it
# was built for and, when the server is older, says so instead of crashing on a
# key that is not there. The bundle is read from disk on every request while the
# Python process keeps running its old code, so the two can drift. Version 20 is
# the queue's decision: the request carries the text of a rule to write and the
# answer says what the decision did, and an older server would take the text as
# absent — writing a rule named after the merchant, which is the behaviour this
# version removed. 21 is the budget planned by month (desiderata 5.12): a budget
# row carries its default, its month override and its items, and every budget
# write answers with the whole month instead of one row. 22 is the general rule
# (desiderata 5.5): a rule has an id, an action, a target and conditions, and the
# writes around it are new, with the account deletion and the movements' batch
# writes beside them. 23 is the sync of one account over a chosen period:
# `/api/sync/period` and the probable duplicates it holds (`/api/sync/held`),
# and an account row says whether it is `connected`. 24 is the release in
# `/api/health` (`version`), which the app shows beside the bundle's own. 25 is
# the account added by hand that a transfer rule writes the other half on: an
# account row carries `computed_balance`, a transaction's `transfer` says
# `by_rule`, and `/api/transfers/labels` lists those `accounts`. 26 is the
# movements behind a proposal: a suggestion's `stake` carries its `items`. 27 is
# the opening shown before it is written: `/api/accounts/{id}/opening/preview`,
# and a sync's account says the opening it `anchored` from the bank's figure. 31
# is the essential on screen: `/api/month`, the tags (`/api/tags`, a transaction's
# `tags`, a `tag` rule, `tag` and `everyday` on `/api/transactions`, `tags` on the
# dashboard reads) and `savings_flow` gone from the metrics. 32 is the refund: a
# category gained `income`, and what `/api/month` and the budgets read as spent can
# now be negative. 33 is the contribution: a category gained `contribution` and
# `description`, `/api/month` `contributions` and `net`, the metrics
# `contributions_monthly`. 34 is the bank's forecast: an account row gained
# `forecast`, and a forecast left the verification. 35 is the credits waiting for a
# decision: `/api/review` gained `credits` and `credits_total`. 36 is the bank's
# unknown balance types: an account row gained `unrecognized_balances`. 37 is the
# bank's rate limit: an account row gained `sync_limit`, and a sync's account
# `rate_limited` and `last_read`. 38 took the assistant's routes away and added
# `/api/statistics`; a budget row gained `usual`. 39 is the size of a movement:
# `amount_min` and `amount_max` on `/api/transactions`, which an older server would
# ignore and answer with the whole list as if it were the filtered one. 40 is the
# wallet that does not report its top-ups: an account row gained
# `unreported_funding`, which a transfer rule towards a connected account needs.
# 41 is the budget month whole: `/api/budgets` and every budget write answer with
# `categories`, `unassigned` items and a `total` instead of a list, a row gained
# `source` and `usual_mean`, and an item may come without `category_id`.
# 42 is the month at a glance: `/api/month` gained `summary`, this month, the month
# before up to the same day and the month before whole, each with `spent`,
# `contributions`, `net`, `income` and `balance`.
# 43 is the plan (desiderata 5.16): `/api/plan`, its goals, profile and tax years,
# and `/api/plan/compare`.
API_VERSION = 43
