import type {
  Account,
  AccountRef,
  Anomaly,
  Category,
  Flows,
  Metrics,
  MonthReading,
  NetWorth,
  Spending,
  Tag,
  Transaction,
  TransferLabels,
} from "../types";

/**
 * The shape of an operation, which this bundle and the server must agree on
 * (`services.offline.FORMAT`). It moves on purpose and by itself, apart from the API
 * version: a server that does not know it refuses the queue, which stays here.
 */
export const OPERATION_FORMAT = 1;

export type OperationKind =
  | "category"
  | "splits"
  | "tag_add"
  | "tag_remove"
  | "note"
  | "delete"
  | "pair"
  | "review";

/**
 * One thing done without a network, with the value the copy held when it was made
 * (`base`): the server compares that with what it holds now, and the difference is
 * the whole conflict test.
 */
export interface Operation {
  id: string;
  kind: OperationKind;
  transaction_id: number;
  value: Record<string, unknown>;
  base: Record<string, unknown>;
  /** When it was made, for the list a person reads; the server does not see it. */
  at: string;
}

/** A proposed pair, by its two legs. */
export interface ProposedPair {
  confidence: string;
  method: string;
  leg_a: number;
  leg_b: number;
}

/** What `/api/offline/bundle` answers: the copy the phone works on. */
export interface Bundle {
  format: number;
  api_version: number;
  created_at: string;
  from: string;
  to: string;
  /** The name of the review bucket: a movement waits while its category is this. */
  uncategorized: string;
  accounts: Account[];
  categories: Category[];
  tags: Tag[];
  transfer_labels: TransferLabels;
  transactions: Transaction[];
  review: {
    queue: number[];
    pending: Record<string, string>;
    proposals_total: number;
    transfers: ProposedPair[];
    transfers_total: number;
    credits: number[];
    credits_total: number;
    accounts: AccountRef[];
  };
  /** Per movement, the legs it could be paired with: the server's own search. */
  candidates: Record<string, number[]>;
}

/** The dashboard's answers for one period the quick chips offer, as they were. */
export interface DashboardSnapshot {
  months: number;
  month: MonthReading;
  metrics: Metrics;
  spending: Spending;
  flows: Flows;
  netWorth: NetWorth;
}

export interface Snapshots {
  taken_at: string;
  periods: DashboardSnapshot[];
  anomalies: Anomaly[];
}

/** What the server says of one operation, in the order it was sent. */
export type OutcomeState = "applicabile" | "gia_cosi" | "conflitto" | "sparita" | "non_valida";

export interface Outcome {
  id: string;
  state: OutcomeState;
  message: string | null;
  /** The server's value, for a conflict, and the token that names it. */
  current: unknown;
  token: string | null;
  applied: boolean;
  dropped: boolean;
}

export interface Resolution {
  id: string;
  choice: "mine" | "server";
  seen: string | null;
}
