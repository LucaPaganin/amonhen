import { useId, useState } from "react";

import { categoryText } from "../category";
import { formatAmount } from "../format";
import type { AssistantContext } from "../types";
import { useAssistant } from "../useAssistant";

/** The questions that are asked most often, one press away. */
const PROMPTS: { label: string; question: string }[] = [
  { label: "Il mese", question: "Cosa è cambiato questo mese rispetto al solito?" },
  { label: "La coda", question: "Da dove comincio nella coda?" },
  { label: "I budget", question: "Quale budget non regge, e perché?" },
];

function questionFor(context: AssistantContext): string {
  if (context.kind === "budget") return "Questo budget regge?";
  if (context.kind === "movimento") return "Com'è questo movimento?";
  return "Cosa è cambiato questo mese?";
}

/** Where the question came from, in the words of the screen that sent it. */
function originOf(context: AssistantContext): string {
  if (context.kind === "budget") return "Arriva dal pulsante «Regge?» di un budget";
  if (context.kind === "movimento") return "Arriva dalla scheda di un movimento";
  return "Arriva da un'altra schermata";
}

interface AssistantScreenProps {
  /** What the section was opened from, when it was opened from somewhere. */
  context: AssistantContext | null;
  /** Said when the proposed question has been asked or let go, so it goes away. */
  onContextDone: () => void;
}

