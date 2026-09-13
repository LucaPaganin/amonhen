import { formatAmount, formatDate } from "../format";
import type { Transaction, TransferCandidate, TransferDecision } from "../types";

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "alta",
  medium: "media",
  low: "bassa",
};

// What the matcher based the pair on, in the words of a person reading the card.
const METHOD_LABELS: Record<string, string> = {
  "amount-date-counterparty": "importo, data e i due conti si nominano",
  "amount-date-counterparty-unverified": "importo e data, conti non verificabili",
  "amount-date-counterparty-one-sided": "importo, data e un conto solo identificato",
  "amount-date": "solo importo e data",
  human: "deciso a mano",
};

function Leg({ leg }: { leg: Transaction }) {
  return (
    <p className="leg">
      <span className="leg__description">{leg.merchant ?? leg.description}</span>
      <span className="leg__meta">
        {leg.account.name} · {formatDate(leg.date)}
      </span>
      <span className="leg__amount">{formatAmount(leg.amount)}</span>
    </p>
  );
}

interface TransferCardProps {
  candidate: TransferCandidate;
  onDecision: (decision: TransferDecision) => void;
}

export function TransferCard({ candidate, onDecision }: TransferCardProps) {
  const confidence = CONFIDENCE_LABELS[candidate.confidence] ?? candidate.confidence;
  const method = METHOD_LABELS[candidate.method] ?? candidate.method;

  return (
    <li className="card">
      <p className="card__caption">
        Confidenza {confidence} · {method}
      </p>
      <div className="legs">
        <Leg leg={candidate.leg_a} />
        <Leg leg={candidate.leg_b} />
      </div>
      <div className="card__actions">
        <button type="button" className="button button--primary" onClick={() => onDecision("confirm")}>
          Conferma
        </button>
        <button type="button" className="button button--danger" onClick={() => onDecision("reject")}>
          Rifiuta
        </button>
      </div>
    </li>
  );
}
