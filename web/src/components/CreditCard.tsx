import { useState } from "react";

import { formatAmount, formatDate } from "../format";
import type { Category, Transaction } from "../types";

/** The three things money coming in can be, and which categories mean each. */
const KINDS = [
  { id: "income", label: "Entrata", fits: (item: Category) => item.income },
  {
    id: "refund",
    label: "Rimborso",
    fits: (item: Category) => !item.income && !item.contribution,
  },
  { id: "contribution", label: "Contributo", fits: (item: Category) => item.contribution },
] as const;

type Kind = (typeof KINDS)[number]["id"];

interface CreditCardProps {
  transaction: Transaction;
  /** Every category a movement may take: the review bucket is not one of them. */
  categories: Category[];
  onOpen: (transaction: Transaction) => void;
  onDecide: (category: string, rule: boolean) => void;
}

/**
 * One credit nobody has decided yet. The type comes first because it is what a
 * person knows about the money; the category follows from it, and a type with one
 * category asks nothing more.
 */
export function CreditCard({ transaction, categories, onOpen, onDecide }: CreditCardProps) {
  const [kind, setKind] = useState<Kind | null>(null);
  const [category, setCategory] = useState("");
  const [rule, setRule] = useState(false);
  const label = transaction.merchant ?? transaction.description;
  const options = categories.filter((item) => KINDS.find(({ id }) => id === kind)?.fits(item));

  const choose = (next: Kind) => {
    const fitting = categories.filter((item) => KINDS.find(({ id }) => id === next)?.fits(item));
    setKind(next);
    setCategory(fitting.length === 1 ? fitting[0].name : "");
  };

  return (
    <li className="card credit">
      <button type="button" className="credit__head" onClick={() => onOpen(transaction)}>
        <span className="leg">
          <span className="leg__description" title={transaction.description}>
            {transaction.description}
          </span>
          <span className="leg__meta">
            {transaction.account.name} · {formatDate(transaction.date)}
          </span>
          <span className="leg__amount amount amount--in">{formatAmount(transaction.amount)}</span>
        </span>
      </button>
      <div className="filters__chips" role="group" aria-label={`Che cos'è ${label}`}>
        {KINDS.map(({ id, label: name }) => (
          <button
            key={id}
            type="button"
            className={kind === id ? "chip chip--toggle chip--on" : "chip chip--toggle"}
            aria-pressed={kind === id}
            onClick={() => choose(id)}
          >
            {name}
          </button>
        ))}
      </div>
      {kind === null ? null : options.length === 0 ? (
        <p className="hint">Nessuna categoria di questo tipo: si crea in Categorie e regole.</p>
      ) : (
        <>
          <div className="card__actions">
            <select
              className="input"
              aria-label={`Categoria per ${label}`}
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="" disabled>
                Scegli la categoria
              </option>
              {options.map((item) => (
                <option key={item.id} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="button button--primary"
              disabled={category === ""}
              onClick={() => onDecide(category, rule)}
            >
              Conferma
            </button>
          </div>
          <label className="rule-toggle">
            <input
              type="checkbox"
              checked={rule}
              onChange={(event) => setRule(event.target.checked)}
            />
            <span>Crea una regola per «{label}»</span>
          </label>
        </>
      )}
    </li>
  );
}
