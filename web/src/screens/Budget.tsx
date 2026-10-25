import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { MouseEvent } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { categoryText } from "../category";
import { Toast } from "../components/Toast";
import { currentMonth, formatAmount, formatDate, formatMonth, monthBounds, shiftMonth } from "../format";
import type {
  AssistantContext,
  Budget,
  BudgetItem,
  BudgetItemDraft,
  BudgetPriority,
  Transaction,
} from "../types";

interface BudgetScreenProps {
  /** Opens the assistant on one budget: the question is composed at that row. */
  onAskAssistant: (context: AssistantContext) => void;
  /** Bumped after a sync: what was spent is read again. */
  refreshToken: number;
}

const PRIORITY_LABELS: Record<BudgetPriority, string> = {
  essential: "Essenziale",
  important: "Importante",
  deferrable: "Rimandabile",
};

const PRIORITIES: BudgetPriority[] = ["essential", "important", "deferrable"];

/** How many past movements the search offers to copy from. */
const SEARCH_LIMIT = 8;

/** An amount a person typed: positive, at most two decimals, comma or point. */
function isPositiveAmount(value: string): boolean {
  const normalized = value.trim().replace(",", ".");
  return /^\d+(\.\d{1,2})?$/.test(normalized) && Number(normalized) > 0;
}

/** The same day of the month in another month, clipped to its last day. */
function moveDay(iso: string, month: string): string {
  const last = Number(monthBounds(month).to.slice(8, 10));
  const day = Math.min(Number(iso.slice(8, 10)), last);
  return `${month}-${String(day).padStart(2, "0")}`;
}

/** What the ceiling says, in one line: the budget, and whether the month holds. */
function ceilingLine(budget: Budget): string {
  if (budget.budget === null) return "Nessun budget impostato";
  const origin = budget.override !== null ? "solo questo mese" : "dal default";
  const remaining = Number.parseFloat(budget.remaining ?? "0");
  const state =
    remaining < 0
      ? `sforato di ${formatAmount(-remaining)}`
      : `restano ${formatAmount(budget.remaining ?? "0")}`;
  return `Budget ${formatAmount(budget.budget)} (${origin}) · ${state}`;
}

/** What the items take of the ceiling; nothing when there are none. */
function planLine(budget: Budget): string | null {
  if (budget.items.length === 0) return null;
  if (budget.free === null) return `Pianificato ${formatAmount(budget.planned)} · nessun budget`;
  if (budget.over_plan) {
    return `Pianificato ${formatAmount(budget.planned)} · le voci superano il budget di ${formatAmount(
      -Number.parseFloat(budget.free),
    )}`;
  }
  return `Pianificato ${formatAmount(budget.planned)} · liberi ${formatAmount(budget.free)}`;
}

interface ItemSheetState {
  /** The item being edited; null for a new one. */
  item: BudgetItem | null;
  categoryId: number;
}

interface BudgetItemSheetProps {
  state: ItemSheetState | null;
  month: string;
  budgets: Budget[];
  onClose: () => void;
  onSave: (draft: BudgetItemDraft, item: BudgetItem | null) => Promise<string | null>;
  onDelete: (item: BudgetItem) => Promise<string | null>;
}

/**
 * A planned expense, new or edited. A new one may start from a past movement:
 * the search copies its description, amount and category into the fields and
 * moves its day into the month being planned, and nothing is saved until the
 * person has read them. An edit may move the item to another month or category.
 */
