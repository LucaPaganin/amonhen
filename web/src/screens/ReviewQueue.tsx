import { useState } from "react";

import { api, errorMessage } from "../api";
import { CategoryPicker } from "../components/CategoryPicker";
import { TransactionRow } from "../components/TransactionRow";
import { TransferCard } from "../components/TransferCard";
import type { Category, ReviewState, Suggestion, SuggestionDecision, Transaction } from "../types";
import type { ReviewQueueController } from "../useReviewQueue";
import { useSuggestions } from "../useSuggestions";

interface ReviewQueueScreenProps {
  review: ReviewQueueController;
  categories: Category[];
  categoriesError: string | null;
  onReloadCategories: () => void;
}

/** The list filter, in the order the work usually gets done. */
const FILTER_CHIPS: { state: ReviewState | "all"; label: (review: ReviewQueueController) => string }[] = [
  { state: "all", label: (review) => `Tutte (${review.uncategorizedTotal})` },
  { state: "proposed", label: (review) => `Con proposta (${review.proposedTotal})` },
  { state: "unhandled", label: (review) => `Sfuggite (${review.unhandledTotal})` },
];

function reviewFlag(transaction: Transaction): { label: string; warning?: boolean } | undefined {
  if (transaction.review_state === "unhandled") {
    return { label: "sfuggita a regole, proposte e giroconti", warning: true };
  }
  if (transaction.proposed_category) {
    return { label: `proposta: ${transaction.proposed_category}` };
  }
  return undefined;
}

