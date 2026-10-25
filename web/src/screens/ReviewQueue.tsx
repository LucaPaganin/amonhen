import { useEffect, useId, useRef, useState } from "react";

import { api, errorMessage } from "../api";
import { deletionNotice } from "../notices";
import { CategoryPicker } from "../components/CategoryPicker";
import { RuleSheet, merchantDraft } from "../components/RuleSheet";
import { TransactionRow } from "../components/TransactionRow";
import { TransferCard } from "../components/TransferCard";
import { bucketName } from "../category";
import { formatAmount, formatDate } from "../format";
import type {
  Category,
  ReviewState,
  RuleDraft,
  Suggestion,
  SuggestionDecision,
  Transaction,
} from "../types";
import type { ReviewQueueController } from "../useReviewQueue";
import { useSuggestions } from "../useSuggestions";

interface ReviewQueueScreenProps {
  review: ReviewQueueController;
  categories: Category[];
  categoriesError: string | null;
  onReloadCategories: () => void;
  /** Writes a rule; answers the error to show in its sheet, or null once saved. */
  onSaveRule: (draft: RuleDraft) => Promise<string | null>;
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

/** The select's last option: it opens the field that makes a category. */
const NEW_CATEGORY = "__new__";

/**
 * What a yes would settle. A proposal is about a merchant, not about one
 * movement, so there is no single amount to show: the queue says how much is
 * waiting, over how many movements, and when they ran — which is what tells a
 * habit from the tail of something already decided.
 */
function stakeText(stake: Suggestion["stake"]): string {
  const { movements, total, first_date: first, last_date: last } = stake;
  if (movements === 0 || first === null || last === null) {
    // Nothing the acceptance could settle: the row may be a split, whose parts
    // are decided by opening it, or a merchant whose money is already decided.
    return "Nessun movimento in attesa che un sì possa decidere.";
  }
  if (movements === 1) return `${formatAmount(total)} · speso il ${formatDate(last)}`;
  const span = first === last ? `il ${formatDate(last)}` : `dal ${formatDate(first)} al ${formatDate(last)}`;
  return `${formatAmount(total)} in ${movements} movimenti · ${span}`;
}

export function ReviewQueueScreen({
  review,
  categories,
  categoriesError,
  onReloadCategories,
  onSaveRule,
}: ReviewQueueScreenProps) {
  const [pickerFor, setPickerFor] = useState<Transaction | null>(null);
  const [movementRule, setMovementRule] = useState<{ transaction: Transaction; category: string } | null>(
    null,
  );
  const [autoRunning, setAutoRunning] = useState(false);
  const [proposing, setProposing] = useState<"classifier" | "llm" | null>(null);
  const suggestions = useSuggestions();

  // What a person may pick instead of the proposal. The review bucket is not a
  // category a rule may point at, so it is not a choice here.
  const categoryOptions = categories.filter((item) => item.name !== bucketName());
  const [chosen, setChosen] = useState<Record<string, string>>({});
  // Quale proposta sta nel dettaglio: il clic la sceglie, e la prima è scelta da
  // sé, così il pannello non è mai un riquadro vuoto che aspetta un gesto.
  const [selected, setSelected] = useState<string | null>(null);
  const active =
    suggestions.suggestions.find((item) => item.merchant === selected) ??
    suggestions.suggestions[0] ??
    null;
  const activeChoice = active === null ? "" : (chosen[active.merchant] ?? active.category);
  const [newFor, setNewFor] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  // Se una regola nasce da un'accettazione lo decide la casella, che è spenta di
  // default: una regola per ogni proposta accettata è una regola per ogni modo in
  // cui una banca stampa lo stesso esercente, e le regole si contano in Categorie.
  const [withRule, setWithRule] = useState<Record<string, boolean>>({});
  // La proposta che aspetta la sua regola: il dialogo si apre qui, e il testo si
  // edita prima di scriverlo, perché è quello che deciderà i movimenti prossimi.
  const [ruleFor, setRuleFor] = useState<{ suggestion: Suggestion; category: string } | null>(null);
  const [ruleText, setRuleText] = useState("");
  const [savingRule, setSavingRule] = useState(false);
  const ruleDialogRef = useRef<HTMLDialogElement>(null);
  const ruleFieldId = useId();

  // Il dialogo è montato solo mentre c'è una regola da scrivere, quindi si apre
  // appena arriva: `showModal` porta con sé l'Esc, il backdrop e la trappola del
  // fuoco, che è la stessa forma dei fogli dell'app.
  useEffect(() => {
    if (ruleFor !== null && !ruleDialogRef.current?.open) ruleDialogRef.current?.showModal();
  }, [ruleFor]);

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

  // Che cosa una decisione ha fatto: la categoria, la regola se è stata scritta,
  // e quanti movimenti tiene. Il dialogo resta aperto quando il ledger rifiuta il
  // testo della regola — il testo scritto non si perde — quindi il chiamante sa
  // se la decisione è stata registrata.
  const recordDecision = async (
    suggestion: Suggestion,
    decision: SuggestionDecision,
    options: { category?: string; rule?: string } = {},
  ): Promise<boolean> => {
    const { error, outcome } = await suggestions.decide(suggestion, decision, options);
    if (error !== null) {
      review.notify(`Proposta non registrata: ${error}`);
      return false;
    }
    if (decision === "dismiss") {
      review.notify(`Proposta rifiutata: ${suggestion.merchant}`);
      return true;
    }
    const decided = outcome?.movements ?? 0;
    const movements = decided === 1 ? "1 movimento" : `${decided} movimenti`;
    review.notify(
      outcome?.rule
        ? `Regola salvata: ${outcome.rule} → ${outcome.category} · ${movements}`
        : `Categoria salvata: ${outcome?.category} · ${movements}`,
    );
    // The movements the decision covered left the queue, so it is read again.
    await review.reload();
    return true;
  };

  /** Il dito sul pulsante della proposta: decide, o apre prima la sua regola. */
  const acceptSuggestion = (suggestion: Suggestion, category: string) => {
    if (withRule[suggestion.merchant]) {
      setRuleText(suggestion.merchant);
      setRuleFor({ suggestion, category });
      return;
    }
    void recordDecision(suggestion, "accept", { category });
  };

  const closeRuleDialog = () => {
    setRuleFor(null);
    setRuleText("");
  };

  const saveRule = async () => {
    if (ruleFor === null || savingRule) return;
    const text = ruleText.trim();
    if (text === "") return;
    setSavingRule(true);
    const recorded = await recordDecision(ruleFor.suggestion, "accept", {
      category: ruleFor.category,
      rule: text,
    });
    if (recorded) closeRuleDialog();
    setSavingRule(false);
  };

  // The right answer for a merchant may be a category that does not exist yet.
  // Making it here leaves it already chosen for that proposal.
  const createCategory = async (suggestion: Suggestion) => {
    const name = newName.trim();
    if (name === "" || creating) return;
    setCreating(true);
    try {
      await api.createCategory(name);
      await onReloadCategories();
      setChosen((current) => ({ ...current, [suggestion.merchant]: name }));
      setNewFor(null);
      setNewName("");
    } catch (error) {
      review.notify(`Categoria non creata: ${errorMessage(error)}`);
    } finally {
      setCreating(false);
    }
  };

  // I comandi di una proposta: la casella che decide se nasce una regola, la
  // scelta della categoria e il pulsante che la conferma, con il campo che ne
  // crea una nuova. Sono gli stessi dentro la scheda (dove li usa il telefono) e
  // nel dettaglio (dove li usa la finestra), quindi si scrivono una volta e il
  // foglio spegne il posto che non serve. Il posto entra negli id perché le due
  // copie stanno nello stesso documento, e un id ripetuto manda l'etichetta al
  // campo sbagliato.
  const proposalControls = (suggestion: Suggestion, place: "card" | "detail") => {
    const choice = chosen[suggestion.merchant] ?? suggestion.category;
    const rejecting = choice === "";
    const wantsRule = Boolean(withRule[suggestion.merchant]);
    return (
      <>
        {rejecting ? null : (
          <label className="rule-toggle" htmlFor={`rule-${place}-${suggestion.merchant}`}>
            <input
              id={`rule-${place}-${suggestion.merchant}`}
              type="checkbox"
              checked={wantsRule}
              onChange={(event) =>
                setWithRule((current) => ({
                  ...current,
                  [suggestion.merchant]: event.target.checked,
                }))
              }
            />
            <span>Crea una regola per «{suggestion.merchant}»</span>
          </label>
        )}
        <div className="card__actions">
          <select
            className="input"
            aria-label={`Categoria per ${suggestion.merchant}`}
            value={choice}
            disabled={categoryOptions.length === 0}
            onChange={(event) =>
              event.target.value === NEW_CATEGORY
                ? setNewFor(suggestion.merchant)
                : setChosen({ ...chosen, [suggestion.merchant]: event.target.value })
            }
          >
            {categoryOptions.map((item) => (
              <option key={item.id} value={item.name}>
                {item.name}
              </option>
            ))}
            <option value="">Nessuna categoria: rifiuta la proposta</option>
            <option value={NEW_CATEGORY}>Nuova categoria…</option>
          </select>
          <button
            type="button"
            className={rejecting ? "button button--danger" : "button button--primary"}
            onClick={() => {
              if (rejecting) {
                void recordDecision(suggestion, "dismiss");
              } else {
                acceptSuggestion(suggestion, choice);
              }
            }}
          >
            {rejecting ? "Rifiuta" : "Accetta"}
          </button>
        </div>
        {newFor === suggestion.merchant ? (
          <form
            className="proposal__new"
            onSubmit={(event) => {
              event.preventDefault();
              void createCategory(suggestion);
            }}
          >
            <label className="visually-hidden" htmlFor={`new-${place}-${suggestion.merchant}`}>
              Nome della nuova categoria
            </label>
            <input
              id={`new-${place}-${suggestion.merchant}`}
              className="input"
              type="text"
              autoComplete="off"
              placeholder="Nome della categoria"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              autoFocus
            />
            <button
              type="submit"
              className="button button--primary"
              disabled={newName.trim() === "" || creating}
            >
              {creating ? "Creo…" : "Crea"}
            </button>
          </form>
        ) : null}
      </>
    );
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

      <section className="panel panel--split">
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
            {suggestions.suggestions.map((suggestion) => {
              // La scheda scelta è quella che il dettaglio mostra. Il fuoco la
              // sceglie, e la scheda è un fermo di tabulazione apposta: sopra i
              // 1024 i suoi comandi stanno nel dettaglio, quindi senza questo
              // fermo una tastiera non avrebbe modo di cambiare proposta.
              return (
                <li
                  className="card proposal"
                  key={suggestion.merchant}
                  tabIndex={0}
                  aria-current={suggestion.merchant === active?.merchant ? "true" : undefined}
                  onClick={() => setSelected(suggestion.merchant)}
                  onFocus={() => setSelected(suggestion.merchant)}
                >
                  <div className="proposal__head">
                    <span className="proposal__merchant">{suggestion.merchant}</span>
                    <span className="chip">{suggestion.category}</span>
                    <span className="proposal__source">
                      {suggestion.source === "llm" ? "modello" : "classificatore"}
                    </span>
                  </div>
                  <p className="chart-note">{stakeText(suggestion.stake)}</p>
                  <div className="proposal__controls">{proposalControls(suggestion, "card")}</div>
                </li>
              );
            })}
          </ul>
        )}

