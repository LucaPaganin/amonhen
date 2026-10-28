import { useState } from "react";

import { api, errorMessage } from "../api";
import { formatAmount, formatDate, toAmount } from "../format";
import type { Account, DeclaredBalanceCheck, OpeningPreview } from "../types";

/** The figure an opening is derived from, in the words of the sentence it sits in. */
const KIND_WORDS: Record<DeclaredBalanceCheck["kind"], string> = {
  available: "disponibile",
  booked: "contabilizzato",
};

interface OpeningRecalcProps {
  account: Account;
  disabled: boolean;
  /** Writes the opening from the check's figure; answers the error, or null. */
  onAnchor: (account: Account, check: DeclaredBalanceCheck) => Promise<string | null>;
}

interface Proposal {
  check: DeclaredBalanceCheck;
  preview: OpeningPreview | null;
  error: string | null;
}

function signed(value: string): string {
  return toAmount(value) > 0 ? `+${formatAmount(value)}` : formatAmount(value);
}

/**
 * Re-deriving the opening from a declared figure, behind a preview.
 *
 * An anchor makes the 5.4 check agree by construction: whatever the ledger is
 * missing or holds twice goes into the opening, and the check stops reporting
 * it. Next to a red chip it read as the fix, and it was the eraser — two card
 * tolls the bank had subtracted without exposing them were folded into the
 * opening, and counted again the day they arrived. So it is closed by default,
 * at the foot of the panel, and says what it moves before it writes.
 */
export function OpeningRecalc({ account, disabled, onAnchor }: OpeningRecalcProps) {
  const [open, setOpen] = useState(false);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(false);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const checks = account.verification.checks;
  if (checks.length === 0) return null;

  const start = async () => {
    setOpen(true);
    setLoading(true);
    setError(null);
    // The server sums: the client only says which figure, and shows the answer.
    const found = await Promise.all(
      checks.map(async (check): Promise<Proposal> => {
        try {
          const preview = await api.previewOpening(account.id, {
            date: check.date,
            balance: check.declared,
            kind: check.kind,
          });
          return { check, preview, error: null };
        } catch (caught) {
          return { check, preview: null, error: errorMessage(caught) };
        }
      }),
    );
    setProposals(found);
    setLoading(false);
  };

  const write = async (check: DeclaredBalanceCheck) => {
    setWriting(true);
    setError(null);
    const message = await onAnchor(account, check);
    setWriting(false);
    if (message === null) setOpen(false);
    else setError(message);
  };

  if (!open) {
    return (
      <div className="account-row__actions">
        <button type="button" className="button" disabled={disabled} onClick={() => void start()}>
          Ricalcola il saldo iniziale
        </button>
      </div>
    );
  }

  return (
    <div className="opening-recalc">
      <p className="hint">
        Il saldo iniziale è il punto fisso da cui la verifica misura: ricalcolarlo lo ricava dal
        saldo della banca, e qualsiasi differenza di oggi ci finisce dentro. Serve quando il punto
        di partenza era sbagliato, non per far tornare un conto che non torna.
      </p>
      {loading ? (
        <p className="state" aria-busy="true">
          Calcolo…
        </p>
      ) : (
        proposals.map(({ check, preview, error: failed }) => (
          <div className="opening-recalc__option" key={`${check.kind}:${check.date}:${check.source}`}>
            {preview === null ? (
              <p className="state state--error" role="alert">
                Anteprima non disponibile: {failed}
              </p>
            ) : (
              <>
                <p className="opening-recalc__line">
                  {`Dal saldo ${KIND_WORDS[check.kind]} del ${formatDate(check.date)} (${formatAmount(
                    check.declared,
                  )}): il saldo iniziale `}
                  {preview.current_balance === null
                    ? `diventa ${formatAmount(preview.opening_balance)}`
                    : toAmount(preview.change) === 0
                      ? `resta ${formatAmount(preview.opening_balance)}`
                      : `passa da ${formatAmount(preview.current_balance)} a ${formatAmount(
                          preview.opening_balance,
                        )} (${signed(preview.change)})`}
                </p>
                {preview.current_balance !== null && toAmount(preview.change) !== 0 ? (
                  <p className="hint">
                    {`Questi ${formatAmount(
                      String(Math.abs(toAmount(preview.change))),
                    )} non verranno più segnalati. Se sono un movimento che manca o uno arrivato due volte, restano nascosti nel saldo iniziale finché non ricompaiono.`}
                  </p>
                ) : null}
                {preview.current_balance !== null && toAmount(preview.change) === 0 ? null : (
                  <div className="account-row__actions">
                    <button
                      type="button"
                      className={
                        preview.current_balance === null
                          ? "button button--primary"
                          : "button button--danger"
                      }
                      disabled={disabled || writing}
                      onClick={() => void write(check)}
                    >
                      {writing ? "Ricalcolo…" : `Ricalcola dal ${KIND_WORDS[check.kind]}`}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        ))
      )}
      {error === null ? null : (
        <p className="state state--error" role="alert">
          Saldo iniziale non ricalcolato: {error}
        </p>
      )}
      <div className="account-row__actions">
        <button type="button" className="button" disabled={writing} onClick={() => setOpen(false)}>
          Annulla
        </button>
      </div>
    </div>
  );
}
