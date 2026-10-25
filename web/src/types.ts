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
  /** On: the next sync writes back the movements deleted from this account. */
  reimport_deleted: boolean;
  opening_date: string | null;
  /** The figure the ledger starts from, or null while nothing anchors it. */
  opening_balance: string | null;
  /** Seen by a sync: Enable Banking knows it, so a period can be asked for it. */
  connected: boolean;
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
  /** The difference is the movements a person deleted, and nothing else. */
  explained: boolean;
  /** What those deleted movements would have added to this figure, signed. */
  suppressed: string;
  suppressed_count: number;
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
  /** Reconciled except for what somebody deleted here, by hand. */
  | { state: "suppressed"; date: string; checks: DeclaredBalanceCheck[] }
  | { state: "mismatch"; date: string; checks: DeclaredBalanceCheck[] }
  | { state: "unverified"; date: null; checks: DeclaredBalanceCheck[] };

/** One account's part of a sync: what it returned, and what the ledger made of it. */
export interface SyncAccountResult {
  account: string;
  fetched: number;
  balances: number;
  /** How the movements were absorbed: `inserted`, `promoted`, `duplicate`, … */
  actions: Record<string, number>;
  error: string | null;
  /** The sync's own 5.4 sentence, when the ledger and the bank disagreed. */
  balance_mismatch: string | null;
  verification: AccountVerification | null;
}

/** What a sync wrote, per account, with what it could not read. */
export interface SyncOutcome {
  accounts: SyncAccountResult[];
  transfers_linked: number;
  rules_applied: number;
  passthrough_legs: number;
  errors: string[];
}

/** One window of a period sync: what the bank returned, or why it did not. */
export interface PeriodWindow {
  from: string;
  to: string;
  fetched: number;
  error: string | null;
}

/** What writing a movement does, as the ledger answers it. */
export type RecordAction =
  | "inserted"
  | "duplicate"
  | "promoted"
  | "updated"
  | "suppressed"
  | "reimported"
  | "held"
  | "discarded";

/** One movement of a period preview, with what writing it would do. */
export interface PeriodMovement {
  date: string;
  amount: string;
  description: string;
  status: TransactionStatus;
  action: RecordAction;
  /** The row a probable duplicate resembles, and the path that wrote it. */
  twin_description: string | null;
  twin_source: string | null;
}

/** A sync of one account over a chosen period, or its preview. */
export interface PeriodSyncOutcome {
  account: string;
  from: string;
  to: string;
  preview: boolean;
  windows: PeriodWindow[];
  actions: Partial<Record<RecordAction, number>>;
  /** Filled by the preview only. */
  movements: PeriodMovement[];
  /** Probable duplicates of an import still waiting for a person, on this account. */
  held: number;
  transfers_linked: number;
  passthrough_legs: number;
  rules_applied: number;
  error: string | null;
  balance_mismatch: string | null;
  errors: string[];
  verification: AccountVerification;
}

/** A movement a period sync did not write: it looks like one an import wrote. */
export interface HeldMovement {
  id: number;
  account_id: number;
  account: string;
  date: string;
  amount: string;
  description: string;
  twin_id: number | null;
  twin_description: string | null;
  twin_source: string | null;
  twin_source_file: string | null;
}

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
  /** The note a person wrote on this movement; the only field they may write. */
  notes: string | null;
  /** Queue only: what the automatic passes already made of this row. */
  review_state?: ReviewState;
  /** Queue only: the category a pending proposal suggests, if any. */
  proposed_category?: string | null;
}

/** `proposed`: something is waiting for a decision. `unhandled`: nothing was. */
export type ReviewState = "proposed" | "unhandled";

/**
 * A movement taken out of the ledger. `unlinked_pair` says a transfer was
 * undone with it: the other leg is spending again, and the row that said so is
 * gone, so the app has to tell the person rather than let it look untouched.
 */
export interface Deletion {
  id: number;
  unlinked_pair: boolean;
}

/** A deleted movement as the trash reads it: enough to recognise, and to undo. */
export interface DeletedMovement {
  id: number;
  account: AccountRef;
  date: string;
  amount: string;
  description: string;
  merchant: string | null;
  status: TransactionStatus;
  notes: string | null;
  /** When it was deleted, ISO: the list says it without a time of day. */
  deleted_at: string;
}

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

/** Read in this order: what cannot be skipped first, what can wait last. */
export type BudgetPriority = "essential" | "important" | "deferrable";

/** An expense planned inside a category's budget for one month (desiderata 5.12). */
export interface BudgetItem {
  id: number;
  description: string;
  amount: string;
  /** A day inside the item's month, or null when it has none. */
  date: string | null;
  priority: BudgetPriority;
  note: string | null;
  /** Read in priority order, whether it still fits the budget; null without one. */
  fits: boolean | null;
}

/** A category's budget for one month, as the server computed it. */
export interface Budget {
  id: number;
  category: string;
  /** What holds this month: the override when there is one, else the default. */
  budget: string | null;
  /** The default the category holds this month, written in this or an earlier one. */
  default: string | null;
  /** This month's own budget, when it has one. */
  override: string | null;
  spent: string;
  /** null when there is no budget; negative when the month is over budget. */
  remaining: string | null;
  /** The sum of the items. */
  planned: string;
  /** The budget the items leave; negative when they exceed it, null without one. */
  free: string | null;
  over_plan: boolean;
  items: BudgetItem[];
}

