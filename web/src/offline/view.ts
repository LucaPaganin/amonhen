// The copy with the operations applied, and the reads the offline screens make of it.
// Pure: the same bundle and queue give the same answers, which is what the tests hold.
import type {
  Account,
  AccountRef,
  ReviewQueue,
  Split,
  Transaction,
  TransactionPage,
  TransferCandidate,
} from "../types";
import type { Bundle, Operation, ProposedPair } from "./types";

export interface View {
  bundle: Bundle;
  /** Every movement the copy holds, with the operations applied; a deleted one is not here. */
  byId: Map<number, Transaction>;
  /** In the review queue: still waiting for a category, by id. */
  queue: number[];
  credits: number[];
  /** Pairs the matcher proposed and nobody has decided. */
  pairs: ProposedPair[];
}

export interface TransactionFilterQuery {
  from?: string;
  to?: string;
  accountId?: number;
  category?: string;
  status?: string;
  search?: string;
  transfer?: boolean;
  tag?: string;
  amountMin?: string;
  amountMax?: string;
  everyday?: boolean;
  limit?: number;
  offset?: number;
}

export interface ReviewFilterQuery {
  state?: "all" | "proposed" | "unhandled";
  accountId?: number | null;
  search?: string;
}

/** A page of the queue is as long as the server's answer is. */
const REVIEW_PAGE = 50;

const cents = (value: string): number => Math.round(Number.parseFloat(value) * 100);
const fromCents = (value: number): string => (value / 100).toFixed(2);
const negated = (value: string): string => fromCents(-cents(value));

/** Newest first, the way the server orders every list. */
export function newestFirst(a: Transaction, b: Transaction): number {
  if (a.date !== b.date) return a.date < b.date ? 1 : -1;
  return b.id - a.id;
}

export function derive(bundle: Bundle, operations: Operation[]): View {
  const view: View = {
    bundle,
    byId: new Map(bundle.transactions.map((item) => [item.id, structuredClone(item)])),
    queue: [...bundle.review.queue],
    credits: [...bundle.review.credits],
    pairs: [...bundle.review.transfers],
  };
  for (const operation of operations) apply(view, operation);
  for (const operation of operations) {
    for (const id of [operation.transaction_id, Number(operation.value.other_id)]) {
      const touched = view.byId.get(id);
      if (touched) touched.pending_offline = true;
    }
  }
  // What waits is what is still without a category and not a leg of anything.
  const waiting = (id: number) => {
    const item = view.byId.get(id);
    return item !== undefined && item.transfer === null && item.category === bundle.uncategorized;
  };
  view.queue = view.queue.filter(waiting);
  view.credits = view.credits.filter(waiting);
  return view;
}

function apply(view: View, op: Operation): void {
  const item = view.byId.get(op.transaction_id);
  switch (op.kind) {
    case "category":
      if (item) setSplits(item, [{ category: String(op.value.category), amount: negated(item.amount) }]);
      return;
    case "splits":
      if (item) setSplits(item, op.value.splits as Split[]);
      return;
    case "note":
      if (item) item.notes = String(op.value.notes ?? "").trim() || null;
      return;
    case "tag_add":
      if (item && !item.tags.includes(String(op.value.tag))) {
        item.tags = [...item.tags, String(op.value.tag)].sort();
      }
      return;
    case "tag_remove":
      if (item) item.tags = item.tags.filter((tag) => tag !== op.value.tag);
      return;
    case "delete":
      if (item) remove(view, item);
      return;
    case "pair":
      pair(view, op.transaction_id, Number(op.value.other_id));
      return;
    case "review":
      review(view, op);
      return;
  }
}

function setSplits(item: Transaction, splits: Split[]): void {
  item.splits = splits.map((split) => ({ ...split }));
  item.category = splits[0]?.category ?? null;
}

/** Back to the review bucket, the way the server leaves a leg whose pair was undone. */
function release(view: View, item: Transaction): void {
  item.transfer = null;
  setSplits(item, [{ category: view.bundle.uncategorized, amount: negated(item.amount) }]);
  const list = cents(item.amount) > 0 ? view.credits : view.queue;
  if (!list.includes(item.id)) list.push(item.id);
}

function remove(view: View, item: Transaction): void {
  view.byId.delete(item.id);
  view.pairs = view.pairs.filter((pair) => pair.leg_a !== item.id && pair.leg_b !== item.id);
  // The other half of a pair is spending again, and the row that said so is gone.
  const other = item.transfer?.kind === "pair" ? view.byId.get(item.transfer.leg_id ?? -1) : undefined;
  if (other) release(view, other);
}

function pair(view: View, legA: number, legB: number): void {
  const first = view.byId.get(legA);
  const second = view.byId.get(legB);
  if (!first || !second) return;
  for (const [leg, other] of [[first, second], [second, first]]) {
    leg.transfer = {
      kind: "pair",
      target: other.account.name,
      state: "confirmed",
      leg_id: other.id,
      by_rule: false,
    };
    leg.splits = [];
    leg.category = null;
  }
  view.pairs = view.pairs.filter(
    (proposed) => ![legA, legB].includes(proposed.leg_a) || ![legA, legB].includes(proposed.leg_b),
  );
}

