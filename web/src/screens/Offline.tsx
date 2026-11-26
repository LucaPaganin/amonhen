import { useMemo, useState } from "react";

import { errorMessage, onlineApi } from "../api";
import { Help } from "../components/Help";
import { PeriodRange } from "../components/PeriodRange";
import type { Period } from "../components/PeriodRange";
import { formatDateWithYear, formatMoment, lastMonths } from "../format";
import { action, show, subject } from "../offline/describe";
import {
  afterSend,
  clearCopy,
  discardOperations,
  download,
  setForced,
  useOfflineState,
} from "../offline/session";
import { commitSend, previewSend } from "../offline/send";
import type { Operation, Outcome, OutcomeState, Resolution } from "../offline/types";
import { settle } from "../offline/view";

const STATE_TEXT: Record<OutcomeState, string> = {
  applicabile: "Si può inviare",
  gia_cosi: "Sul server è già così",
  conflitto: "Conflitto: decidi tu",
  sparita: "Il movimento non c'è più",
  non_valida: "Non applicabile",
};

/** The period offered for a first download: the last three months. */
const DEFAULT_MONTHS = 3;

interface OfflineScreenProps {
  /** A download or a send changes what the other screens read: they read again. */
  onChanged: () => void;
}

type Choice = "mine" | "server";