        {/* Il dettaglio della proposta scelta. Sopra i 1024 sta accanto
            all'elenco (`.panel--split`); sotto non c'è, perché su un telefono la
            scheda è già il dettaglio. Dice cosa quella riga vale e cosa fa
            accettarla, così la coda resta il posto dove si decide senza aprire
            niente. */}
        <aside className="queue-detail">
          {active === null ? (
            <p className="state">Nessuna proposta da guardare.</p>
          ) : (
            <>
              <p className="queue-detail__merchant">{active.merchant}</p>
              <p className="hint">
                {active.source === "llm" ? "proposta dal modello" : "proposta dal classificatore"}
              </p>
              <p className="queue-detail__choice">
                <span className="chip">{activeChoice === "" ? "nessuna categoria" : activeChoice}</span>
              </p>
              <p className="chart-note">{stakeText(active.stake)}</p>
              <p className="hint">
                {activeChoice === ""
                  ? "Rifiutarla lascia il merchant senza categoria e fuori dalla coda."
                  : `Accettarla assegna «${activeChoice}» ai movimenti in attesa; la regola si scrive solo se la chiedi.`}
              </p>
              <div className="queue-detail__controls">{proposalControls(active, "detail")}</div>
            </>
          )}
        </aside>
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
        onSaveNotes={async (notes) => {
          const transaction = pickerFor;
          if (!transaction) return;
          await api.setNotes(transaction.id, notes);
          // The queue is the server's to rebuild, so a note is written and the
          // page is fetched again rather than patched here.
          await review.reload();
        }}
        onDelete={async () => {
          const transaction = pickerFor;
          if (!transaction) return;
          const deleted = await api.deleteTransaction(transaction.id);
          setPickerFor(null);
          review.notify(deletionNotice(deleted));
          await review.reload();
        }}
        onSelect={(category, options) => {
          const transaction = pickerFor;
          setPickerFor(null);
          if (!transaction) return;
          // The rule's text is written before anything is saved: it decides the
          // movements the bank has not printed yet, so it is not just the merchant.
          if (options.rule) setMovementRule({ transaction, category });
          else void review.categorize(transaction, category);
        }}
        onClose={() => setPickerFor(null)}
      />