export function ReviewQueueScreen({
  review,
  categories,
  categoriesError,
  onReloadCategories,
}: ReviewQueueScreenProps) {
  const [pickerFor, setPickerFor] = useState<Transaction | null>(null);
  const [autoRunning, setAutoRunning] = useState(false);
  const [proposing, setProposing] = useState<"classifier" | "llm" | null>(null);
  const suggestions = useSuggestions();

  // What needs a decision: an automatic pass produced something and waits for a
  // yes or a no. The rest is backlog to work through, not a queue of decisions.
  const decisions = review.proposalsTotal + review.transfersTotal;
  const isEmpty =
    review.uncategorizedTotal === 0 &&
    review.transfersTotal === 0 &&
    review.proposalsTotal === 0 &&
    !review.loading &&
    !review.loadError;

  const runAutoCategorize = async () => {
    setAutoRunning(true);
    try {
      const result = await api.categorize();
      review.notify(
        result.applied > 0
          ? `${result.applied} movimenti categorizzati`
          : "Nessun movimento categorizzato automaticamente",
      );
      await review.reload();
    } catch (error) {
      review.notify(`Categorizzazione automatica non riuscita: ${errorMessage(error)}`);
    } finally {
      setAutoRunning(false);
    }
  };

  // `detail` from the backend is the whole message: for the model button a 503
  // carries the reason the LLM is unavailable (`errorMessage` returns it as-is).
  const runProposals = async (kind: "classifier" | "llm") => {
    if (proposing !== null) return;
    setProposing(kind);
    try {
      let message: string;
      if (kind === "classifier") {
        const { considered, recorded } = await api.propose();
        message =
          recorded > 0
            ? `${recorded} proposte su ${considered} merchant considerati`
            : `Nessuna proposta: ${considered} merchant considerati`;
      } else {
        const { recorded } = await api.llmSuggest();
        message = recorded > 0 ? `${recorded} proposte dal modello` : "Il modello non ha proposto nulla";
      }
      review.notify(message);
      await suggestions.reload();
    } catch (error) {
      review.notify(errorMessage(error));
    } finally {
      setProposing(null);
    }
  };

  const decideSuggestion = async (suggestion: Suggestion, decision: SuggestionDecision) => {
    const error = await suggestions.decide(suggestion, decision);
    if (error) {
      review.notify(`Proposta non registrata: ${error}`);
      return;
    }
    if (decision === "accept") {
      review.notify(`Regola salvata: ${suggestion.merchant} → ${suggestion.category}`);
      // The rule just categorized matching transactions, so the queue shrank.
      await review.reload();
    } else {
      review.notify(`Proposta rifiutata: ${suggestion.merchant}`);
    }
  };

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Da confermare</h1>
          <p className="screen__subtitle">
            {review.loading && decisions === 0
              ? "Caricamento…"
              : `${decisions} da decidere · ${review.uncategorizedTotal} senza categoria, di cui ${review.unhandledTotal} sfuggite`}
          </p>
        </div>
        <div className="screen__actions">
          <button
            type="button"
            className="button"
            onClick={() => void review.reload()}
            disabled={review.loading}
          >
            Aggiorna
          </button>
          <button
            type="button"
            className="button"
            onClick={() => void runAutoCategorize()}
            disabled={autoRunning}
          >
            {autoRunning ? "Categorizzo…" : "Categorizza"}
          </button>
        </div>
      </header>

      {review.loadError ? (
        <div className="state state--error" role="alert">
          <p>{review.loadError}</p>
          <button type="button" className="button" onClick={() => void review.reload()}>
            Riprova
          </button>
        </div>
      ) : null}

      {isEmpty ? <p className="state state--empty">Tutto in ordine: niente da confermare.</p> : null}

      <section className="panel">
        <h2 className="section-title">
          Proposte da confermare <span className="count">{suggestions.suggestions.length}</span>
        </h2>
        <div className="proposal-actions">
          <button
            type="button"
            className="button"
            onClick={() => void runProposals("classifier")}
            disabled={proposing !== null}
          >
            {proposing === "classifier" ? "Analizzo…" : "Proponi categorie"}
          </button>
          <button
            type="button"
            className="button"
            onClick={() => void runProposals("llm")}
            disabled={proposing !== null}
          >
            {proposing === "llm" ? "Chiedo al modello…" : "Chiedi al modello"}
          </button>
        </div>

        {suggestions.loadError ? (
          <div className="state state--error" role="alert">
            <p>Impossibile caricare le proposte: {suggestions.loadError}</p>
            <button type="button" className="button" onClick={() => void suggestions.reload()}>
              Riprova
            </button>
          </div>
        ) : suggestions.loading && suggestions.suggestions.length === 0 ? (
          <p className="state" aria-busy="true">
            Caricamento…
          </p>
        ) : suggestions.suggestions.length === 0 ? (
          <p className="state">
            Nessuna proposta in attesa. «Proponi categorie» interroga il classificatore statistico,
            «Chiedi al modello» il modello linguistico configurato.
          </p>
        ) : (
          <ul className="card-list">
            {suggestions.suggestions.map((suggestion) => (
              <li className="card proposal" key={suggestion.merchant}>
                <div className="proposal__head">
                  <span className="proposal__merchant">{suggestion.merchant}</span>
                  <span className="chip">{suggestion.category}</span>
                  <span className="proposal__source">
                    {suggestion.source === "llm" ? "modello" : "classificatore"}
                  </span>
                </div>
                <div className="card__actions">
                  <button
                    type="button"
                    className="button button--primary"
                    onClick={() => void decideSuggestion(suggestion, "accept")}
                  >
                    Accetta
                  </button>
                  <button
                    type="button"
                    className="button button--danger"
                    onClick={() => void decideSuggestion(suggestion, "dismiss")}
                  >
                    Rifiuta
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {!review.loadError && !isEmpty ? (
        <>
          <h2 className="section-title">
            Possibili giroconti <span className="count">{review.transfers.length}</span>
          </h2>
          {review.transfers.length === 0 ? (
            <p className="state">Nessun giroconto da confermare.</p>
          ) : (
            <ul className="card-list">
              {review.transfers.map((candidate) => (
                <TransferCard
                  key={`${candidate.leg_a.id}-${candidate.leg_b.id}`}
                  candidate={candidate}
                  onDecision={(decision) => void review.decideTransfer(candidate, decision)}
                />
              ))}
            </ul>
          )}
        </>
      ) : null}

      <section className="panel" hidden={review.uncategorizedTotal === 0}>
        <h2 className="section-title">
          Movimenti senza categoria <span className="count">{review.uncategorizedTotal}</span>
        </h2>

        <div className="filters">
          <div className="filters__chips" role="group" aria-label="Filtra i movimenti senza categoria">
            {FILTER_CHIPS.map((chip) => (
              <button
                key={chip.state}
                type="button"
                className={
                  review.filters.state === chip.state ? "chip chip--toggle chip--on" : "chip chip--toggle"
                }
                aria-pressed={review.filters.state === chip.state}
                onClick={() => review.setFilters({ state: chip.state })}
              >
                {chip.label(review)}
              </button>
            ))}
          </div>
          <input
            className="input"
            type="search"
            placeholder="Cerca nella descrizione…"
            aria-label="Cerca fra i movimenti senza categoria"
            value={review.filters.search}
            onChange={(event) => review.setFilters({ search: event.target.value })}
          />
          {review.accounts.length > 1 ? (
            <select
              className="input"
              aria-label="Filtra per conto"
              value={review.filters.accountId ?? ""}
              onChange={(event) =>
                review.setFilters({
                  accountId: event.target.value === "" ? null : Number(event.target.value),
                })
              }
            >
              <option value="">Tutti i conti</option>
              {review.accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          ) : null}
        </div>

        <p className="chart-note">
          «Sfuggite» sono le spese che nessuna regola ha categorizzato, per cui il classificatore non
          ha proposto nulla e che il riconoscimento dei giroconti non ha appaiato: sono le uniche che
          restano da smistare a mano.
        </p>

        {review.uncategorized.length === 0 ? (
          <p className="state">
            {review.filters.state === "unhandled" && review.unhandledTotal === 0
              ? "Nessuna spesa è sfuggita: regole, proposte e giroconti le hanno prese tutte."
              : "Nessun movimento con questo filtro."}
          </p>
        ) : (
          <ul className="txn-list">
            {review.uncategorized.map((transaction) => (
              <TransactionRow
                key={transaction.id}
                transaction={transaction}
                onSelect={setPickerFor}
                flag={reviewFlag(transaction)}
              />
            ))}
          </ul>
        )}
      </section>

      <CategoryPicker
        open={pickerFor !== null}
        title={pickerFor ? `Categorizza «${pickerFor.merchant ?? pickerFor.description}»` : ""}
        merchant={pickerFor?.merchant ?? null}
        transaction={pickerFor}
        categories={categories}
        categoriesError={categoriesError}
        onReloadCategories={onReloadCategories}
        onCreateCategory={async (name) => {
          await api.createCategory(name);
          await onReloadCategories();
        }}
        onSaveSplits={async (splits) => {
          const transaction = pickerFor;
          if (!transaction) return;
          await api.setSplits(transaction.id, splits);
          setPickerFor(null);
          await review.reload();
        }}
        onSelect={(category, options) => {
          const transaction = pickerFor;
          setPickerFor(null);
          if (transaction) void review.categorize(transaction, category, options);
        }}
        onClose={() => setPickerFor(null)}
      />
    </section>
  );
}
