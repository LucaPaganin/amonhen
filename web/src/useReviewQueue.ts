import { useCallback, useEffect, useState } from "react";

import { api, errorMessage, isAbortError } from "./api";
import type {
  AccountRef,
  ReviewState,
  Transaction,
  TransferCandidate,
  TransferDecision,
} from "./types";

interface ReviewQueueState {
  uncategorized: Transaction[];
  uncategorizedTotal: number;
  proposedTotal: number;
  unhandledTotal: number;
  accounts: AccountRef[];
  transfers: TransferCandidate[];
  transfersTotal: number;
  proposalsTotal: number;
}

export interface ReviewQueueController {
  uncategorized: Transaction[];
  uncategorizedTotal: number;
  proposedTotal: number;
  unhandledTotal: number;
  accounts: AccountRef[];
  transfers: TransferCandidate[];
  transfersTotal: number;
  proposalsTotal: number;
  filters: ReviewFilters;
  setFilters: (next: Partial<ReviewFilters>) => void;
  loading: boolean;
  loadError: string | null;
  notice: string | null;
  reload: () => void;
  categorize: (
    transaction: Transaction,
    category: string,
    options?: { rule?: boolean },
  ) => Promise<boolean>;
  decideTransfer: (candidate: TransferCandidate, decision: TransferDecision) => Promise<boolean>;
  notify: (message: string) => void;
  dismissNotice: () => void;
}

const EMPTY_QUEUE: ReviewQueueState = {
  uncategorized: [],
  uncategorizedTotal: 0,
  proposedTotal: 0,
  unhandledTotal: 0,
  accounts: [],
  transfers: [],
  transfersTotal: 0,
  proposalsTotal: 0,
};

function byDateDescending(a: Transaction, b: Transaction): number {
  if (a.date !== b.date) return a.date < b.date ? 1 : -1;
  return b.id - a.id;
}

/** What the queue is showing: the counts beside the filter always stay whole. */
export interface ReviewFilters {
  state: ReviewState | "all";
  accountId: number | null;
  search: string;
}

const ALL_FILTERS: ReviewFilters = { state: "all", accountId: null, search: "" };

export function useReviewQueue(): ReviewQueueController {
  const [queue, setQueue] = useState<ReviewQueueState>(EMPTY_QUEUE);
  const [filters, setFiltersState] = useState<ReviewFilters>(ALL_FILTERS);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const data = await api.review(filters, signal);
      setQueue({
        uncategorized: data.uncategorized,
        uncategorizedTotal: data.uncategorized_total,
        proposedTotal: data.proposed_total,
        unhandledTotal: data.unhandled_total,
        accounts: data.accounts,
        transfers: data.transfers,
        transfersTotal: data.transfers_total,
        proposalsTotal: data.proposals_total,
      });
      setLoadError(null);
      setLoading(false);
    } catch (error) {
      if (isAbortError(error)) return;
      setLoadError(errorMessage(error));
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const setFilters = useCallback((next: Partial<ReviewFilters>) => {
    setFiltersState((current) => ({ ...current, ...next }));
  }, []);

  const reload = useCallback(() => load(), [load]);

  // Optimistic: the row leaves the list immediately; a failed save puts it back.
  // The totals come from the server afterwards, because this function is also
  // used by the Movements screen, where the row was never in the queue.
  const categorize = useCallback(
    async (
      transaction: Transaction,
      category: string,
      options: { rule?: boolean } = {},
    ): Promise<boolean> => {
      setQueue((current) => ({
        ...current,
        uncategorized: current.uncategorized.filter((item) => item.id !== transaction.id),
      }));

      try {
        await api.setCategory(transaction.id, category);
        void load();
      } catch (error) {
        setQueue((current) => ({
          ...current,
          uncategorized: [...current.uncategorized, transaction].sort(byDateDescending),
        }));
        setNotice(`Categoria non salvata: ${errorMessage(error)}`);
        return false;
      }

      if (options.rule && transaction.merchant) {
        try {
          await api.createRule(transaction.merchant, category);
          setNotice(`Regola salvata: ${transaction.merchant} → ${category}`);
        } catch (error) {
          setNotice(`Categoria salvata, ma la regola non è stata creata: ${errorMessage(error)}`);
        }
      }
      return true;
    },
    [load],
  );

  // Optimistic: the candidate disappears immediately; a failed decision puts it back.
  const decideTransfer = useCallback(
    async (candidate: TransferCandidate, decision: TransferDecision): Promise<boolean> => {
      const isCandidate = (item: TransferCandidate) =>
        item.leg_a.id === candidate.leg_a.id && item.leg_b.id === candidate.leg_b.id;

      setQueue((current) => ({
        ...current,
        transfers: current.transfers.filter((item) => !isCandidate(item)),
      }));

      try {
        await api.reviewTransfer(candidate.leg_a.id, candidate.leg_b.id, decision);
        // Rejecting restores the Uncategorized category on both legs, so the
        // queue and its totals change on the server: ask it, do not guess.
        void load();
        return true;
      } catch (error) {
        setQueue((current) => ({
          ...current,
          transfers: [candidate, ...current.transfers],
        }));
        setNotice(`Decisione non salvata: ${errorMessage(error)}`);
        return false;
      }
    },
    [load],
  );

  const notify = useCallback((message: string) => setNotice(message), []);
  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    uncategorized: queue.uncategorized,
    uncategorizedTotal: queue.uncategorizedTotal,
    proposedTotal: queue.proposedTotal,
    unhandledTotal: queue.unhandledTotal,
    accounts: queue.accounts,
    transfers: queue.transfers,
    transfersTotal: queue.transfersTotal,
    proposalsTotal: queue.proposalsTotal,
    filters,
    setFilters,
    loading,
    loadError,
    notice,
    reload,
    categorize,
    decideTransfer,
    notify,
    dismissNotice,
  };
}
