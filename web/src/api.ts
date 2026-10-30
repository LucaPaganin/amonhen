import type {
  Account,
  AccountFlags,
  Anomaly,
  AssistantContext,
  AssistantHistoryEntry,
  AssistantReading,
  AssistantState,
  Budget,
  BudgetItemDraft,
  Category,
  CsvImportOutcome,
  CsvPreview,
  DashboardFilters,
  Declaration,
  Flows,
  Health,
  Metrics,
  NetWorth,
  NewAccount,
  OpeningPreview,
  ReviewQueue,
  ReviewState,
  Rule,
  RuleDraft,
  RulePreview,
  BatchDeletion,
  BatchCategory,
  AccountDeletion,
  SetupBanks,
  SetupCredentials,
  SetupState,
  Spending,
  Suggestion,
  DeletedMovement,
  Deletion,
  SuggestionDecision,
  SuggestionDecisionOutcome,
  SyncOutcome,
  PeriodSyncOutcome,
  HeldMovement,
  RecordAction,
  Transaction,
  TransactionPage,
  TransferDecision,
  TransferLabels,
  TransferUnlink,
  VirtualAccount,
  ScalableImportRequest,
  ScalableReading,
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
  /** Only the movements posted to this virtual account. */
  virtualAccountId?: number;
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
  if (query.virtualAccountId !== undefined) params.set("virtual_account_id", String(query.virtualAccountId));
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  return params.toString();
}

export interface SplitInput {
  category: string;
  amount: string;
}

/** The column map the import screen built: one field per choice it offered.
 *
 * An empty column means "not chosen": a statement carries either one signed
 * amount column or a debit and a credit pair, and the half left blank is what
 * the preview reports back as a problem.
 */
export interface CsvMapping {
  delimiter: string;
  skip_rows: number;
  date_column: string;
  date_format: string;
  amount_column: string;
  debit_column: string;
  credit_column: string;
  decimal_separator: string;
  description_columns: string[];
  external_id_column: string;
  invert_sign: boolean;
}

