import { useState } from "react";

import { api, errorMessage } from "../api";
import { formatAmount, formatDate } from "../format";
import type { Account, HeldMovement, PeriodSyncOutcome, RecordAction } from "../types";

/**
 * What writing a movement did, or would do, in the words the panel uses. Each
 * label is followed by its count ("nuovi: 1"), so one word fits every number.
 */
const ACTION_LABELS: Record<RecordAction, string> = {
  inserted: "nuovi",
  duplicate: "già presenti",
  promoted: "da sospesi a contabilizzati",
  updated: "aggiornati",
  suppressed: "cancellati a mano, restano fuori",
  reimported: "cancellati a mano, ripristinati",
  held: "probabili doppioni di un import, in attesa",
  discarded: "probabili doppioni già scartati",
};

/** The same, for one movement of the preview. */
const MOVEMENT_LABELS: Record<RecordAction, string> = {
  inserted: "nuovo",
  duplicate: "già presente",
  promoted: "da sospeso a contabilizzato",
  updated: "aggiornato",
  suppressed: "cancellato a mano, resta fuori",
  reimported: "cancellato a mano, ripristinato",
  held: "probabile doppione: aspetta una decisione",
  discarded: "probabile doppione già scartato",
};

const ACTION_ORDER: RecordAction[] = [
  "inserted",
  "promoted",
  "duplicate",
  "held",
  "discarded",
  "suppressed",
  "reimported",
  "updated",
];

const SOURCE_LABELS: Record<string, string> = { import: "import da file", psd2: "sync" };

function today(): string {
  return new Date().toLocaleDateString("en-CA");
}

/** Thirty days back from today, the default a person starts editing from. */
function monthAgo(): string {
  const date = new Date();
  date.setDate(date.getDate() - 30);
  return date.toLocaleDateString("en-CA");
}

function summary(outcome: PeriodSyncOutcome): string {
  const parts = ACTION_ORDER.filter((action) => (outcome.actions[action] ?? 0) > 0).map(
    (action) => `${ACTION_LABELS[action]}: ${outcome.actions[action]}`,
  );
  if (parts.length === 0) return outcome.preview ? "Niente da scrivere." : "Niente di scritto.";
  return `${outcome.preview ? "Anteprima" : "Fatto"} — ${parts.join(" · ")}.`;
}

function windowLine(window: PeriodSyncOutcome["windows"][number]): string {
  const span = `${formatDate(window.from)} – ${formatDate(window.to)}`;
  if (window.error !== null) return `${span}: la banca ha rifiutato (${window.error})`;
  if (window.fetched === 0) return `${span}: la banca non ha restituito movimenti`;
  return `${span}: ${window.fetched} ${window.fetched === 1 ? "movimento" : "movimenti"}`;
}

interface PeriodSyncProps {
  account: Account;
  held: HeldMovement[];
  /** The ledger changed: balances, verification and the held list are read again. */
  onChanged: () => void;
  onNotice: (message: string) => void;
}

/**
 * One connected account synced over a chosen period, past included. The bank
 * often serves only about ninety days whatever is asked, so every window says
 * what it returned: an empty window is an answer, not a period covered. A
 * movement that looks like one an import wrote in other words is held, and
 * written or discarded here, one at a time.
 */
