import { useState } from "react";

import { errorMessage } from "../api";
import type { SplitInput } from "../api";
import { formatAmount, toAmount } from "../format";
import type { Category, Transaction } from "../types";
import { categoryText } from "../category";

interface SplitRow {
  category: string;
  amount: string;
}

interface SplitEditorProps {
  transaction: Transaction;
  categories: Category[];
  onSave: (splits: SplitInput[]) => Promise<void>;
  onCancel: () => void;
}

function initialRows(transaction: Transaction): SplitRow[] {
  if (transaction.splits.length > 0) {
    return transaction.splits.map((split) => ({
      category: split.category,
      amount: Math.abs(toAmount(split.amount)).toFixed(2),
    }));
  }
  return [{ category: transaction.category ?? "", amount: "" }];
}

export function SplitEditor({ transaction, categories, onSave, onCancel }: SplitEditorProps) {
  const [rows, setRows] = useState<SplitRow[]>(() => initialRows(transaction));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Category postings carry the opposite sign of the real account, so the
  // editor works in magnitudes and re-applies the sign only when saving.
  const sign = toAmount(transaction.amount) > 0 ? -1 : 1;
  const target = Math.abs(toAmount(transaction.amount));
  const total = rows.reduce((sum, row) => sum + toAmount(row.amount), 0);
  const balanced = Math.abs(total - target) < 0.005;
  const complete = rows.every(
    (row) => row.category !== "" && row.amount.trim() !== "" && toAmount(row.amount) > 0,
  );
  const canSave = rows.length > 0 && complete && !saving;

  const updateRow = (index: number, patch: Partial<SplitRow>) => {
    setRows((current) =>
      current.map((row, position) => (position === index ? { ...row, ...patch } : row)),
    );
  };

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    const splits = rows.map((row) => ({
      category: row.category,
      amount: (sign * toAmount(row.amount)).toFixed(2),
    }));
    try {
      await onSave(splits);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="split">
      <p className="split__hint">
        Dividi il movimento tra più categorie. Il totale deve corrispondere all'importo del
        movimento.
      </p>

      <ul className="split__rows">
        {rows.map((row, index) => {
          const known = row.category === "" || categories.some((item) => item.name === row.category);
          return (
            <li className="split__row" key={index}>
              <select
                className="split__category"
                aria-label={`Categoria riga ${index + 1}`}
                value={row.category}
                onChange={(event) => updateRow(index, { category: event.target.value })}
              >
                <option value="">Scegli…</option>
                {known ? null : <option value={row.category}>{categoryText(row.category)}</option>}
                {categories.map((item) => (
                  <option key={item.id} value={item.name}>
                    {categoryText(item.name)}
                  </option>
                ))}
              </select>
              <input
                className="split__amount"
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                placeholder="0,00"
                aria-label={`Importo riga ${index + 1}`}
                value={row.amount}
                onChange={(event) => updateRow(index, { amount: event.target.value })}
              />
              <button
                type="button"
                className="button button--ghost split__remove"
                aria-label={`Rimuovi riga ${index + 1}`}
                disabled={rows.length === 1}
                onClick={() => setRows((current) => current.filter((_, position) => position !== index))}
              >
                ✕
              </button>
            </li>
          );
        })}
      </ul>

      <button
        type="button"
        className="button"
        onClick={() => setRows((current) => [...current, { category: "", amount: "" }])}
      >
        Aggiungi riga
      </button>

      <p className={balanced ? "split__total split__total--ok" : "split__total split__total--off"}>
        Totale {formatAmount(total)} su {formatAmount(target)}
        {balanced
          ? null
          : total < target
            ? ` · mancano ${formatAmount(target - total)}`
            : ` · eccedono ${formatAmount(total - target)}`}
      </p>

      {error ? (
        <p className="state state--error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="split__actions">
        <button type="button" className="button" onClick={onCancel} disabled={saving}>
          Annulla
        </button>
        <button type="button" className="button button--primary" onClick={() => void handleSave()} disabled={!canSave}>
          {saving ? "Salvo…" : "Salva split"}
        </button>
      </div>
    </div>
  );
}