function review(view: View, op: Operation): void {
  const legA = op.transaction_id;
  const legB = Number(op.value.other_id);
  const involved = (proposed: ProposedPair) =>
    [proposed.leg_a, proposed.leg_b].sort().join() === [legA, legB].sort().join();
  const found = view.pairs.find(involved);
  view.pairs = view.pairs.filter((proposed) => !involved(proposed));
  if (!found) return;
  for (const id of [found.leg_a, found.leg_b]) {
    const item = view.byId.get(id);
    if (!item) continue;
    if (op.value.decision === "reject") release(view, item);
    else if (item.transfer) item.transfer = { ...item.transfer, state: "confirmed" };
  }
}

// -- the reads ------------------------------------------------------------------------------

function withReview(view: View, item: Transaction): Transaction {
  const proposed = item.merchant ? view.bundle.review.pending[item.merchant] : undefined;
  return {
    ...item,
    proposed_category: proposed ?? null,
    review_state: proposed ? "proposed" : "unhandled",
  };
}

function inQueue(view: View, ids: number[]): Transaction[] {
  return ids
    .map((id) => view.byId.get(id))
    .filter((item): item is Transaction => item !== undefined)
    .sort(newestFirst);
}

/** The server's `/api/transactions` over the copy, for the filters Movimenti offers. */
export function readTransactions(view: View, query: TransactionFilterQuery): TransactionPage {
  const { bundle } = view;
  const computed = new Set(
    bundle.accounts.filter((account: Account) => account.computed_balance).map((a) => a.id),
  );
  const needle = query.search?.toLowerCase();
  // The copy ends where the period it was taken for ends: asking beyond it would return
  // less than the ledger holds without saying so.
  const from = query.from && query.from > bundle.from ? query.from : bundle.from;
  const to = query.to && query.to < bundle.to ? query.to : bundle.to;

  const matches = (item: Transaction): boolean => {
    if (item.date < from || item.date > to) return false;
    if (query.accountId !== undefined && item.account.id !== query.accountId) return false;
    if (query.status && item.status !== query.status) return false;
    if (query.category && !item.splits.some((split) => split.category === query.category)) return false;
    if (query.tag && !item.tags.includes(query.tag)) return false;
    if (query.transfer !== undefined && (item.transfer !== null) !== query.transfer) return false;
    if (needle) {
      const text = [item.description, item.counterparty, item.notes].map((part) => (part ?? "").toLowerCase());
      if (!text.some((part) => part.includes(needle))) return false;
    }
    const size = Math.abs(cents(item.amount));
    if (query.amountMin && size < cents(query.amountMin)) return false;
    if (query.amountMax && size > cents(query.amountMax)) return false;
    return true;
  };
  const everyday = (item: Transaction) => !computed.has(item.account.id) && item.transfer === null;

  const all = [...view.byId.values()].filter(matches).sort(newestFirst);
  const shown = query.everyday ? all.filter(everyday) : all;
  const offset = query.offset ?? 0;
  return {
    total: shown.length,
    hidden: all.length - shown.length,
    items: shown.slice(offset, offset + (query.limit ?? 100)),
  };
}

/** The server's `/api/review` over the copy: the filters narrow the list, never the counts. */
export function readReview(view: View, query: ReviewFilterQuery): ReviewQueue {
  const backlog = inQueue(view, view.queue).map((item) => withReview(view, item));
  const proposed = backlog.filter((item) => item.review_state === "proposed");
  const unhandled = backlog.filter((item) => item.review_state === "unhandled");
  let selected = { all: backlog, proposed, unhandled }[query.state ?? "all"];
  if (query.accountId) selected = selected.filter((item) => item.account.id === query.accountId);
  if (query.search) {
    const needle = query.search.toLowerCase();
    selected = selected.filter((item) => item.description.toLowerCase().includes(needle));
  }
  const accounts = new Map<number, AccountRef>();
  for (const item of backlog) accounts.set(item.account.id, item.account);

  const transfers: TransferCandidate[] = [];
  for (const proposal of view.pairs.slice(0, REVIEW_PAGE)) {
    const legA = view.byId.get(proposal.leg_a);
    const legB = view.byId.get(proposal.leg_b);
    if (legA && legB) {
      transfers.push({ confidence: proposal.confidence, method: proposal.method, leg_a: legA, leg_b: legB });
    }
  }
  return {
    uncategorized: selected.slice(0, REVIEW_PAGE),
    uncategorized_total: backlog.length,
    proposed_total: proposed.length,
    unhandled_total: unhandled.length,
    accounts: [...accounts.values()].sort((a, b) => a.name.localeCompare(b.name)),
    transfers,
    transfers_total: view.pairs.length,
    proposals_total: view.bundle.review.proposals_total,
    credits: inQueue(view, view.credits).slice(0, REVIEW_PAGE),
    credits_total: view.credits.length,
  };
}

/** The legs this movement could be paired with, still free in the copy. */
export function readCandidates(view: View, id: number): Transaction[] {
  return (view.bundle.candidates[String(id)] ?? [])
    .map((candidate) => view.byId.get(candidate))
    .filter((item): item is Transaction => item !== undefined && item.transfer === null);
}

/** The copy as it stands after these operations went to the server: what to keep. */
export function settle(bundle: Bundle, applied: Operation[]): Bundle {
  const view = derive(bundle, applied);
  return {
    ...bundle,
    transactions: [...view.byId.values()].sort(newestFirst),
    review: {
      ...bundle.review,
      queue: view.queue,
      credits: view.credits,
      transfers: view.pairs,
    },
  };
}
