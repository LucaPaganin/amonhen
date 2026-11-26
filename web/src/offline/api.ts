// What `api` answers when there is no network: the same methods, over the copy on the
// phone. A method that is not here needs the server, and `api` says so.
import { ApiError } from "../apiError";
import type { DashboardFilters, Split, Transaction } from "../types";
import { record, current } from "./session";
import type { DashboardSnapshot, Operation } from "./types";
import { derive, readCandidates, readReview, readTransactions, type View } from "./view";

let cache: { bundle: unknown; queue: Operation[]; view: View } | null = null;

function view(): View {
  const { bundle, queue } = current();
  if (!bundle) throw new ApiError(0, "nessuna copia scaricata: serve la rete");
  if (!cache || cache.bundle !== bundle || cache.queue !== queue) {
    cache = { bundle, queue, view: derive(bundle, queue) };
  }
  return cache.view;
}

/** The movement as the server held it when the copy was taken: where a base comes from. */
function original(id: number): Transaction {
  const found = current().bundle?.transactions.find((item) => item.id === id);
  if (!found) throw new ApiError(404, "movimento non presente nella copia");
  return found;
}

function present(id: number): Transaction {
  const found = view().byId.get(id);
  if (!found) throw new ApiError(404, "movimento non presente nella copia");
  return found;
}

function notALeg(item: Transaction): void {
  if (item.transfer) throw new ApiError(422, "è un giroconto: la categoria non si cambia");
}

const heldSplits = (item: Transaction) => ({
  splits: item.splits.map(({ category, amount }) => ({ category, amount })),
});

/** The dashboard's answer for the period asked: the span in whole months decides which. */
function snapshotFor(filters: DashboardFilters): DashboardSnapshot {
  const snapshots = current().snapshots;
  if (!snapshots) throw new ApiError(0, "cruscotto non scaricato: serve la rete");
  if (filters.accounts.length || filters.categories.length || filters.tags.length) {
    throw new ApiError(0, "con questi filtri il cruscotto non è stato scaricato: serve la rete");
  }
  const [fromYear, fromMonth] = filters.from.split("-").map(Number);
  const [toYear, toMonth] = filters.to.split("-").map(Number);
  const months = toYear * 12 + toMonth - (fromYear * 12 + fromMonth) + 1;
  const found = snapshots.periods.find((period) => period.months === months);
  if (!found) throw new ApiError(0, "periodo non scaricato: serve la rete");
  return found;
}

const unique = <T>(values: T[]): T[] => [...new Set(values)];

export const offlineApi = {
  // The bundle knows the review bucket's name; the version check is the server's alone.
  health: async () => ({ status: "offline", uncategorized: view().bundle.uncategorized }),
  accounts: async () => view().bundle.accounts,
  categories: async () => view().bundle.categories,
  tags: async () => view().bundle.tags,
  transferLabels: async () => view().bundle.transfer_labels,
  transactions: async (query: Parameters<typeof readTransactions>[1] & { virtualAccountId?: number }) => {
    if (query.virtualAccountId !== undefined) throw new ApiError(0, "serve la rete");
    return readTransactions(view(), query);
  },
  transaction: async (id: number) => present(id),
  review: async (query: Parameters<typeof readReview>[1] = {}) => readReview(view(), query),
  transferCandidates: async (id: number) => readCandidates(view(), id),

  month: async (filters: DashboardFilters) => snapshotFor(filters).month,
  metrics: async (filters: DashboardFilters) => snapshotFor(filters).metrics,
  spending: async (filters: DashboardFilters) => snapshotFor(filters).spending,
  flows: async (filters: DashboardFilters) => snapshotFor(filters).flows,
  netWorth: async (filters: DashboardFilters) => snapshotFor(filters).netWorth,
  anomalies: async () => {
    const snapshots = current().snapshots;
    if (!snapshots) throw new ApiError(0, "cruscotto non scaricato: serve la rete");
    return snapshots.anomalies;
  },

  setCategory: async (id: number, category: string) => {
    notALeg(present(id));
    if (!view().bundle.categories.some((item) => item.name === category)) {
      throw new ApiError(422, "categoria nuova: serve la rete per crearla");
    }
    await record("category", id, { category }, heldSplits(original(id)));
    return present(id);
  },
  setSplits: async (id: number, splits: Split[]) => {
    notALeg(present(id));
    const known = new Set(view().bundle.categories.map((item) => item.name));
    if (splits.some((split) => !known.has(split.category))) {
      throw new ApiError(422, "categoria nuova: serve la rete per crearla");
    }
    await record("splits", id, { splits }, heldSplits(original(id)));
    return present(id);
  },
  setNotes: async (id: number, notes: string) => {
    present(id);
    await record("note", id, { notes }, { notes: original(id).notes ?? "" });
    return present(id);
  },
  setTags: async (id: number, tags: string[]) => {
    const item = present(id);
    const known = new Set(view().bundle.tags.map((tag) => tag.name));
    const wanted = unique(tags.map((tag) => tag.trim()).filter(Boolean));
    if (wanted.some((tag) => !known.has(tag))) throw new ApiError(422, "tag nuovo: serve la rete per crearlo");
    for (const tag of wanted.filter((name) => !item.tags.includes(name))) await record("tag_add", id, { tag }, {});
    for (const tag of item.tags.filter((name) => !wanted.includes(name))) await record("tag_remove", id, { tag }, {});
    return present(id);
  },
  tagTransactions: async (ids: number[], tag: string) => {
    if (!view().bundle.tags.some((item) => item.name === tag)) {
      throw new ApiError(422, "tag nuovo: serve la rete per crearlo");
    }
    let tagged = 0;
    for (const id of ids) {
      if (present(id).tags.includes(tag)) continue;
      await record("tag_add", id, { tag }, {});
      tagged += 1;
    }
    return { tagged };
  },
  categorizeTransactions: async (ids: number[], category: string) => {
    if (!view().bundle.categories.some((item) => item.name === category)) {
      throw new ApiError(422, "categoria nuova: serve la rete per crearla");
    }
    let categorized = 0;
    let skipped = 0;
    for (const id of ids) {
      const item = present(id);
      if (item.transfer) {
        skipped += 1;
        continue;
      }
      await record("category", id, { category }, heldSplits(original(id)));
      categorized += 1;
    }
    return { categorized, skipped };
  },
  deleteTransaction: async (id: number) => {
    const item = present(id);
    const held = original(id);
    const unlinked = item.transfer?.kind === "pair";
    await record(
      "delete",
      id,
      {},
      { date: held.date, amount: held.amount, description: held.description, status: held.status },
    );
    return { id, unlinked_pair: unlinked };
  },
  deleteTransactions: async (ids: number[]) => {
    let deleted = 0;
    let unlinkedPairs = 0;
    for (const id of ids) {
      const result = await offlineApi.deleteTransaction(id);
      deleted += 1;
      if (result.unlinked_pair) unlinkedPairs += 1;
    }
    return { deleted, unlinked_pairs: unlinkedPairs };
  },
  pairTransfer: async (legA: number, legB: number) => {
    present(legA);
    present(legB);
    await record("pair", legA, { other_id: legB }, {});
    return present(legA);
  },
  reviewTransfer: async (legA: number, legB: number, decision: "confirm" | "reject") => {
    await record("review", legA, { other_id: legB, decision }, { state: 0 });
    return { ok: true };
  },
};
