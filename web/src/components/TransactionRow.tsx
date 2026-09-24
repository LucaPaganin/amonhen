import { formatAmount, formatDate, toAmount } from "../format";
import type { Transaction } from "../types";
import { categoryText } from "../category";

interface TransactionRowProps {
  transaction: Transaction;
  runningTotal?: number;
  onSelect?: (transaction: Transaction) => void;
  /** What the queue already tried on this row, if anything. */
  flag?: { label: string; warning?: boolean };
}

export function TransactionRow({ transaction, runningTotal, onSelect, flag }: TransactionRowProps) {
  const title = transaction.merchant ?? transaction.description;
  const amount = formatAmount(transaction.amount);
  const income = toAmount(transaction.amount) >= 0;
  const transfer = transaction.transfer;
  // A leg says where its other half is. Money arriving under a declared name is
  // not a giroconto in the other direction: it is money that is not income, and
  // reading it as one is how a month's income got counted twice.
  const transferLabel = transfer
    ? transfer.kind === "pair"
      ? `Giroconto con ${transfer.target}`
      : income
        ? `Non è un'entrata · ${transfer.target}`
        : `Giroconto verso ${transfer.target}`
    : null;
  const categoryLabel =
    transferLabel ??
    (transaction.splits.length > 1
      ? `${transaction.splits.length} categorie`
      : (transaction.category ?? "senza categoria"));

  const content = (
    <>
      <span className="txn__date">{formatDate(transaction.date)}</span>
      <span className="txn__body">
        <span className="txn__title">{title}</span>
        {transaction.notes === null ? null : (
          <span className="txn__note">{transaction.notes}</span>
        )}
        <span className="txn__meta">
          <span>{transaction.account.name}</span>
          {transferLabel ? (
            <span className="chip chip--transfer">{transferLabel}</span>
          ) : transaction.splits.length > 1 ? (
            <span className="chip chip--split">{categoryLabel}</span>
          ) : transaction.category ? (
            <span className="chip">{categoryText(transaction.category)}</span>
          ) : null}
          {transfer?.state === "proposed" ? (
            <span className="chip chip--warning">Da confermare</span>
          ) : null}
          {transaction.status === "PDNG" ? <span className="chip chip--pending">In attesa</span> : null}
          {flag ? (
            <span className={flag.warning ? "chip chip--warning" : "chip chip--proposal"}>
              {flag.label}
            </span>
          ) : null}
        </span>
      </span>
      <span className="txn__figures">
        <span className={income ? "amount amount--in" : "amount"}>{amount}</span>
        {runningTotal === undefined ? null : (
          <span className="txn__running">Progressivo {formatAmount(runningTotal)}</span>
        )}
      </span>
    </>
  );

  return (
    <li>
      {onSelect ? (
        <button
          type="button"
          className="txn"
          onClick={() => onSelect(transaction)}
          aria-label={`${title}, ${formatDate(transaction.date)}, ${amount}, ${transaction.account.name}, ${categoryLabel}${
            transaction.notes === null ? "" : `, nota: ${transaction.notes}`
          }${transaction.status === "PDNG" ? ", in attesa" : ""}${flag ? `, ${flag.label}` : ""}`}
        >
          {content}
        </button>
      ) : (
        <div className="txn txn--static">{content}</div>
      )}
    </li>
  );
}