/** A statement pasted as text, the account it belongs to, and its map. */
export interface CsvImportRequest {
  filename: string;
  content: string;
  account: string;
  mapping: CsvMapping;
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
  // One connected account over a chosen period; `preview` writes nothing.
  syncPeriod: (accountId: number, from: string, to: string, preview: boolean) =>
    send<PeriodSyncOutcome>("POST", "/sync/period", { account_id: accountId, from, to, preview }),
  // The probable duplicates a period sync held, and the decision on each one.
  held: (signal?: AbortSignal) => get<HeldMovement[]>("/sync/held", signal),
  decideHeld: (heldId: number, decision: "write" | "discard") =>
    send<{ transaction_id: number | null; action: RecordAction | null; held: HeldMovement[] }>(
      "POST",
      `/sync/held/${heldId}/${decision}`,
      {},
    ),
  accounts: (signal?: AbortSignal) => get<Account[]>("/accounts", signal),
  virtualAccounts: (signal?: AbortSignal) => get<VirtualAccount[]>("/virtual-accounts", signal),
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
  // The account's own flags: whether its inflows are savings, whether the
  // movements deleted from it may come back at the next sync, and whether its
  // balance is read from its movements.
  setAccountFlags: (accountId: number, flags: AccountFlags) =>
    send<Account>("PATCH", `/accounts/${accountId}`, flags),
  createAccount: (body: NewAccount) => send<Account>("POST", "/accounts", body),
  declareBalance: (accountId: number, body: Declaration) =>
    send<Account>("PUT", `/accounts/${accountId}/declaration`, body),
  previewOpening: (accountId: number, body: Declaration) =>
    send<OpeningPreview>("POST", `/accounts/${accountId}/opening/preview`, body),
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
  // Writing a rule applies it at once — a deleting one empties what it matches —
  // so the editor asks for the preview first.
  createRule: (draft: RuleDraft) => send<Rule>("POST", "/rules", draft),
  previewRule: (draft: RuleDraft) => send<RulePreview>("POST", "/rules/preview", draft),
  removeRule: (id: number) =>
    send<{ id: number; pattern: string; held: number }>("POST", "/rules/remove", { id }),
  deleteTransactions: (ids: number[]) => send<BatchDeletion>("POST", "/transactions/delete", { ids }),
  categorizeTransactions: (ids: number[], category: string) =>
    send<BatchCategory>("POST", "/transactions/category", { ids, category }),
  deleteAccount: (id: number) => drop<AccountDeletion>(`/accounts/${id}`),
  createCategory: (name: string) => send<{ id: number; name: string }>("POST", "/categories", { name }),
  csvPreview: (body: CsvImportRequest) => send<CsvPreview>("POST", "/import/csv/preview", body),
  csvImport: (body: CsvImportRequest) => send<CsvImportOutcome>("POST", "/import/csv", body),
  scalablePreview: (body: ScalableImportRequest) =>
    send<ScalableReading>("POST", "/import/scalable/preview", body),
  scalableImport: (body: ScalableImportRequest) => send<ScalableReading>("POST", "/import/scalable", body),
  recordValuation: (id: number, body: { date: string; value: string }) =>
    send<{ difference: string; account: Account }>("POST", `/accounts/${id}/valuation`, body),
  categorize: () => send<{ applied: number }>("POST", "/categorize", {}),
  // Every budget write answers with the whole month it was made for: a default
  // changed from a month, or an item moved to another category, changes more
  // than the row that was touched.
  budgets: (month: string, signal?: AbortSignal) =>
    get<Budget[]>(`/budgets?month=${encodeURIComponent(month)}`, signal),
  /** The default from `month` on; the months before keep theirs. */
  setBudget: (categoryId: number, amount: string | null, month: string) =>
    send<Budget[]>("PUT", `/budgets/${categoryId}?month=${encodeURIComponent(month)}`, { amount }),
  /** This month only; null hands the month back to the default. */
  setBudgetOverride: (categoryId: number, amount: string | null, month: string) =>
    send<Budget[]>("PUT", `/budgets/${categoryId}/override?month=${encodeURIComponent(month)}`, {
      amount,
    }),
  copyBudgetItems: (categoryId: number, fromMonth: string, toMonth: string) =>
    send<{ copied: number; budgets: Budget[] }>("POST", `/budgets/${categoryId}/copy`, {
      from_month: fromMonth,
      to_month: toMonth,
    }),
  createBudgetItem: (draft: BudgetItemDraft) => send<Budget[]>("POST", "/budget-items", draft),
  /** Answers for `month`, the one on screen, even when the item moved out of it. */
  updateBudgetItem: (id: number, draft: BudgetItemDraft, month: string) =>
    send<Budget[]>("PUT", `/budget-items/${id}?month=${encodeURIComponent(month)}`, draft),
  deleteBudgetItem: (id: number) => drop<Budget[]>(`/budget-items/${id}`),
  anomalies: (days = 31, signal?: AbortSignal) => get<Anomaly[]>(`/anomalies?days=${days}`, signal),
  suggestions: (signal?: AbortSignal) => get<Suggestion[]>("/suggestions", signal),
  decideSuggestion: (
    merchant: string,
    decision: SuggestionDecision,
    options: { category?: string; rule?: string } = {},
  ) =>
    // The merchant travels in the body: names routinely contain a slash. The
    // category travels with it because a person may correct the proposal, and
    // the rule only when its text was written for it: without one the ledger
    // decides the movements and leaves `rules` alone.
    send<SuggestionDecisionOutcome>("POST", "/suggestions/decision", {
      merchant,
      decision,
      category: options.category ?? null,
      rule: options.rule ?? null,
    }),
  propose: () => send<{ considered: number; recorded: number }>("POST", "/propose", {}),
  llmSuggest: () => send<{ recorded: number }>("POST", "/llm-suggest", {}),
  // The first setup. Every write answers with the whole setup payload, so the
  // screen that asked for it never re-reads what it has just changed.
  setup: (signal?: AbortSignal) => get<SetupState>("/setup", signal),
  saveCredentials: (body: SetupCredentials) =>
    send<SetupState>("PUT", "/setup/credentials", body),
  setupBanks: (country: string, signal?: AbortSignal) =>
    get<SetupBanks>(`/setup/banks?country=${encodeURIComponent(country)}`, signal),
  // The authorization happens at the bank: this answers with where to send the
  // browser, which the caller navigates to.
  setupConnect: (bank: string, country: string) =>
    send<{ url: string }>("POST", "/setup/connect", { bank, country }),
  // An empty start date clears the one on the file, and the sync falls back to
  // its own default backfill from then on.
  renameConfiguredAccount: (accountUid: string, name: string, startSyncDate: string) =>
    send<SetupState>("PATCH", `/setup/accounts/${encodeURIComponent(accountUid)}`, {
      name,
      start_sync_date: startSyncDate,
    }),
  removeConfiguredAccount: (accountUid: string) =>
    drop<SetupState>(`/setup/accounts/${encodeURIComponent(accountUid)}`),
};
