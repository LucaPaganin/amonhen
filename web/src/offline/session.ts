// What the phone holds and whether it is using it. A module-level store, because the `api`
// the screens call has to know it outside React; `useOfflineState` is how a screen reads it.
import { useSyncExternalStore } from "react";
import type { onlineApi } from "../api";
import { discard, enqueue, newOperationId } from "./queue";
import { read, remove, requestPersistence, write } from "./store";
import type { Bundle, DashboardSnapshot, Operation, OperationKind, Snapshots } from "./types";
import { OPERATION_FORMAT } from "./types";

export interface OfflineState {
  /** The storage has been read: before this, nothing here says anything. */
  loaded: boolean;
  bundle: Bundle | null;
  queue: Operation[];
  snapshots: Snapshots | null;
  /** A person chose to work on the copy even with a network. */
  forced: boolean;
  online: boolean;
  /** The browser promised to keep the copy; null until it was asked. */
  persisted: boolean | null;
}

/** The periods the dashboard's quick chips offer, in months. */
export const SNAPSHOT_MONTHS = [1, 3, 6, 12, 24];

const FORCED_KEY = "amonhen:offline-forced";

let state: OfflineState = {
  loaded: false,
  bundle: null,
  queue: [],
  snapshots: null,
  forced: readForced(),
  online: typeof navigator === "undefined" ? true : navigator.onLine,
  persisted: null,
};
const listeners = new Set<() => void>();

function readForced(): boolean {
  try {
    return localStorage.getItem(FORCED_KEY) === "1";
  } catch {
    return false;
  }
}

function set(next: Partial<OfflineState>): void {
  state = { ...state, ...next };
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useOfflineState(): OfflineState {
  return useSyncExternalStore(subscribe, () => state);
}

export function current(): OfflineState {
  return state;
}

export function isOffline(): boolean {
  return state.forced || !state.online;
}

const ready: Promise<void> =
  typeof indexedDB === "undefined"
    ? Promise.resolve()
    : (async () => {
        try {
          const [bundle, queue, snapshots] = await Promise.all([
            read<Bundle>("bundle"),
            read<Operation[]>("queue"),
            read<Snapshots>("snapshots"),
          ]);
          set({ loaded: true, bundle: bundle ?? null, queue: queue ?? [], snapshots: snapshots ?? null });
        } catch {
          // A storage that cannot be read is a phone with no copy; the app works online.
          set({ loaded: true });
        }
      })();

export const whenReady = (): Promise<void> => ready;

if (typeof window !== "undefined") {
  window.addEventListener("online", () => set({ online: true }));
  window.addEventListener("offline", () => set({ online: false }));
}

export function setForced(forced: boolean): void {
  try {
    if (forced) localStorage.setItem(FORCED_KEY, "1");
    else localStorage.removeItem(FORCED_KEY);
  } catch {
    // The choice then lasts until the page closes.
  }
  set({ forced });
}

async function saveQueue(queue: Operation[]): Promise<void> {
  set({ queue });
  await write("queue", queue);
}

/** Record something done on the copy, with the value the copy held when it was done. */
export async function record(
  kind: OperationKind,
  transactionId: number,
  value: Record<string, unknown>,
  base: Record<string, unknown>,
): Promise<void> {
  const operation: Operation = {
    id: newOperationId(),
    kind,
    transaction_id: transactionId,
    value,
    base,
    at: new Date().toISOString(),
  };
  await saveQueue(enqueue(state.queue, operation));
}

export async function discardOperations(ids: string[]): Promise<void> {
  await saveQueue(discard(state.queue, ids));
}

/** What a send leaves: the copy as the server now has it, minus what was settled. */
export async function afterSend(bundle: Bundle, queue: Operation[]): Promise<void> {
  set({ bundle, queue });
  await Promise.all([write("bundle", bundle), write("queue", queue)]);
}

/** Forget the copy. Refused while changes wait: they cannot be downloaded again. */
export async function clearCopy(): Promise<void> {
  if (state.queue.length > 0) throw new Error("ci sono modifiche da inviare: invale o scartale prima");
  await Promise.all([remove("bundle"), remove("snapshots"), remove("queue")]);
  set({ bundle: null, snapshots: null, queue: [] });
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`errore ${response.status}`);
  return (await response.json()) as T;
}

/**
 * Download the copy for a period, and the dashboard as it stands for each of the
 * periods it offers. Nothing is replaced until everything has arrived, so a signal that
 * drops half-way leaves the previous copy whole.
 */
export async function download(
  from: string,
  to: string,
  source: Pick<typeof onlineApi, "month" | "metrics" | "spending" | "flows" | "netWorth" | "anomalies">,
  periodOf: (months: number) => { from: string; to: string },
): Promise<void> {
  if (state.queue.length > 0 && state.bundle) {
    // A new copy takes the old one's place: the queued operations keep their bases, so
    // they are compared with the server at the send, not with this download.
  }
  const bundle = await fetchJson<Bundle>(`/offline/bundle?from=${from}&to=${to}`);
  if (bundle.format !== OPERATION_FORMAT) throw new Error("il server parla un formato offline diverso: aggiorna l'app");
  const periods: DashboardSnapshot[] = [];
  for (const months of SNAPSHOT_MONTHS) {
    const filters = { ...periodOf(months), accounts: [], categories: [], tags: [] };
    const [month, metrics, spending, flows, netWorth] = await Promise.all([
      source.month(filters),
      source.metrics(filters),
      source.spending(filters),
      source.flows(filters),
      source.netWorth(filters),
    ]);
    periods.push({ months, month, metrics, spending, flows, netWorth });
  }
  const snapshots: Snapshots = {
    taken_at: bundle.created_at,
    periods,
    anomalies: await source.anomalies(31),
  };
  await Promise.all([write("bundle", bundle), write("snapshots", snapshots)]);
  set({ bundle, snapshots, persisted: await requestPersistence() });
}
