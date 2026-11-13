# Transfers

Part of what `CLAUDE.md` says before changing code. A rule that changes changes here, in the same change as the code.

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
  manual pairing nothing but the pairs the matcher would have accepted, except
  for the distance: `settings.MANUAL_PAIR_MAX_GAP_DAYS` (7) instead of
  `TRANSFER_MAX_GAP_DAYS` (2), because a withdrawal from PayPal reaches the bank
  days later. A day costs 10 of the evidence weight down to a floor of 1, so a
  wide gap ranks a candidate last instead of dropping it.
  `mark_own_transfer` is the single-movement version of `own_accounts`: the
  label it takes becomes the virtual account, so the leg leaves the burn and the
  income series at once (the income query already skips any transaction with a
  virtual posting), and unlinking it reports when a configured label will put it
  back at the next sync.
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
  `link_transfers` on every path that writes movements, so a real pair between two
  tracked accounts always wins, and it drops any pending proposal for those
  merchants because nothing would ever categorize them. Income excludes any
  transaction with a virtual posting for the same reason.
- **A declared passthrough carries a direction and a destination.** `passthrough`
  in `accounts.json` maps one destination (the virtual account the other side is
  recorded into) to the texts the bank prints, and `incoming_only` makes a label
  match money arriving alone — a firm that reimburses also gets paid, and the
  same name must not take the payment out of the burn. Two alternatives were
  rejected on the live ledger: pairing a credit with the debit it compensates
  (no such pair exists) and a refund category of its own (a category posting on a credit
  leaves it in income).
- **A transfer rule runs first.** `apply_transfer_rules` follows every account that
  fetched something, and comes before `link_transfers` on every path that writes
  movements: a pass, a period, `settle`, a file import from the app or the command line,
  and a held movement written by hand. The order is written once, in
  `services.ingest.settle_after_ingest` (transfer rules, pairing, passthrough, the
  double-entry check, the rules), and every one of those paths calls it; the import and
  the held movement used to pair first, so on them the matcher could take a transfer a
  rule named (`tests/test_settle_after_ingest.py`). After each account, because the other half used to appear only when the
  slowest bank of the run had finished; before the pairing, because a paired leg is not
  `_decidable`, so an equal amount on another account would have taken a transfer the
  person named with a rule. Category rules still run last: on a leg the matcher pairs,
  the pair wins.
- **A connected wallet that does not report its top-ups takes the other half too.**
  PayPal paid with a Revolut card reports the purchase and never the top-up, so the
  purchase arrived on both accounts as two debits nobody pairs — spending counted
  twice. `accounts.unreported_funding` (*Non riporta le ricariche* in Conti, `PATCH
  /api/accounts/{id}`, `account-flags --unreported-funding`) lets `mirror_target`
  accept that connected account, and `/api/transfers/labels` offers it; everything
  else is the mirror below. On the live ledger the rule is `paypal *` on Revolut
  personale with a minimum of a cent: plain `paypal` also took two PayPal direct
  debits from before PayPal's history starts (2026-09-28) and three zero-amount
  card checks, which would have taken real spending away.
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
