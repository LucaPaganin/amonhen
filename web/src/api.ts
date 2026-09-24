import type {
  Account,
  Anomaly,
  AssistantContext,
  AssistantHistoryEntry,
  AssistantReading,
  AssistantState,
  Budget,
  Category,
  DashboardFilters,
  Declaration,
  Flows,
  Health,
  Metrics,
  NetWorth,
  NewAccount,
  ReviewQueue,
  ReviewState,
  Rule,
  Spending,
  Suggestion,
  DeletedMovement,
  Deletion,
  SuggestionDecision,
  SyncOutcome,
  Transaction,
  TransactionPage,
  TransferDecision,
  TransferLabels,
  TransferUnlink,
} from "./types";
import { monthBounds } from "./format";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) return "connessione non disponibile";
  if (error instanceof Error) return error.message;
  return "errore sconosciuto";
}

async function toResult<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T;

  let detail = `errore ${response.status}`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail !== "") detail = body.detail;
  } catch {
    // Non-JSON error body: keep the status-derived message.
  }
  throw new ApiError(response.status, detail);
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return toResult<T>(await fetch(`/api${path}`, { signal, headers: { Accept: "application/json" } }));
}

async function send<T>(method: string, path: string, body: unknown): Promise<T> {
  return toResult<T>(
    await fetch(`/api${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export interface TransactionQuery {
  from?: string;
  to?: string;
  accountId?: number;
  category?: string;
  status?: string;
  search?: string;
  /** true: only transfer legs. false: everything else. */
  transfer?: boolean;
  limit?: number;
  offset?: number;
}

function transactionSearch(query: TransactionQuery): string {
  const params = new URLSearchParams();
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);
  if (query.accountId !== undefined) params.set("account_id", String(query.accountId));
  if (query.category) params.set("category", query.category);
  if (query.status) params.set("status", query.status);
  if (query.search) params.set("search", query.search);
  if (query.transfer !== undefined) params.set("transfer", String(query.transfer));
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  return params.toString();
}

export interface SplitInput {
  category: string;
  amount: string;
}

export interface ReviewQuery {
  state?: ReviewState | "all";
  accountId?: number | null;
  search?: string;
}

function reviewSearch(query: ReviewQuery): string {
  const params = new URLSearchParams({ limit: "50" });
  if (query.state && query.state !== "all") params.set("state", query.state);
  if (query.accountId) params.set("account_id", String(query.accountId));
  if (query.search) params.set("search", query.search);
  return params.toString();
}

async function drop<T>(path: string): Promise<T> {
  return toResult<T>(
    await fetch(`/api${path}`, { method: "DELETE", headers: { Accept: "application/json" } }),
  );
}

/** The dashboard reads: a period in months, and the names to narrow it to. */
function filterSearch(filters: DashboardFilters): string {
  const start = monthBounds(filters.from);
  const end = monthBounds(filters.to);
  const params = new URLSearchParams({ from: start.from, to: end.to });
  if (filters.accounts.length > 0) params.set("accounts", filters.accounts.join(","));
  if (filters.categories.length > 0) params.set("categories", filters.categories.join(","));
  return params.toString();
}

export const api = {
  health: (signal?: AbortSignal) => get<Health>("/health", signal),
  // Synchronous on purpose: the button asked for this run, and the answer is
  // what the run wrote. A second one while it is going answers 409.
  sync: () => send<SyncOutcome>("POST", "/sync", {}),
  accounts: (signal?: AbortSignal) => get<Account[]>("/accounts", signal),
  categories: (signal?: AbortSignal) => get<Category[]>("/categories", signal),
  transactions: (query: TransactionQuery, signal?: AbortSignal) =>
    get<TransactionPage>(`/transactions?${transactionSearch(query)}`, signal),
  transaction: (id: number, signal?: AbortSignal) => get<Transaction>(`/transactions/${id}`, signal),
  review: (query: ReviewQuery = {}, signal?: AbortSignal) =>
    get<ReviewQueue>(`/review?${reviewSearch(query)}`, signal),
  metrics: (filters: DashboardFilters, signal?: AbortSignal) =>
    get<Metrics>(`/metrics?${filterSearch(filters)}`, signal),
  spending: (filters: DashboardFilters, signal?: AbortSignal) =>
    get<Spending>(`/spending?${filterSearch(filters)}`, signal),
  flows: (filters: DashboardFilters, signal?: AbortSignal) =>
    get<Flows>(`/flows?${filterSearch(filters)}`, signal),
  // Net worth is what the accounts are worth: categories have nothing to say.
  netWorth: (filters: DashboardFilters, signal?: AbortSignal) =>
    get<NetWorth>(`/networth?${filterSearch({ ...filters, categories: [] })}`, signal),
  setCategory: (transactionId: number, category: string) =>
    send<Transaction>("POST", `/transactions/${transactionId}/category`, { category }),
  setSplits: (transactionId: number, splits: SplitInput[]) =>
    send<Transaction>("PUT", `/transactions/${transactionId}/splits`, { splits }),
  // A note is the one field of a movement the app writes: everything else is
  // the bank's own statement.
  setNotes: (transactionId: number, notes: string) =>
    send<Transaction>("PUT", `/transactions/${transactionId}/notes`, { notes }),
  deleteTransaction: (transactionId: number) =>
    drop<Deletion>(`/transactions/${transactionId}`),
  // The movements a person deleted and has not brought back, for the trash in
  // the Conti section; the restore answer is the movement itself.
  deleted: (signal?: AbortSignal) => get<DeletedMovement[]>("/deleted", signal),
  restoreDeleted: (deletedId: number) =>
    send<Transaction>("POST", `/deleted/${deletedId}/restore`, {}),
  setCategoryFlags: (categoryId: number, flags: { episodic?: boolean; essential?: boolean }) =>
    send<Category>("PATCH", `/categories/${categoryId}`, flags),
  // The account's own flags: whether its inflows are savings, and whether the
  // movements deleted from it may come back at the next sync.
  setAccountFlags: (
    accountId: number,
    flags: { investment?: boolean; reimport_deleted?: boolean },
  ) => send<Account>("PATCH", `/accounts/${accountId}`, flags),
  createAccount: (body: NewAccount) => send<Account>("POST", "/accounts", body),
  declareBalance: (accountId: number, body: Declaration) =>
    send<Account>("PUT", `/accounts/${accountId}/declaration`, body),
  setOpening: (accountId: number, body: Declaration) =>
    send<Account>("PUT", `/accounts/${accountId}/opening`, body),
  reviewTransfer: (legA: number, legB: number, decision: TransferDecision) =>
    send<{ ok: boolean }>("POST", `/transfers/${legA}/${legB}/review`, { decision }),
  transferLabels: (signal?: AbortSignal) => get<TransferLabels>("/transfers/labels", signal),
  transferCandidates: (id: number, signal?: AbortSignal) =>
    get<Transaction[]>(`/transfers/${id}/candidates`, signal),
  pairTransfer: (legA: number, legB: number) =>
    send<Transaction>("POST", "/transfers/pair", { leg_a: legA, leg_b: legB }),
  markPassthrough: (transactionId: number, destination: string) =>
    send<Transaction>("POST", "/transfers/passthrough", {
      transaction_id: transactionId,
      destination,
    }),
  unlinkTransfer: (transactionId: number) =>
    send<TransferUnlink>("POST", "/transfers/unlink", { transaction_id: transactionId }),
  rules: (signal?: AbortSignal) => get<Rule[]>("/rules", signal),
  assistant: (signal?: AbortSignal) => get<AssistantState>("/assistant", signal),
  assistantHistory: (signal?: AbortSignal) =>
    get<AssistantHistoryEntry[]>("/assistant/readings", signal),
  askAssistant: (question: string, context: AssistantContext | null) =>
    send<AssistantReading>("POST", "/assistant/ask", { question, context }),
  decideBudgetProposal: (category: string, decision: "accept" | "dismiss") =>
    send<{ category: string; decision: string }>("POST", "/assistant/budgets/decision", {
      category,
      decision,
    }),
  createRule: (pattern: string, category: string) => send<Rule>("POST", "/rules", { pattern, category }),
  removeRule: (pattern: string) =>
    send<{ pattern: string; held: number }>("POST", "/rules/remove", { pattern }),
  createCategory: (name: string) => send<{ id: number; name: string }>("POST", "/categories", { name }),
  categorize: () => send<{ applied: number }>("POST", "/categorize", {}),
  budgets: (month?: string, signal?: AbortSignal) =>
    get<Budget[]>(month ? `/budgets?month=${encodeURIComponent(month)}` : "/budgets", signal),
  setBudget: (categoryId: number, amount: string | null, month?: string) =>
    send<Budget>(
      "PUT",
      month ? `/budgets/${categoryId}?month=${encodeURIComponent(month)}` : `/budgets/${categoryId}`,
      { amount },
    ),
  anomalies: (days = 31, signal?: AbortSignal) => get<Anomaly[]>(`/anomalies?days=${days}`, signal),
  suggestions: (signal?: AbortSignal) => get<Suggestion[]>("/suggestions", signal),
  decideSuggestion: (merchant: string, decision: SuggestionDecision, category?: string) =>
    // The merchant travels in the body: names routinely contain a slash. The
    // category travels with it because a person may correct the proposal.
    send<{ merchant: string; decision: SuggestionDecision }>("POST", "/suggestions/decision", {
      merchant,
      decision,
      category: category ?? null,
    }),
  propose: () => send<{ considered: number; recorded: number }>("POST", "/propose", {}),
  llmSuggest: () => send<{ recorded: number }>("POST", "/llm-suggest", {}),
};
