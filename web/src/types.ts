export type TransactionStatus = "BOOK" | "PDNG";

export interface AccountRef {
  id: number;
  name: string;
}

/** The handshake with the server: `api_version` is absent on an older one. */
export interface Health {
  status: string;
  api_version?: number;
  /** The name the review bucket has on the server: a key, not a word to show. */
  uncategorized?: string;
}

/** What a question is about, when it is about one thing: a row, a budget. */
export interface AssistantContext {
  kind: "cruscotto" | "movimento" | "budget";
  id?: number;
}

/** Desiderata 5.9: whether the assistant is on, and what it already proposed. */
export interface AssistantState {
  configured: boolean;
  model: string | null;
  calls_today: number;
  call_limit: number;
  budget_proposals: BudgetProposal[];
}

/** A monthly budget the assistant proposed: nothing is applied until accepted. */
export interface BudgetProposal {
  category: string;
  amount: string;
  source: string;
  created_at: string;
}

/**
 * What a reading proposes. A category proposal is confirmed where every other
 * proposal is, in the queue; a budget one is decided here.
 */
export interface AssistantProposal {
  kind: "categoria" | "budget";
  merchant?: string;
  category: string;
  amount?: string;
}

/** One reading of the numbers already computed, with the model that wrote it. */
export interface AssistantReading {
  question: string;
  answer: string;
  model: string;
  /** The data it read, hashed: the same question on it is not asked twice. */
  fingerprint: string;
  created_at: string;
  cached: boolean;
  proposals: AssistantProposal[];
}

/** A reading kept, refusals included: `refused` says why it was not shown. */
export interface AssistantHistoryEntry {
  question: string;
  answer: string;
  model: string;
  created_at: string;
  refused: string | null;
}

export interface Account extends AccountRef {
  type: string;
  balance: string;
  investment: boolean;
  opening_date: string | null;
  /** The figure the ledger starts from, or null while nothing anchors it. */
  opening_balance: string | null;
  /** The 5.4 invariant per account: what the bank declared, and whether we agree. */
  verification: AccountVerification;
}

/** A real account added by hand: the broker, or a bank that is not connected. */
export interface NewAccount {
  name: string;
  institution?: string;
  currency?: string;
  opening_balance?: string;
  opening_date?: string;
}

/** A balance read off the bank, and which of its two figures it is. */
export interface Declaration {
  date: string;
  balance: string;
  kind: "available" | "booked";
}

/**
 * One assertion per kind of declaration: the bank's available figure counts the
 * pending movements and its booked figure does not, so a failure says whether to
 * look at the pending rows or at duplicates and gaps.
 */
export interface DeclaredBalanceCheck {
  kind: "available" | "booked";
  source: string;
  date: string;
  declared: string;
  computed: string;
  difference: string;
  ok: boolean;
}

export type AccountVerification =
  | { state: "verified"; date: string; checks: DeclaredBalanceCheck[] }
  | { state: "mismatch"; date: string; checks: DeclaredBalanceCheck[] }
  | { state: "unverified"; date: null; checks: DeclaredBalanceCheck[] };

export interface Category {
  id: number;
  name: string;
  episodic: boolean;
  essential: boolean;
}

export interface Split {
  category: string;
  amount: string;
}

/**
 * What a leg is attached to. `target` is the account the other half sits on for
 * a pair, and the declared destination the money was recorded into when the
 * other half is not in the ledger — an own account that is not connected here,
 * or somebody else's money passing through. `proposed` is waiting for an answer;
 * a link a person made or confirmed is `confirmed`.
 */
export interface TransferDetail {
  kind: "pair" | "passthrough";
  target: string;
  state: "proposed" | "confirmed";
  /** The other leg, for a pair. Null when the other half is not in the ledger. */
  leg_id: number | null;
}

export interface Transaction {
  id: number;
  date: string;
  amount: string;
  description: string;
  merchant: string | null;
  status: TransactionStatus;
  account: AccountRef;
  category: string | null;
  splits: Split[];
  /** Null when the row is not a transfer leg at all. */
  transfer: TransferDetail | null;
  counterparty: string | null;
  source: string;
  /** Queue only: what the automatic passes already made of this row. */
  review_state?: ReviewState;
  /** Queue only: the category a pending proposal suggests, if any. */
  proposed_category?: string | null;
}