      {movementRule === null ? null : (
        <RuleSheet
          title={`Una regola da «${movementRule.transaction.merchant ?? movementRule.transaction.description}»`}
          initial={merchantDraft(
            movementRule.transaction.merchant ?? movementRule.transaction.description,
            movementRule.category,
          )}
          categories={categories}
          onSave={async (draft) => {
            const asked = movementRule;
            const message = await onSaveRule(draft);
            if (message !== null) return message;
            setMovementRule(null);
            if (draft.action === "category" && draft.target) {
              await review.categorize(asked.transaction, draft.target);
            }
            review.notify(`Regola salvata: «${draft.pattern}»`);
            await review.reload();
            return null;
          }}
          onClose={() => setMovementRule(null)}
        />
      )}

      {/* La regola che sta per nascere, prima che nasca: il testo è quello che
          deciderà ogni movimento che la banca stamperà dopo, quindi si scrive qui
          invece di essere il nome del merchant, ed è editabile. Annullare non
          lascia niente a metà: la proposta resta in coda e i movimenti restano
          dov'erano. */}
      {ruleFor === null ? null : (
        <dialog
          ref={ruleDialogRef}
          className="sheet"
          aria-labelledby={`${ruleFieldId}-title`}
          onCancel={(event) => {
            event.preventDefault();
            closeRuleDialog();
          }}
          onClose={closeRuleDialog}
          onClick={(event) => {
            if (event.target === ruleDialogRef.current) closeRuleDialog();
          }}
        >
          <div className="sheet__panel">
            <header className="sheet__header">
              <h2 className="sheet__title" id={`${ruleFieldId}-title`}>
                La regola per «{ruleFor.suggestion.merchant}»
              </h2>
              <button
                type="button"
                className="button button--ghost"
                onClick={closeRuleDialog}
                aria-label="Chiudi"
              >
                ✕
              </button>
            </header>
            <form
              className="sheet__new"
              onSubmit={(event) => {
                event.preventDefault();
                void saveRule();
              }}
            >
              <label className="sheet__new-label" htmlFor={ruleFieldId}>
                Testo della regola
              </label>
              <input
                id={ruleFieldId}
                className="input"
                type="text"
                value={ruleText}
                autoComplete="off"
                onChange={(event) => setRuleText(event.target.value)}
              />
              <p className="hint">
                Vale per ogni movimento la cui descrizione contiene questo testo, senza badare alle
                maiuscole; fra barre è un&apos;espressione regolare —{" "}
                <code>/amazon (eu|payments)/</code> prende una famiglia che la banca scrive in
                troppi modi. La regola assegna «{ruleFor.category}», come la categoria scelta qui
                accanto.
              </p>
              <div className="card__actions">
                <button
                  type="submit"
                  className="button button--primary"
                  disabled={savingRule || ruleText.trim() === ""}
                >
                  {savingRule ? "Salvo…" : "Accetta e crea la regola"}
                </button>
                <button type="button" className="button" onClick={closeRuleDialog} disabled={savingRule}>
                  Annulla
                </button>
              </div>
            </form>
          </div>
        </dialog>
      )}
    </section>
  );
}