function BudgetItemSheet({ state, month, budgets, onClose, onSave, onDelete }: BudgetItemSheetProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const fieldId = useId();
  const [categoryId, setCategoryId] = useState(0);
  const [itemMonth, setItemMonth] = useState(month);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState("");
  const [priority, setPriority] = useState<BudgetPriority>("important");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<Transaction[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);

  const open = state !== null;
  const editing = state?.item ?? null;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (state !== null && !dialog.open) {
      setCategoryId(state.categoryId);
      setItemMonth(month);
      setDescription(editing?.description ?? "");
      setAmount(editing?.amount ?? "");
      setDate(editing?.date ?? "");
      setPriority(editing?.priority ?? "important");
      setNote(editing?.note ?? "");
      setError(null);
      setSearch("");
      setResults([]);
      setSearchError(null);
      dialog.showModal();
    } else if (state === null && dialog.open) {
      dialog.close();
    }
  }, [state, editing, month]);

  // The search runs as it is typed, and only a new item offers it: an edit
  // already has its fields.
  useEffect(() => {
    if (!open || editing !== null || search.trim().length < 2) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .transactions({ search: search.trim(), limit: SEARCH_LIMIT }, controller.signal)
        .then((page) => {
          setResults(page.items.filter((row) => row.amount.startsWith("-")));
          setSearchError(null);
        })
        .catch((caught: unknown) => {
          if (!isAbortError(caught)) setSearchError(errorMessage(caught));
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [open, editing, search]);

  const handleBackdropClick = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === dialogRef.current) onClose();
  };

  const copyFrom = (row: Transaction) => {
    setDescription(row.merchant ?? row.description);
    setAmount(row.amount.replace(/^-/, ""));
    setDate(moveDay(row.date, itemMonth));
    const category = budgets.find((budget) => budget.category === row.category);
    if (category !== undefined) setCategoryId(category.id);
    setSearch("");
    setResults([]);
  };

  // Moving an item to another month carries its day along, so the date never
  // falls outside the month it belongs to.
  const changeMonth = (value: string) => {
    if (value === "") return;
    setItemMonth(value);
    if (date !== "") setDate(moveDay(date, value));
  };

  const bounds = monthBounds(itemMonth);
  const valid =
    description.trim() !== "" && isPositiveAmount(amount) && categoryId > 0 && itemMonth !== "";

  const submit = async () => {
    if (!valid || saving) return;
    setSaving(true);
    setError(null);
    const message = await onSave(
      {
        category_id: categoryId,
        month: itemMonth,
        description: description.trim(),
        amount: amount.trim().replace(",", "."),
        date: date === "" ? null : date,
        priority,
        note: note.trim() === "" ? null : note.trim(),
      },
      editing,
    );
    setSaving(false);
    if (message !== null) {
      setError(message);
      return;
    }
    onClose();
  };

  const remove = async () => {
    if (editing === null || saving) return;
    setSaving(true);
    const message = await onDelete(editing);
    setSaving(false);
    if (message !== null) {
      setError(message);
      return;
    }
    onClose();
  };

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
            {editing === null ? "Nuova voce" : "Modifica voce"}
          </h2>
          <button type="button" className="button button--ghost" onClick={onClose} aria-label="Chiudi">
            ✕
          </button>
        </header>

        {editing === null ? (
          <div className="field budget-copy">
            <label htmlFor={`${fieldId}-search`}>Copia da un movimento passato</label>
            <input
              id={`${fieldId}-search`}
              className="input"
              type="search"
              placeholder="Cerca per descrizione"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            {searchError !== null ? (
              <p className="account-form__error" role="alert">
                Ricerca non riuscita: {searchError}
              </p>
            ) : null}
            {results.length > 0 ? (
              <ul className="sheet__list budget-copy__results">
                {results.map((row) => (
                  <li key={row.id}>
                    <button type="button" className="sheet__option budget-copy__option" onClick={() => copyFrom(row)}>
                      <span className="budget-copy__name">{row.merchant ?? row.description}</span>
                      <span className="budget-copy__meta">
                        {formatDate(row.date)} · {formatAmount(row.amount)} · {categoryText(row.category)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <form
          className="account-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="field">
            <label htmlFor={`${fieldId}-description`}>Descrizione</label>
            <input
              id={`${fieldId}-description`}
              className="input"
              type="text"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-amount`}>Importo</label>
            <input
              id={`${fieldId}-amount`}
              className="input"
              type="text"
              inputMode="decimal"
              placeholder="0,00"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-category`}>Categoria</label>
            <select
              id={`${fieldId}-category`}
              className="input"
              value={categoryId}
              onChange={(event) => setCategoryId(Number(event.target.value))}
            >
              {budgets.map((budget) => (
                <option key={budget.id} value={budget.id}>
                  {categoryText(budget.category)}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-priority`}>Priorità</label>
            <select
              id={`${fieldId}-priority`}
              className="input"
              value={priority}
              onChange={(event) => setPriority(event.target.value as BudgetPriority)}
            >
              {PRIORITIES.map((value) => (
                <option key={value} value={value}>
                  {PRIORITY_LABELS[value]}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-month`}>Mese</label>
            <input
              id={`${fieldId}-month`}
              className="input"
              type="month"
              value={itemMonth}
              onChange={(event) => changeMonth(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-date`}>Data (facoltativa)</label>
            <input
              id={`${fieldId}-date`}
              type="date"
              min={bounds.from}
              max={bounds.to}
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-note`}>Nota</label>
            <input
              id={`${fieldId}-note`}
              className="input"
              type="text"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>

          {error !== null ? (
            <p className="account-form__error" role="alert">
              {error}
            </p>
          ) : null}

          <div className="account-form__actions">
            <button type="submit" className="button button--primary" disabled={!valid || saving}>
              {saving ? "Salvo…" : editing === null ? "Aggiungi" : "Salva"}
            </button>
            <button type="button" className="button" onClick={onClose}>
              Annulla
            </button>
            {editing !== null ? (
              <button type="button" className="button button--danger" disabled={saving} onClick={() => void remove()}>
                Elimina
              </button>
            ) : null}
          </div>
        </form>
      </div>
    </dialog>
  );
}

export function BudgetScreen({ onAskAssistant, refreshToken }: BudgetScreenProps) {
  const [month, setMonth] = useState(currentMonth);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingBudget, setEditingBudget] = useState<number | null>(null);
  const [budgetDraft, setBudgetDraft] = useState("");
  const [pending, setPending] = useState<number | null>(null);
  const [sheet, setSheet] = useState<ItemSheetState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async (value: string, signal?: AbortSignal) => {
    setLoading(true);
    try {
      setBudgets(await api.budgets(value, signal));
      setError(null);
    } catch (caught) {
      if (isAbortError(caught)) return;
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(month, controller.signal);
    return () => controller.abort();
  }, [load, month, refreshToken]);

  // Every budget write answers with the month again, so a write is a request
  // and a replacement of the list, never an adjustment made here.
  const write = async (budget: Budget, request: () => Promise<Budget[]>, done: string) => {
    if (pending !== null) return;
    setPending(budget.id);
    try {
      setBudgets(await request());
      setEditingBudget(null);
      setNotice(done);
    } catch (caught) {
      setNotice(`Budget non salvato: ${errorMessage(caught)}`);
    } finally {
      setPending(null);
    }
  };

  const draftAmount = (): string | null => {
    const value = budgetDraft.trim().replace(",", ".");
    if (!/^\d+(\.\d{1,2})?$/.test(value)) {
      setNotice("Importo non valido: usa cifre e al massimo due decimali.");
      return null;
    }
    return value;
  };

  const saveDefault = (budget: Budget) => {
    const amount = draftAmount();
    if (amount === null) return;
    void write(
      budget,
      () => api.setBudget(budget.id, amount, month),
      `Budget di ${categoryText(budget.category)} salvato da ${formatMonth(month)} in poi`,
    );
  };

  const saveOverride = (budget: Budget) => {
    const amount = draftAmount();
    if (amount === null) return;
    void write(
      budget,
      () => api.setBudgetOverride(budget.id, amount, month),
      `Budget di ${categoryText(budget.category)} salvato solo per ${formatMonth(month)}`,
    );
  };

  const copyPrevious = async (budget: Budget) => {
    if (pending !== null) return;
    setPending(budget.id);
    const previous = shiftMonth(month, -1);
    try {
      const answer = await api.copyBudgetItems(budget.id, previous, month);
      setBudgets(answer.budgets);
      setNotice(
        answer.copied === 0
          ? `Niente da copiare da ${formatMonth(previous)}`
          : `${answer.copied} ${answer.copied === 1 ? "voce copiata" : "voci copiate"} da ${formatMonth(previous)}`,
      );
    } catch (caught) {
      setNotice(`Voci non copiate: ${errorMessage(caught)}`);
    } finally {
      setPending(null);
    }
  };

  const saveItem = async (draft: BudgetItemDraft, item: BudgetItem | null): Promise<string | null> => {
    try {
      if (item === null) {
        // A new item answers with the month it was planned for, which may not
        // be the one on screen: then the screen's month is read again.
        const answer = await api.createBudgetItem(draft);
        setBudgets(draft.month === month ? answer : await api.budgets(month));
      } else {
        setBudgets(await api.updateBudgetItem(item.id, draft, month));
      }
      // An item saved into another month leaves this list; the notice says where it went.
      const elsewhere = draft.month !== month ? ` in ${formatMonth(draft.month)}` : "";
      setNotice(item === null ? `Voce aggiunta${elsewhere}` : `Voce salvata${elsewhere}`);
      return null;
    } catch (caught) {
      return errorMessage(caught);
    }
  };

  const deleteItem = async (item: BudgetItem): Promise<string | null> => {
    try {
      setBudgets(await api.deleteBudgetItem(item.id));
      setNotice(`Voce eliminata: ${item.description}`);
      return null;
    } catch (caught) {
      return errorMessage(caught);
    }
  };

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Budget</h1>
          <p className="screen__subtitle">
            Quanto vuoi spendere in un mese per ogni categoria, e le spese che sai già di dover fare.
          </p>
        </div>
      </header>

      <section className="panel">
        <h2 className="section-title">
          Budget <span className="count">{formatMonth(month)}</span>
        </h2>
        <div className="month-picker">
          <button
            type="button"
            className="button"
            onClick={() => setMonth(shiftMonth(month, -1))}
            aria-label="Mese precedente"
          >
            ‹
          </button>
          <label className="visually-hidden" htmlFor="budget-month">
            Mese
          </label>
          <input
            id="budget-month"
            className="month-picker__input"
            type="month"
            value={month}
            onChange={(event) => {
              if (event.target.value !== "") setMonth(event.target.value);
            }}
          />
          <button
            type="button"
            className="button"
            onClick={() => setMonth(shiftMonth(month, 1))}
            aria-label="Mese successivo"
          >
            ›
          </button>
        </div>
        <p className="hint">
          Un budget salvato «da questo mese» vale anche per i mesi dopo, e lascia i mesi prima come
          erano. Le voci stanno dentro il budget: in cima le essenziali, e quelle che non ci stanno più
          sono segnate.
        </p>
        {error !== null ? (
          <div className="state state--error" role="alert">
            <p>Impossibile caricare i budget: {error}</p>
            <button type="button" className="button" onClick={() => void load(month)}>
              Riprova
            </button>
          </div>
        ) : loading && budgets.length === 0 ? (
          <p className="state" aria-busy="true">
            Caricamento…
          </p>
        ) : budgets.length === 0 ? (
          <p className="state">Nessuna categoria su cui impostare un budget.</p>
        ) : (
          <ul className="budget-list">
            {budgets.map((budget) => {
              const remaining = budget.remaining === null ? null : Number.parseFloat(budget.remaining);
              const over = (remaining !== null && remaining < 0) || budget.over_plan;
              const editing = editingBudget === budget.id;
              const busy = pending === budget.id;
              const plan = planLine(budget);
              return (
                <li className={over ? "budget-row budget-row--over" : "budget-row"} key={budget.id}>
                  <div className="budget-row__head">
                    <span className="budget-row__name">{categoryText(budget.category)}</span>
                    <span className="budget-row__spent">{formatAmount(budget.spent)} spesi</span>
                  </div>
                  <p className="budget-row__status">{ceilingLine(budget)}</p>
                  {plan !== null ? (
                    <p className={budget.over_plan ? "budget-row__status budget-row__over" : "budget-row__status"}>
                      {plan}
                    </p>
                  ) : null}
                  {budget.items.length > 0 ? (
                    <ul className="budget-items">
                      {budget.items.map((item) => (
                        <li key={item.id}>
                          <button
                            type="button"
                            className={item.fits === false ? "budget-item budget-item--out" : "budget-item"}
                            onClick={() => setSheet({ item, categoryId: budget.id })}
                            aria-label={`Modifica ${item.description}`}
                          >
                            <span className="budget-item__text">
                              <span className="budget-item__name">{item.description}</span>
                              <span className="budget-item__meta">
                                <span className={`chip chip--priority-${item.priority}`}>
                                  {PRIORITY_LABELS[item.priority]}
                                </span>
                                {item.date !== null ? <span>{formatDate(item.date)}</span> : null}
                                {item.fits === false ? <span className="chip chip--warning">Non ci sta</span> : null}
                                {item.note !== null ? <span className="budget-item__note">{item.note}</span> : null}
                              </span>
                            </span>
                            <span className="budget-item__amount">{formatAmount(item.amount)}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {editing ? (
                    <form
                      className="budget-editor"
                      onSubmit={(event) => {
                        event.preventDefault();
                        saveDefault(budget);
                      }}
                    >
                      <label className="visually-hidden" htmlFor={`budget-${budget.id}`}>
                        Budget mensile per {categoryText(budget.category)}
                      </label>
                      <input
                        id={`budget-${budget.id}`}
                        className="input"
                        type="text"
                        inputMode="decimal"
                        placeholder="0,00"
                        value={budgetDraft}
                        onChange={(event) => setBudgetDraft(event.target.value)}
                        autoFocus
                      />
                      <div className="budget-editor__actions">
                        <button
                          type="submit"
                          className="button button--primary"
                          disabled={busy || budgetDraft.trim() === ""}
                        >
                          Da questo mese in poi
                        </button>
                        <button
                          type="button"
                          className="button"
                          disabled={busy || budgetDraft.trim() === ""}
                          onClick={() => saveOverride(budget)}
                        >
                          Solo questo mese
                        </button>
                        {budget.override !== null ? (
                          <button
                            type="button"
                            className="button"
                            disabled={busy}
                            onClick={() =>
                              void write(
                                budget,
                                () => api.setBudgetOverride(budget.id, null, month),
                                `${formatMonth(month)} torna al budget di default`,
                              )
                            }
                          >
                            Torna al default
                          </button>
                        ) : null}
                        {budget.default !== null ? (
                          <button
                            type="button"
                            className="button button--danger"
                            disabled={busy}
                            onClick={() =>
                              void write(
                                budget,
                                () => api.setBudget(budget.id, null, month),
                                `Budget di ${categoryText(budget.category)} rimosso da ${formatMonth(month)} in poi`,
                              )
                            }
                          >
                            Rimuovi da questo mese
                          </button>
                        ) : null}
                        <button type="button" className="button" onClick={() => setEditingBudget(null)}>
                          Annulla
                        </button>
                      </div>
                    </form>
                  ) : (
                    <div className="budget-row__actions">
                      <button
                        type="button"
                        className="button"
                        onClick={() => {
                          setEditingBudget(budget.id);
                          setBudgetDraft(budget.budget ?? "");
                        }}
                      >
                        {budget.budget === null ? "Imposta budget" : "Modifica budget"}
                      </button>
                      <button
                        type="button"
                        className="button"
                        onClick={() => setSheet({ item: null, categoryId: budget.id })}
                      >
                        Aggiungi voce
                      </button>
                      <button
                        type="button"
                        className="button"
                        disabled={busy}
                        onClick={() => void copyPrevious(budget)}
                      >
                        Copia dal mese prima
                      </button>
                      {budget.budget === null ? null : (
                        <button
                          type="button"
                          className="button"
                          onClick={() => onAskAssistant({ kind: "budget", id: budget.id })}
                        >
                          Regge?
                        </button>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <BudgetItemSheet
        state={sheet}
        month={month}
        budgets={budgets}
        onClose={() => setSheet(null)}
        onSave={saveItem}
        onDelete={deleteItem}
      />

      {notice !== null ? <Toast message={notice} onDismiss={() => setNotice(null)} /> : null}
    </section>
  );
}