/** `proposed`: something is waiting for a decision. `unhandled`: nothing was. */
export type ReviewState = "proposed" | "unhandled";

export interface TransferCandidate {
  confidence: string;
  method: string;
  leg_a: Transaction;
  leg_b: Transaction;
}

export interface ReviewQueue {
  uncategorized: Transaction[];
  uncategorized_total: number;
  proposed_total: number;
  unhandled_total: number;
  /** Accounts with rows in the backlog: the filter offers only real choices. */
  accounts: AccountRef[];
  transfers: TransferCandidate[];
  transfers_total: number;
  proposals_total: number;
}

export interface TransactionPage {
  total: number;
  items: Transaction[];
}

/**
 * What the server actually applied to a reading, echoed back so the client
 * never has to guess what it is looking at.
 */
export interface Applied {
  accounts: string[];
  categories: string[];
  from?: string;
  to?: string;
}

/**
 * The dashboard filters: a period in months, and what to read. Account names
 * narrow everything that belongs to an account; category names narrow the
 * spending alone. Both empty means the whole ledger.
 */
export interface DashboardFilters {
  from: string;
  to: string;
  accounts: string[];
  categories: string[];
}

export interface Metrics {
  currency: string;
  applied: Applied;
  period: { start: string; end: string };
  months_of_history: number;
  partial: boolean;
  episodic_partial: boolean;
  recurring_burn: string | null;
  episodic_accrual: string | null;
  expected_burn: string | null;
  liquidity: string | null;
  runway_months: string | null;
  essential_monthly: string | null;
  discretionary_monthly: string | null;
  savings_flow: string | null;
}

/** One slice of the spending pie: a category and what it took this month. */
export interface CategorySpend {
  category: string;
  amount: string;
}

export interface Spending {
  currency: string;
  applied: Applied;
  period: { start: string; end: string };
  total: string;
  /** Each slice is what that category took in the whole period. */
  categories: CategorySpend[];
}

/** One month of the income/expense chart; `partial` marks the month in progress. */
export interface MonthlyFlow {
  month: string;
  income: string;
  expenses: string;
  partial: boolean;
}

export interface Flows {
  currency: string;
  applied: Applied;
  months: MonthlyFlow[];
}

/** A balance the bank reported, never a reconstructed one. */
export interface NetWorthPoint {
  date: string;
  total: string;
}

export interface AccountBalance {
  account: string;
  date: string;
  balance: string;
}

export interface NetWorth {
  currency: string;
  applied: Applied;
  points: NetWorthPoint[];
  accounts: AccountBalance[];
}

export type TransferDecision = "confirm" | "reject";

/** The names a leg can be recorded into: declared in the config, or already used. */
export interface TransferLabels {
  configured: string[];
  recorded: string[];
}

export interface TransferUnlink {
  /** The declared destination the leg pointed at, when it was a lone leg. */
  released: string | null;
  /** True when a sync re-applies that label, so unlinking it will not stick. */
  configured: boolean;
  transaction: Transaction;
}

export interface Budget {
  id: number;
  category: string;
  /** null when the category has no budget this month. */
  budget: string | null;
  spent: string;
  /** null when there is no budget; negative when the month is over budget. */
  remaining: string | null;
}

export interface Anomaly {
  transaction_id: number;
  date: string;
  merchant: string;
  category: string;
  amount: string;
  median: string;
  mad: string;
  score: string;
  method: "mad" | "p95";
  /** Ready-to-show Italian explanation built by the backend. */
  sentence: string;
}

export interface Suggestion {
  merchant: string;
  category: string;
  source: "classifier" | "llm";
  created_at: string;
}

export type SuggestionDecision = "accept" | "dismiss";

/** A saved text -> category rule and how many movements it currently holds. */
export interface Rule {
  pattern: string;
  category: string;
  count: number;
}
