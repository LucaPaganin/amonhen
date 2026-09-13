import { useEffect, useId, useRef, useState } from "react";
import type { MouseEvent } from "react";

import { api, errorMessage } from "../api";
import { formatAmount, formatDate } from "../format";
import type { Transaction, TransferLabels } from "../types";

interface TransferPanelProps {
  open: boolean;
  transaction: Transaction | null;
  onDone: (notice: string) => void;
  onClose: () => void;
}

/**
 * What a row is attached to, and the ways to change that by hand.
 *
 * A leg the matcher proposed can be answered here as well as in the queue; a
 * movement that is not a transfer can be recorded into a declared destination —
 * an own account that is not connected here, or the name of whoever sent money
 * that is not income — or paired with the movement the matcher itself
 * would have accepted. Nothing here invents a half: a lone leg says which
 * account it went to, a pair says which account holds the other end.
 */
export function TransferPanel({ open, transaction, onDone, onClose }: TransferPanelProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [labels, setLabels] = useState<TransferLabels>({ configured: [], recorded: [] });
  const [destination, setDestination] = useState("");
  const [counterpart, setCounterpart] = useState<Transaction | null>(null);
  const [candidates, setCandidates] = useState<Transaction[] | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!open || transaction === null) {
      if (dialog.open) dialog.close();
      return;
    }
    setDestination("");
    setChosen(null);
    setCounterpart(null);
    setCandidates(null);
    setError(null);
    if (!dialog.open) dialog.showModal();

    const controller = new AbortController();
    if (transaction.transfer === null) {
      api
        .transferLabels(controller.signal)
        .then(setLabels)
        .catch(() => undefined);
      api
        .transferCandidates(transaction.id, controller.signal)
        .then(setCandidates)
        .catch((failure) => {
          // An empty list would read as "nothing matches", which is a different
          // statement than "the lookup failed".
          setCandidates([]);
          setError(errorMessage(failure));
        });
    } else if (transaction.transfer.leg_id !== null) {
      api
        .transaction(transaction.transfer.leg_id, controller.signal)
        .then(setCounterpart)
        .catch(() => undefined);
    }
    return () => controller.abort();
  }, [open, transaction]);

  const run = async (action: () => Promise<string>) => {
    setBusy(true);
    setError(null);
    try {
      const notice = await action();
      onDone(notice);
      onClose();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  };

  const handleBackdropClick = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === dialogRef.current) onClose();
  };

  const transfer = transaction?.transfer ?? null;
  const proposedLeg = transfer?.state === "proposed" ? transfer.leg_id : null;
  // The configuration and the ledger usually name the same account: offering it
  // twice would read as two accounts.
  const available = [
    ...new Map(
      [...labels.configured, ...labels.recorded].map((name) => [name.toLocaleLowerCase(), name]),
    ).values(),
  ];

  return (
    <dialog
      ref={dialogRef}
      className="sheet"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      onClick={handleBackdropClick}
    >
      <div className="sheet__panel">
        <header className="sheet__header">
          <h2 className="sheet__title" id={titleId}>
            {transfer ? "Giroconto o denaro non tuo" : "Segna come giroconto o denaro non tuo"}
          </h2>
          <button type="button" className="button button--ghost" onClick={onClose} aria-label="Chiudi">
            ✕
          </button>
        </header>

        {transaction === null ? null : (
          <>
            <p className="transfer__subject">
              <span className="transfer__description">
                {transaction.merchant ?? transaction.description}
              </span>
              <span className="leg__meta">
                {transaction.account.name} · {formatDate(transaction.date)} ·{" "}
                {formatAmount(transaction.amount)}
              </span>
            </p>

            {transfer ? (
              <>
                <p className="transfer__state">
                  {transfer.kind === "passthrough"
                    ? `Registrato verso «${transfer.target}»: né una spesa né un'entrata.`
                    : `Abbinato al movimento su «${transfer.target}».`}
                  {transfer.state === "proposed" ? " Il matcher l'ha proposto: tocca a te dirlo." : ""}
                </p>

                {counterpart ? (
                  <p className="leg">
                    <span className="leg__description">
                      {counterpart.merchant ?? counterpart.description}
                    </span>
                    <span className="leg__meta">
                      {counterpart.account.name} · {formatDate(counterpart.date)}
                    </span>
                    <span className="leg__amount">{formatAmount(counterpart.amount)}</span>
                  </p>
                ) : null}

                {proposedLeg !== null ? (
                  <button
                    type="button"
                    className="button button--primary button--block"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        await api.reviewTransfer(proposedLeg, transaction.id, "confirm");
                        return "Giroconto confermato";
                      })
                    }
                  >
                    È un giroconto
                  </button>
                ) : null}

                <button
                  type="button"
                  className="button button--danger button--block"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      const result = await api.unlinkTransfer(transaction.id);
                      if (result.configured && result.released) {
                        return `Segno annullato, ma «${result.released}» è fra le voci dichiarate in accounts.json: il prossimo sync lo rimette`;
                      }
                      return "Segno annullato: il movimento torna in coda";
                    })
                  }
                >
                  Annulla il segno
                </button>
              </>
            ) : (
              <>
                <p className="transfer__hint">
                  Vale per il denaro che non è tuo da contare: quello che sposti fra conti
                  tuoi, la quota di chi condivide un conto, un rimborso. Non è una spesa e
                  non è un&apos;entrata.
                </p>

                <form
                  className="sheet__new"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const name = destination.trim();
                    void run(async () => {
                      await api.markPassthrough(transaction.id, name);
                      return `Registrato verso «${name}»: fuori dalle spese e dalle entrate`;
                    });
                  }}
                >
                  <label className="sheet__new-label" htmlFor={`${titleId}-label`}>
                    Verso un conto tuo non collegato, o il nome di chi manda il denaro
                  </label>
                  <div className="sheet__new-row">
                    <input
                      id={`${titleId}-label`}
                      className="input"
                      type="text"
                      list={`${titleId}-labels`}
                      value={destination}
                      placeholder="Es. Conto deposito senza vincoli"
                      autoComplete="off"
                      onChange={(event) => setDestination(event.target.value)}
                    />
                    <datalist id={`${titleId}-labels`}>
                      {available.map((name) => (
                        <option key={name} value={name} />
                      ))}
                    </datalist>
                    <button type="submit" className="button" disabled={busy || destination.trim() === ""}>
                      {busy ? "Registro…" : "Registra"}
                    </button>
                  </div>
                </form>

                <h3 className="transfer__subtitle">Oppure abbinalo a un altro movimento</h3>
                {candidates === null ? (
                  <p className="state" aria-busy="true">
                    Cerco…
                  </p>
                ) : candidates.length === 0 ? (
                  <p className="state">
                    Nessun movimento con l&apos;importo opposto su un altro conto negli stessi
                    giorni.
                  </p>
                ) : (
                  <ul className="sheet__list">
                    {candidates.map((candidate) => (
                      <li key={candidate.id}>
                        <button
                          type="button"
                          className={
                            chosen === candidate.id ? "sheet__option sheet__option--on" : "sheet__option"
                          }
                          aria-pressed={chosen === candidate.id}
                          onClick={() => setChosen(candidate.id)}
                        >
                          <span className="leg__description">
                            {candidate.merchant ?? candidate.description}
                          </span>
                          <span className="leg__meta">
                            {candidate.account.name} · {formatDate(candidate.date)}
                          </span>
                          <span className="leg__amount">{formatAmount(candidate.amount)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                {chosen !== null ? (
                  <button
                    type="button"
                    className="button button--primary button--block"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        const other = candidates?.find((candidate) => candidate.id === chosen);
                        await api.pairTransfer(transaction.id, chosen);
                        const name = other?.merchant ?? other?.description ?? String(chosen);
                        return `Giroconto abbinato con «${name}»`;
                      })
                    }
                  >
                    Abbina
                  </button>
                ) : null}
              </>
            )}

            {error ? (
              <p className="state state--error" role="alert">
                {error}
              </p>
            ) : null}
          </>
        )}
      </div>
    </dialog>
  );
}