export function AssistantScreen({ context, onContextDone }: AssistantScreenProps) {
  const assistant = useAssistant();
  const [question, setQuestion] = useState("");
  const questionId = useId();
  const { ask, decide } = assistant;
  const state = assistant.state;

  // La domanda che un'altra schermata ha portato qui è composta, non chiesta:
  // una chiamata parte da un pulsante e da nient'altro, perché esce dalla
  // macchina verso un fornitore esterno ed è contata. Il pannello dice cosa
  // verrebbe domandato e a chi, e a mandarla è il dito.
  const suggestion =
    context === null
      ? null
      : { context, question: questionFor(context), origin: originOf(context) };

  const askSuggestion = async () => {
    if (suggestion === null) return;
    // Il pannello resta in piedi se la chiamata non riesce: la domanda composta
    // non si perde, e si riprova senza tornare alla riga che l'aveva portata qui.
    if (await ask(suggestion.question, suggestion.context)) onContextDone();
  };

  // Chiedere qualcos'altro lascia cadere la domanda che era in attesa: in
  // schermata se ne tiene una sola, quella a cui si sta rispondendo.
  const askFromTheScreen = (asked: string) => {
    void ask(asked, { kind: "cruscotto" });
    if (suggestion !== null) onContextDone();
  };

  // Il modello si nomina mentre la richiesta è in volo: chi ha premuto vede chi
  // sta rispondendo, invece di un'attesa senza soggetto. Prima che lo stato
  // arrivi non c'è ancora un nome, e la frase deve restare in italiano.
  const askingLabel = state?.model ? `Chiedo a ${state.model}…` : "Chiedo al modello…";

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Assistente</h1>
          <p className="screen__subtitle">
            {state === null
              ? "Leggo i numeri già calcolati…"
              : state.configured
                ? `${state.model} · ${state.calls_today} chiamate su ${state.call_limit} oggi`
                : "Spento: manca il modello in configurazione"}
          </p>
        </div>
      </header>

      {assistant.stateError ? (
        <div className="state state--error" role="alert">
          <p>{assistant.stateError}</p>
        </div>
      ) : null}

      {state !== null && !state.configured ? (
        <div className="state">
          <p>
            L&apos;assistente è configurazione, non codice: senza endpoint e modello la sezione
            resta spenta, e nessuna schermata dell&apos;app dipende da lei.
          </p>
          <pre className="state__command">
            AMONHEN_LLM_URL=https://api.deepseek.com/chat/completions{"\n"}
            AMONHEN_LLM_MODEL=deepseek-v4-flash{"\n"}
            AMONHEN_LLM_API_KEY=…
          </pre>
        </div>
      ) : null}

      {suggestion === null ? null : (
        <section className="panel">
          <h2 className="section-title">Domanda pronta</h2>
          <p>{suggestion.question}</p>
          <p className="chart-note">
            {suggestion.origin}
            {state?.configured === false
              ? ": l'assistente è spento, quindi la domanda resta qui e non parte."
              : `: a rispondere è ${state?.model ?? "il modello configurato"}, e lo manda il ` +
                "pulsante qui sotto. Se la stessa domanda sugli stessi numeri ha già una " +
                "risposta, torna quella e non parte nessuna chiamata."}
          </p>
          <div className="card__actions">
            <button
              type="button"
              className="button button--primary"
              disabled={assistant.asking || state?.configured === false}
              onClick={() => void askSuggestion()}
            >
              {assistant.asking ? askingLabel : "Chiedi"}
            </button>
            <button type="button" className="button" onClick={onContextDone}>
              Lascia perdere
            </button>
          </div>
        </section>
      )}

      <section className="panel">
        <h2 className="section-title">Cosa vuoi sapere</h2>
        <p className="chart-note">
          La lettura parla dei numeri che l&apos;app ha già calcolato: non fa i conti e non scrive
          niente. Quello che propone lo confermi tu.
        </p>
        <div className="filters__chips" role="group" aria-label="Domande pronte">
          {PROMPTS.map((prompt) => (
            <button
              key={prompt.label}
              type="button"
              className="chip chip--toggle"
              disabled={assistant.asking || state?.configured === false}
              onClick={() => askFromTheScreen(prompt.question)}
            >
              {prompt.label}
            </button>
          ))}
        </div>
        <form
          className="filters"
          onSubmit={(event) => {
            event.preventDefault();
            askFromTheScreen(question.trim());
          }}
        >
          <div className="field field--wide">
            <label htmlFor={questionId}>Domanda</label>
            <input
              id={questionId}
              className="input"
              type="text"
              value={question}
              placeholder="Es. perché agosto è più caro di luglio?"
              onChange={(event) => setQuestion(event.target.value)}
            />
          </div>
          <button
            type="submit"
            className="button button--primary"
            disabled={assistant.asking || state?.configured === false}
          >
            {assistant.asking ? askingLabel : "Chiedi"}
          </button>
        </form>
      </section>

      {assistant.askError ? (
        <div className="state state--error" role="alert">
          <p>{assistant.askError}</p>
        </div>
      ) : null}

      {assistant.reading === null ? null : (
        <section className="panel">
          <h2 className="section-title">
            Lettura{" "}
            <span className="count">{assistant.reading.cached ? "già chiesta" : "nuova"}</span>
          </h2>
          <article className="card">
            <p className="card__caption">
              Testo generato da {assistant.reading.model} · dati {assistant.reading.fingerprint}
              {assistant.reading.cached ? " · stessa domanda, stessi numeri" : ""}
            </p>
            <p className="assistant__answer">{assistant.reading.answer}</p>
            <p className="chart-note">
              Le cifre nella prosa sono citazioni dei numeri calcolati qui: se il modello ne
              scrivesse una sua, la lettura verrebbe rifiutata invece che mostrata.
            </p>
          </article>
          {assistant.reading.proposals.length === 0 ? null : (
            <ul className="card-list">
              {assistant.reading.proposals.map((proposal) => (
                <li
                  className="card"
                  key={`${proposal.kind}-${proposal.merchant ?? ""}-${proposal.category}`}
                >
                  <p className="card__caption">
                    {proposal.kind === "categoria"
                      ? "Proposta di categoria"
                      : "Proposta di budget"}
                  </p>
                  <p className="proposal__head">
                    <span className="proposal__merchant">
                      {proposal.merchant ?? categoryText(proposal.category)}
                    </span>
                    <span className="chip">{categoryText(proposal.category)}</span>
                    {proposal.amount ? (
                      <span className="chip">{formatAmount(proposal.amount)} al mese</span>
                    ) : null}
                  </p>
                  {proposal.kind === "categoria" ? (
                    <p className="chart-note">Si conferma in «Da confermare», come ogni proposta.</p>
                  ) : (
                    <div className="card__actions">
                      <button
                        type="button"
                        className="button button--primary"
                        onClick={() => void decide(proposal.category, "accept")}
                      >
                        Accetta
                      </button>
                      <button
                        type="button"
                        className="button button--danger"
                        onClick={() => void decide(proposal.category, "dismiss")}
                      >
                        Scarta
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {state === null || state.budget_proposals.length === 0 ? null : (
        <section className="panel">
          <h2 className="section-title">
            Budget proposti <span className="count">{state.budget_proposals.length}</span>
          </h2>
          <ul className="card-list">
            {state.budget_proposals.map((proposal) => (
              <li className="card" key={proposal.category}>
                <p className="proposal__head">
                  <span className="proposal__merchant">{categoryText(proposal.category)}</span>
                  <span className="chip">{formatAmount(proposal.amount)} al mese</span>
                </p>
                <div className="card__actions">
                  <button
                    type="button"
                    className="button button--primary"
                    onClick={() => void decide(proposal.category, "accept")}
                  >
                    Accetta
                  </button>
                  <button
                    type="button"
                    className="button button--danger"
                    onClick={() => void decide(proposal.category, "dismiss")}
                  >
                    Scarta
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {assistant.history.length === 0 ? null : (
        <section className="panel">
          <h2 className="section-title">
            Letto finora <span className="count">{assistant.history.length}</span>
          </h2>
          <ul className="card-list">
            {assistant.history.map((entry) => (
              <li className="card" key={`${entry.created_at}-${entry.question}`}>
                <p className="proposal__head">
                  <span className="proposal__merchant">
                    {entry.question || "Lettura senza domanda"}
                  </span>
                  {entry.refused ? (
                    // The reason names the figure the model made up; that number
                    // is exactly what must not reach the screen.
                    <span className="chip chip--warning">rifiutata: citava una cifra non calcolata</span>
                  ) : null}
                </p>
                <p className="card__caption">
                  {entry.model} · {entry.created_at}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