/** What a planned expense is written with, new or edited. */
export interface BudgetItemDraft {
  category_id: number;
  month: string;
  description: string;
  amount: string;
  date: string | null;
  priority: BudgetPriority;
  note: string | null;
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

/** What a proposal would settle: a merchant's waiting movements, and their span. */
export interface SuggestionStake {
  movements: number;
  total: string;
  /** Null when nothing is waiting for this merchant any more. */
  first_date: string | null;
  last_date: string | null;
}

export interface Suggestion {
  merchant: string;
  category: string;
  source: "classifier" | "llm";
  created_at: string;
  /** What accepting or rejecting decides: usually more than one movement. */
  stake: SuggestionStake;
}

export type SuggestionDecision = "accept" | "dismiss";

/** What a decision did: the category it assigned, the rule it wrote when one was
 * asked for, and how many movements that rule holds. A dismissal did nothing. */
export interface SuggestionDecisionOutcome {
  merchant: string;
  decision: SuggestionDecision;
  category: string | null;
  rule: string | null;
  movements: number;
}

/** What a rule does to the movements it matches. */
export type RuleAction = "category" | "delete" | "transfer";

/**
 * A saved rule and how many movements it currently holds: a text, the conditions
 * that narrow it, and what follows. `target` is the category or the destination;
 * `category` repeats it for a category rule only.
 */
export interface Rule {
  id: number;
  pattern: string;
  action: RuleAction;
  target: string | null;
  category: string | null;
  account_id: number | null;
  account: string | null;
  /** Sizes, sign left out: "between 5 and 10 euro". */
  amount_min: string | null;
  amount_max: string | null;
  count: number;
}

/** A rule as the editor writes it; `id` changes that rule instead of matching by text. */
export interface RuleDraft {
  id?: number | null;
  pattern: string;
  action: RuleAction;
  target: string | null;
  account_id: number | null;
  amount_min: string | null;
  amount_max: string | null;
}

/** The movements a rule would take, before it is written. */
export interface RulePreview {
  count: number;
  items: { id: number; date: string; amount: string; description: string; account: string }[];
}

export interface BatchDeletion {
  deleted: number;
  unlinked_pairs: number;
}

export interface BatchCategory {
  categorized: number;
  skipped: number;
}

export interface AccountDeletion {
  name: string;
  movements: number;
  /** True when the account was also taken out of the sync's configuration. */
  disconnected: boolean;
}

/** What the first setup still has to write, as the machine key that names it. */
export type SetupRequirement = "application_id" | "private_key" | "accounts";

/** One entry of the configuration file: an account an authorization found. */
export interface ConfiguredAccount {
  /** Enable Banking's own identifier: how the entry is renamed or dropped. */
  account_uid: string;
  /** The ledger's name for the account, which is what a rename decides. */
  name: string;
  institution: string;
  country: string;
  /** From when the movements are imported; null imports everything. */
  start_sync_date: string | null;
  /** When the consent stops working, as the bank reported it. */
  session_expiry: string | null;
}

/** What the last authorization wrote, so the return from the bank is visible. */
export interface SetupLastConnect {
  when: string;
  /** Per account: added by this authorization, or an existing consent renewed. */
  written: { account: string; action: "added" | "refreshed" }[];
}

/**
 * The configuration as the server sees it, the file that does not exist yet
 * included: `missing` names what has to be written before the app can work, and
 * `configured` is true exactly when nothing is missing.
 */
export interface SetupState {
  configured: boolean;
  missing: SetupRequirement[];
  application_id: string;
  redirect_url: string;
  account_holder_name: string;
  /** Where the private key was written; the key itself never travels back. */
  pem_path: string;
  key_loads: boolean;
  accounts: ConfiguredAccount[];
  last_connect: SetupLastConnect | null;
}

/** The credentials the first step collects; the key only when it is being set. */
export interface SetupCredentials {
  application_id: string;
  redirect_url: string;
  account_holder_name?: string;
  private_key?: string;
}

/** One bank an authorization can be started for, by its exact ASPSP name. */
export interface SetupBank {
  name: string;
  country: string;
}

/** The banks one country has, already filtered and sorted by the server. */
export interface SetupBanks {
  country: string;
  banks: SetupBank[];
}

/** One row of a CSV as the chosen mapping reads it, before anything is written. */
export interface CsvPreviewRow {
  line: number;
  date: string;
  amount: string;
  description: string;
}

/** A row the mapping could not read: the line in the file and why. */
export interface CsvRejectedRow {
  line: number;
  reason: string;
}

/** What the file would become: the columns to choose from, and the first rows. */
export interface CsvPreview {
  ready: boolean;
  problem: string | null;
  columns: string[];
  rows: CsvPreviewRow[];
  parsed: number;
  rejected: CsvRejectedRow[];
}

/** What the import wrote, and what it left alone. */
export interface CsvImportOutcome {
  account: string;
  filename: string;
  parsed: number;
  /** How many rows each thing happened to: inserted, duplicate, and the rest. */
  actions: Record<string, number>;
  rejected: CsvRejectedRow[];
  passthrough: number;
  rules: number;
}