export function PeriodSync({ account, held, onChanged, onNotice }: PeriodSyncProps) {
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(monthAgo);
  const [to, setTo] = useState(today);
  const [running, setRunning] = useState<"preview" | "write" | null>(null);
  const [outcome, setOutcome] = useState<PeriodSyncOutcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<number | null>(null);
  // The 5.4 state before the last run: a mismatch that a past period brought
  // is the sign of a duplicate, one that was already there says nothing new.
  const [stateBefore, setStateBefore] = useState(account.verification.state);

  const run = async (preview: boolean) => {
    if (running !== null) return;
    setRunning(preview ? "preview" : "write");
    setError(null);
    setStateBefore(account.verification.state);
    try {
      const result = await api.syncPeriod(account.id, from, to, preview);
      setOutcome(result);
      if (!preview) onChanged();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setRunning(null);
    }
  };

  const decide = async (item: HeldMovement, decision: "write" | "discard") => {
    if (deciding !== null) return;
    setDeciding(item.id);
    try {
      await api.decideHeld(item.id, decision);
      onNotice(
        decision === "write"
          ? `Movimento scritto: ${item.description}`
          : `Movimento scartato: ${item.description}`,
      );
      onChanged();
    } catch (caught) {
      onNotice(`Nessuna decisione: ${errorMessage(caught)}`);
    } finally {
      setDeciding(null);
    }
  };

  const invalid = from === "" || to === "" || from > to || to > today();

  return (
    <div className="period-sync">
      {open ? null : (
        <div className="account-row__actions">
          <button type="button" className="button" onClick={() => setOpen(true)}>
            Sincronizza un periodo
          </button>
        </div>
      )}
      {open ? (
        <form
          className="period-sync__form"
          onSubmit={(event) => {
            event.preventDefault();
            void run(false);
          }}
        >
          <p className="hint">
            Chiede alla banca i movimenti di questo conto fra due date, anche passate. Molte banche
            ne restituiscono solo circa novanta giorni: ogni finestra dice cosa è arrivato. Un
            movimento che somiglia a uno importato da file con un'altra descrizione non viene
            scritto finché non decidi tu.
          </p>
          <div className="period-sync__dates">
            <div className="field">
              <label htmlFor={`period-from-${account.id}`}>Dal</label>
              <input
                id={`period-from-${account.id}`}
                type="date"
                max={to || today()}
                value={from}
                onChange={(event) => setFrom(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor={`period-to-${account.id}`}>Al</label>
              <input
                id={`period-to-${account.id}`}
                type="date"
                min={from}
                max={today()}
                value={to}
                onChange={(event) => setTo(event.target.value)}
              />
            </div>
          </div>
          <div className="account-row__actions">
            <button
              type="button"
              className="button"
              disabled={invalid || running !== null}
              onClick={() => void run(true)}
            >
              {running === "preview" ? "Chiedo alla banca…" : "Anteprima"}
            </button>
            <button
              type="submit"
              className="button button--primary"
              disabled={invalid || running !== null}
            >
              {running === "write" ? "Sincronizzo…" : "Sincronizza il periodo"}
            </button>
            <button
              type="button"
              className="button"
              disabled={running !== null}
              onClick={() => {
                setOpen(false);
                setOutcome(null);
                setError(null);
              }}
            >
              Chiudi
            </button>
          </div>
          {error === null ? null : (
            <p className="state state--error" role="alert">
              Periodo non sincronizzato: {error}
            </p>
          )}
          {outcome === null ? null : (
            <div className="period-sync__outcome" aria-live="polite">
              <ul className="period-sync__windows">
                {outcome.windows.map((window) => (
                  <li
                    key={`${window.from}:${window.to}`}
                    className={window.error === null ? undefined : "period-sync__failed"}
                  >
                    {windowLine(window)}
                  </li>
                ))}
              </ul>
              {outcome.error === null ? null : (
                <p className="state state--error" role="alert">
                  {outcome.error}
                </p>
              )}
              <p>{summary(outcome)}</p>
              {outcome.windows.some((window) => window.error !== null) ? (
                <p className="hint">
                  Le finestre rifiutate non sono state scritte: riprova con un periodo più stretto.
                </p>
              ) : null}
              {!outcome.preview &&
              outcome.verification.state === "mismatch" &&
              stateBefore !== "mismatch" ? (
                <p className="state state--error">
                  Prima di questo periodo il saldo tornava con quello dichiarato dalla banca, ora no:
                  è probabile che un movimento sia entrato due volte.
                </p>
              ) : null}
              {/* What is already in the ledger is counted above and not listed:
                  the list is the movements a write would change. */}
              {outcome.preview && outcome.movements.some((m) => m.action !== "duplicate") ? (
                <ul className="trash-list">
                  {outcome.movements
                    .filter((movement) => movement.action !== "duplicate")
                    .map((movement, index) => (
                    <li className="trash-row" key={`${movement.date}:${index}`}>
                      <span className="trash-row__text">
                        <span className="txn__title">{movement.description}</span>
                        <span className="txn__meta">
                          <span>{formatDate(movement.date)}</span>
                          <span>{formatAmount(movement.amount)}</span>
                          <span>{MOVEMENT_LABELS[movement.action]}</span>
                        </span>
                        {movement.twin_description === null ? null : (
                          <span className="txn__note">
                            somiglia a «{movement.twin_description}» (
                            {SOURCE_LABELS[movement.twin_source ?? ""] ?? movement.twin_source})
                          </span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )}
        </form>
      ) : null}
      {held.length === 0 ? null : (
        <div className="period-sync__held">
          <p className="hint">
            {held.length === 1
              ? "1 movimento della banca somiglia a uno importato da file: scrivilo se è un altro movimento, scartalo se è lo stesso."
              : `${held.length} movimenti della banca somigliano a movimenti importati da file: scrivi quelli che sono altri movimenti, scarta quelli che sono gli stessi.`}
          </p>
          <ul className="trash-list">
            {held.map((item) => (
              <li className="trash-row" key={item.id}>
                <span className="trash-row__text">
                  <span className="txn__title">{item.description}</span>
                  <span className="txn__meta">
                    <span>{formatDate(item.date)}</span>
                    <span>{formatAmount(item.amount)}</span>
                  </span>
                  {item.twin_description === null ? null : (
                    <span className="txn__note">
                      già nel ledger come «{item.twin_description}»
                      {item.twin_source_file === null ? "" : ` (${item.twin_source_file})`}
                    </span>
                  )}
                </span>
                <span className="account-row__actions">
                  <button
                    type="button"
                    className="button"
                    disabled={deciding !== null}
                    onClick={() => void decide(item, "write")}
                  >
                    Scrivi
                  </button>
                  <button
                    type="button"
                    className="button"
                    disabled={deciding !== null}
                    onClick={() => void decide(item, "discard")}
                  >
                    Scarta
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