export function OfflineScreen({ onChanged }: OfflineScreenProps) {
  const offline = useOfflineState();
  const [period, setPeriod] = useState<Period>(() => lastMonths(DEFAULT_MONTHS));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<Outcome[] | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [report, setReport] = useState<{ operation: Operation; outcome: Outcome }[] | null>(null);
  const { bundle, queue } = offline;

  const byId = useMemo(() => new Map(queue.map((operation) => [operation.id, operation])), [queue]);

  const guard = async (what: string, work: () => Promise<void>) => {
    setBusy(what);
    setError(null);
    try {
      await work();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(null);
    }
  };

  const startDownload = () =>
    guard("download", async () => {
      if (queue.length > 0 && !window.confirm("Hai modifiche da inviare: la nuova copia prende il posto della vecchia, le modifiche restano in coda. Scaricare?")) {
        return;
      }
      await download(period.from, period.to, onlineApi, lastMonths);
      setOutcomes(null);
      onChanged();
    });

  const startPreview = () =>
    guard("preview", async () => {
      const reply = await previewSend(queue);
      setOutcomes(reply.outcomes);
      setChoices({});
      setReport(null);
    });

  const confirmSend = () =>
    guard("commit", async () => {
      const resolutions: Resolution[] = (outcomes ?? [])
        .filter((outcome) => outcome.state === "conflitto" && choices[outcome.id] !== undefined)
        .map((outcome) => ({ id: outcome.id, choice: choices[outcome.id], seen: outcome.token }));
      const reply = await commitSend(queue, resolutions);
      const settled = reply.outcomes.filter(
        (outcome) =>
          outcome.applied ||
          outcome.dropped ||
          outcome.state === "gia_cosi" ||
          outcome.state === "sparita" ||
          outcome.state === "non_valida",
      );
      const settledIds = new Set(settled.map((outcome) => outcome.id));
      const applied = queue.filter((operation) =>
        reply.outcomes.some((outcome) => outcome.id === operation.id && outcome.applied),
      );
      const remaining = queue.filter((operation) => !settledIds.has(operation.id));
      setReport(
        settled.flatMap((outcome) => {
          const operation = byId.get(outcome.id);
          return operation ? [{ operation, outcome }] : [];
        }),
      );
      setOutcomes(reply.outcomes.filter((outcome) => !settledIds.has(outcome.id)));
      setChoices({});
      if (bundle) {
        // The copy follows the server: read it again, and if the network fails now, keep
        // what the sent operations did to it, so the phone does not show them undone.
        const fallback = settle(bundle, applied);
        await afterSend(fallback, remaining);
        try {
          await download(bundle.from, bundle.to, onlineApi, lastMonths);
        } catch {
          // The send went through; only the refresh did not.
        }
      }
      onChanged();
    });

  const undecided = (outcomes ?? []).filter(
    (outcome) => outcome.state === "conflitto" && choices[outcome.id] === undefined,
  ).length;

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">
            Offline <Help topic="offline" label="uso senza rete" />
          </h1>
          <p className="screen__subtitle">Una copia dei movimenti sul telefono, e le modifiche da inviare.</p>
        </div>
      </header>

      {error !== null ? (
        <div className="state state--error" role="alert">
          <p>{error}</p>
        </div>
      ) : null}

      <section className="panel">
        <h2 className="section-title">La copia sul telefono</h2>
        {bundle === null ? (
          <p className="state">Nessuna copia scaricata.</p>
        ) : (
          <p className="chart-note" data-testid="offline-status">
            Scaricata il {formatMoment(bundle.created_at)}: movimenti dal {formatDateWithYear(bundle.from)} al{" "}
            {formatDateWithYear(bundle.to)}, {bundle.transactions.length} in tutto. Il cruscotto è fermo a quel
            momento.
            {offline.persisted === false ? " Il browser non ha promesso di tenerla: scaricala di nuovo se sparisce." : ""}
          </p>
        )}
        <PeriodRange id="offline" period={period} onChange={setPeriod} />
        <div className="offline-actions">
          <button type="button" className="button button--primary" disabled={busy !== null} onClick={startDownload}>
            {busy === "download" ? "Scarico…" : bundle === null ? "Scarica la copia" : "Scarica di nuovo"}
          </button>
          <button
            type="button"
            className="button button--ghost"
            aria-pressed={offline.forced}
            onClick={() => setForced(!offline.forced)}
            disabled={bundle === null && !offline.forced}
          >
            {offline.forced ? "Torna alla rete" : "Lavora offline"}
          </button>
          <button
            type="button"
            className="button button--danger"
            disabled={bundle === null || busy !== null}
            onClick={() => void guard("clear", clearCopy)}
          >
            Cancella dati offline
          </button>
        </div>
      </section>

      <section className="panel">
        <h2 className="section-title">Da inviare {queue.length > 0 ? `(${queue.length})` : ""}</h2>
        {queue.length === 0 && outcomes === null ? (
          <p className="state">Nessuna modifica in coda.</p>
        ) : null}

        <ul className="offline-list">
          {queue.map((operation) => {
            const outcome = outcomes?.find((item) => item.id === operation.id);
            return (
              <li className="offline-item" key={operation.id} data-state={outcome?.state ?? "coda"}>
                <p className="offline-item__what">{action(bundle, operation)}</p>
                <p className="chart-note">{subject(bundle, operation)}</p>
                {outcome ? (
                  <p className="offline-item__state">
                    {STATE_TEXT[outcome.state]}
                    {outcome.message ? ` — ${outcome.message}` : ""}
                  </p>
                ) : null}
                {outcome?.state === "conflitto" ? (
                  <div className="offline-conflict" role="group" aria-label="Come risolvere il conflitto">
                    <dl>
                      <dt>Quando hai scaricato</dt>
                      <dd>{show(operation.base)}</dd>
                      <dt>La tua modifica</dt>
                      <dd>{show(operation.value)}</dd>
                      <dt>Sul server ora</dt>
                      <dd>{show(outcome.current)}</dd>
                    </dl>
                    <div className="offline-actions">
                      {(["mine", "server"] as const).map((choice) => (
                        <button
                          key={choice}
                          type="button"
                          className="chip chip--toggle"
                          aria-pressed={choices[operation.id] === choice}
                          onClick={() => setChoices({ ...choices, [operation.id]: choice })}
                        >
                          {choice === "mine" ? "Tieni la mia" : "Tieni quella del server"}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
                <button
                  type="button"
                  className="button button--ghost"
                  disabled={busy !== null}
                  onClick={() => void discardOperations([operation.id])}
                >
                  Scarta
                </button>
              </li>
            );
          })}
        </ul>

        {queue.length > 0 ? (
          outcomes === null ? (
            <button type="button" className="button button--primary" disabled={busy !== null} onClick={startPreview}>
              {busy === "preview" ? "Controllo…" : "Invia…"}
            </button>
          ) : (
            <div className="offline-actions">
              <button type="button" className="button button--primary" disabled={busy !== null} onClick={confirmSend}>
                {busy === "commit" ? "Invio…" : "Conferma l'invio"}
              </button>
              <button type="button" className="button button--ghost" onClick={() => setOutcomes(null)}>
                Annulla
              </button>
              {undecided > 0 ? (
                <p className="chart-note">
                  {undecided === 1 ? "Un conflitto senza risposta" : `${undecided} conflitti senza risposta`} resta
                  in coda.
                </p>
              ) : null}
            </div>
          )
        ) : null}

        {report !== null ? (
          <div className="offline-report" role="status">
            <h3>Cosa è successo</h3>
            <ul>
              {report.map(({ operation, outcome }) => (
                <li key={operation.id}>
                  {action(bundle, operation)} — {outcome.applied ? "inviata" : outcome.dropped ? "tenuta quella del server" : STATE_TEXT[outcome.state]}
                  {outcome.message && !outcome.applied && !outcome.dropped ? ` (${outcome.message})` : ""}
                </li>
              ))}
            </ul>
            <button type="button" className="button button--ghost" onClick={() => setReport(null)}>
              Chiudi
            </button>
          </div>
        ) : null}
      </section>
    </section>
  );
}
