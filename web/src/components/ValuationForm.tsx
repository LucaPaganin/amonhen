import { useState } from "react";
import type { FormEvent } from "react";

import { api, errorMessage } from "../api";
import { formatAmount, toAmount } from "../format";
import type { Account } from "../types";

interface ValuationFormProps {
  account: Account;
  disabled: boolean;
  /** The account changed: what it is worth now, and the return it booked. */
  onValued: (difference: string) => void;
}

function today(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

/**
 * What an investment account added by hand is worth, cash and securities together.
 *
 * Its movements are only the money that went in and out, so the market is in
 * none of them: a declaration alone would leave the check red by exactly what
 * the securities did, and re-deriving the opening would hide the return in it.
 * The server books the difference as a return instead, and this says how much.
 */
export function ValuationForm({ account, disabled, onValued }: ValuationFormProps) {
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(today);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Typed the Italian way, "42.677,95": the comma is the decimal point.
      const plain = value.includes(",") ? value.replace(/\./g, "").replace(",", ".") : value;
      const answer = await api.recordValuation(account.id, { date, value: plain.trim() });
      setOpen(false);
      setValue("");
      onValued(answer.difference);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="button" disabled={disabled} onClick={() => setOpen(true)}>
        Aggiorna il valore
      </button>
    );
  }

  return (
    <form className="opening-recalc" onSubmit={(event) => void submit(event)}>
      <p className="hint">
        Il valore di oggi, liquidità e titoli insieme. La differenza dal saldo dei movimenti è il
        rendimento: va su «Rendimento investimenti», non è un'entrata e non è risparmio.
      </p>
      <div className="field">
        <label htmlFor={`valuation-date-${account.id}`}>Data</label>
        <input
          id={`valuation-date-${account.id}`}
          className="input"
          type="date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
          required
        />
      </div>
      <div className="field">
        <label htmlFor={`valuation-value-${account.id}`}>Valore</label>
        <input
          id={`valuation-value-${account.id}`}
          className="input"
          inputMode="decimal"
          value={value}
          placeholder={formatAmount(toAmount(account.balance))}
          onChange={(event) => setValue(event.target.value)}
          required
        />
      </div>
      {error === null ? null : (
        <p className="state state--error" role="alert">
          {error}
        </p>
      )}
      <div className="account-row__actions">
        <button type="submit" className="button button--primary" disabled={busy || value.trim() === ""}>
          Registra il valore
        </button>
        <button type="button" className="button" disabled={busy} onClick={() => setOpen(false)}>
          Annulla
        </button>
      </div>
    </form>
  );
}
