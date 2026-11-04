import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { categoryText } from "../category";
import { Help } from "../components/Help";
import { Toast } from "../components/Toast";
import { Toggle } from "../components/Toggle";
import {
  currentMonth,
  formatAmount,
  formatDate,
  formatMonth,
  monthBounds,
  shiftMonth,
  toAmount,
} from "../format";
import type {
  Budget,
  BudgetItem,
  BudgetItemDraft,
  BudgetMonth,
  BudgetPriority,
  Transaction,
} from "../types";

interface BudgetScreenProps {
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

/** The complete months a budget is read against. */
const WINDOWS = [3, 6, 12] as const;

type View = "categories" | "items";
type Statistic = "median" | "mean";

/** Per-viewer conveniences: the view, the statistic, the window, the hidden rows. */
const PREFERENCES_KEY = "amonhen.budget.view";

interface Preferences {
  view: View;
  statistic: Statistic;
  months: number;
  showEmpty: boolean;
}

const DEFAULT_PREFERENCES: Preferences = {
  view: "categories",
  statistic: "median",
  months: 6,
  showEmpty: false,
};

function readPreferences(): Preferences {
  try {
    const raw = window.localStorage.getItem(PREFERENCES_KEY);
    if (raw === null) return DEFAULT_PREFERENCES;
    const stored = JSON.parse(raw) as Partial<Preferences>;
    return {
      view: stored.view === "items" ? "items" : "categories",
      statistic: stored.statistic === "mean" ? "mean" : "median",
      months: WINDOWS.includes(stored.months as (typeof WINDOWS)[number])
        ? (stored.months as number)
        : DEFAULT_PREFERENCES.months,
      showEmpty: stored.showEmpty === true,
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function writePreferences(preferences: Preferences) {
  try {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
  } catch {
    // A private window has no storage: the screen works the same, it just forgets.
  }
}

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

const STATISTIC_LABELS: Record<Statistic, string> = { median: "mediana", mean: "media" };

/**
 * A budget against what the months before took. The words say the direction and
 * the size; null when there is nothing to compare with.
 */
function comparison(
  budget: string | null,
  usual: string | null,
): { text: string; tone: "over" | "under" | "even" } | null {
  if (budget === null || usual === null) return null;
  const planned = toAmount(budget);
  const past = toAmount(usual);
  if (past <= 0) return null;
  const share = Math.round(((planned - past) / past) * 100);
  if (Math.abs(share) < 5) return { text: "in linea", tone: "even" };
  return share > 0
    ? { text: `${share}% in più`, tone: "over" }
    : { text: `${-share}% in meno`, tone: "under" };
}

/** Where the ceiling of a category comes from, in words. */
function sourceText(budget: Budget): string {
  switch (budget.source) {
    case "override":
      return "solo questo mese";
    case "default":
      return "dal default";
    case "items":
      return "dalle voci";
    default:
      return "";
  }
}

function usualOf(budget: Budget, statistic: Statistic): string | null {
  return statistic === "median" ? budget.usual : budget.usual_mean;
}

/** The window in words: "giugno – ottobre 2026", or why there is none. */
function windowText(data: BudgetMonth): string {
  const { from, to, months } = data.window;
  if (from === null || to === null || months === 0) return "nessun mese completo prima di questo";
  if (from === to) return formatMonth(from);
  return `${formatMonth(from)} – ${formatMonth(to)} (${months} mesi)`;
}

/** Spent against the ceiling, as a bar: full past the ceiling, red when over. */
function Meter({ spent, budget }: { spent: string; budget: string | null }) {
  if (budget === null || toAmount(budget) <= 0) return null;
  const share = Math.max(0, toAmount(spent) / toAmount(budget));
  const over = share > 1;
  return (
    <span
      className={over ? "budget-meter budget-meter--over" : "budget-meter"}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={Number(toAmount(budget).toFixed(2))}
      aria-valuenow={Number(Math.max(0, toAmount(spent)).toFixed(2))}
      aria-label="Speso sul budget"
    >
      <span className="budget-meter__fill" style={{ width: `${Math.min(share, 1) * 100}%` }} />
    </span>
  );
}

interface ItemSheetState {
  /** The item being edited; null for a new one. */
  item: BudgetItem | null;
  /** The category a new item starts in; null lets the rules decide. */
  categoryId: number | null;
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
 * person has read them. An edit may move the item to another month or category,
 * or leave it without one.
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
      setCategoryId(state.categoryId ?? 0);
      setItemMonth(editing?.month ?? month);
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
  const valid = description.trim() !== "" && isPositiveAmount(amount) && itemMonth !== "";

  const submit = async () => {
    if (!valid || saving) return;
    setSaving(true);
    setError(null);
    const message = await onSave(
      {
        category_id: categoryId > 0 ? categoryId : null,
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
              <option value={0}>Da assegnare (decide una regola, se c'è)</option>
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

interface QuickAddProps {
  budgets: Budget[];
  busy: boolean;
  onAdd: (description: string, amount: string, categoryId: number | null) => Promise<boolean>;
  onMore: () => void;
}

/**
 * The fastest way to write an expense: what it is and how much. The category is
 * optional — a category rule on the description gives one, or the item waits
 * under *Da assegnare* — and the rest of the fields are in the full form.
 */
function QuickAdd({ budgets, busy, onAdd, onMore }: QuickAddProps) {
  const fieldId = useId();
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [categoryId, setCategoryId] = useState(0);
  const valid = description.trim() !== "" && isPositiveAmount(amount);

  const submit = async () => {
    if (!valid || busy) return;
    const added = await onAdd(
      description.trim(),
      amount.trim().replace(",", "."),
      categoryId > 0 ? categoryId : null,
    );
    if (added) {
      setDescription("");
      setAmount("");
      setCategoryId(0);
    }
  };

  return (
    <form
      className="budget-quick"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div className="budget-quick__fields">
        <label className="visually-hidden" htmlFor={`${fieldId}-description`}>
          Descrizione della spesa
        </label>
        <input
          id={`${fieldId}-description`}
          className="input budget-quick__description"
          type="text"
          placeholder="Una spesa che sai già, es. Bollo auto"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
        <label className="visually-hidden" htmlFor={`${fieldId}-amount`}>
          Importo
        </label>
        <input
          id={`${fieldId}-amount`}
          className="input budget-quick__amount"
          type="text"
          inputMode="decimal"
          placeholder="0,00"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
        <label className="visually-hidden" htmlFor={`${fieldId}-category`}>
          Categoria
        </label>
        <select
          id={`${fieldId}-category`}
          className="input budget-quick__category"
          value={categoryId}
          onChange={(event) => setCategoryId(Number(event.target.value))}
        >
          <option value={0}>Categoria: dopo</option>
          {budgets.map((budget) => (
            <option key={budget.id} value={budget.id}>
              {categoryText(budget.category)}
            </option>
          ))}
        </select>
      </div>
      <div className="budget-quick__actions">
        <button type="submit" className="button button--primary" disabled={!valid || busy}>
          Aggiungi
        </button>
        <button type="button" className="button button--ghost" onClick={onMore}>
          Più dettagli
        </button>
      </div>
    </form>
  );
}

/** The month's totals: what is budgeted, against what the months before took. */
function Summary({ data, statistic }: { data: BudgetMonth; statistic: Statistic }) {
  const { total } = data;
  const budgetedUsual = statistic === "median" ? total.budgeted_usual : total.budgeted_usual_mean;
  const allUsual = statistic === "median" ? total.usual : total.usual_mean;
  const label = STATISTIC_LABELS[statistic];
  const against = total.categories > 0 ? comparison(total.budget, budgetedUsual) : null;
  const unassigned = data.unassigned.length;
  return (
    <div className="budget-summary">
      <div className="budget-summary__figures">
        <div className="budget-figure">
          <span className="budget-figure__label">A budget</span>
          <span className="budget-figure__value">{formatAmount(total.budget)}</span>
          <span className="budget-figure__meta">
            {total.categories === 1 ? "1 categoria" : `${total.categories} categorie`}
          </span>
        </div>
        <div className="budget-figure">
          <span className="budget-figure__label">Di solito, le stesse ({label})</span>
          <span className="budget-figure__value">
            {budgetedUsual !== null && total.categories > 0 ? formatAmount(budgetedUsual) : "—"}
          </span>
          {against !== null ? (
            <span className={`budget-figure__meta budget-compare--${against.tone}`}>
              il budget è {against.text}
            </span>
          ) : null}
        </div>
        <div className="budget-figure">
          <span className="budget-figure__label">Tutta la spesa, di solito</span>
          <span className="budget-figure__value">{allUsual !== null ? formatAmount(allUsual) : "—"}</span>
          <span className="budget-figure__meta">{label}</span>
        </div>
        <div className="budget-figure">
          <span className="budget-figure__label">Speso questo mese</span>
          <span className="budget-figure__value">{formatAmount(total.spent)}</span>
          <span className="budget-figure__meta">
            {formatAmount(total.budgeted_spent)} nelle categorie a budget
          </span>
        </div>
      </div>
      <Meter spent={total.budgeted_spent} budget={total.categories > 0 ? total.budget : null} />
      <p className="hint">
        Confronto con {windowText(data)}.
        {unassigned > 0
          ? ` ${unassigned === 1 ? "Una voce aspetta" : `${unassigned} voci aspettano`} una categoria (${formatAmount(
              total.unassigned,
            )}), e non conta nel budget finché non ce l'ha.`
          : ""}
      </p>
    </div>
  );
}

interface CategoryRowProps {
  budget: Budget;
  statistic: Statistic;
  open: boolean;
  busy: boolean;
  editing: boolean;
  draft: string;
  onToggle: () => void;
  onDraft: (value: string) => void;
  onStartEditing: () => void;
  onStopEditing: () => void;
  onSaveDefault: () => void;
  onSaveOverride: () => void;
  onClearOverride: () => void;
  onClearDefault: () => void;
  onAddItem: () => void;
  onCopyPrevious: () => void;
  onOpenItem: (item: BudgetItem) => void;
}

/** One category: the ceiling, what was spent, how it compares, and its items on request. */
function CategoryRow(props: CategoryRowProps) {
  const { budget, statistic, open, busy, editing, draft } = props;
  const usual = usualOf(budget, statistic);
  const against = comparison(budget.budget, usual);
  const remaining = budget.remaining === null ? null : toAmount(budget.remaining);
  const over = (remaining !== null && remaining < 0) || budget.over_plan;
  const detailsId = useId();
  return (
    <li className={over ? "budget-row budget-row--over" : "budget-row"}>
      <button
        type="button"
        className="budget-row__toggle"
        aria-expanded={open}
        aria-controls={detailsId}
        onClick={props.onToggle}
      >
        <span className="budget-row__head">
          <span className="budget-row__name">{categoryText(budget.category)}</span>
          <span className="budget-row__amount">
            {budget.budget === null ? "—" : formatAmount(budget.budget)}
          </span>
        </span>
        <Meter spent={budget.spent} budget={budget.budget} />
        <span className="budget-row__status">
          {formatAmount(budget.spent)} spesi
          {remaining !== null
            ? remaining < 0
              ? ` · sforato di ${formatAmount(-remaining)}`
              : ` · restano ${formatAmount(budget.remaining ?? "0")}`
            : ""}
          {budget.source !== null ? ` · ${sourceText(budget)}` : ""}
        </span>
        {budget.over_plan ? (
          <span className="budget-row__status budget-row__over">
            Le voci superano il budget di {formatAmount(-toAmount(budget.free ?? "0"))}
          </span>
        ) : null}
        <span className="budget-row__status">
          {usual === null || (toAmount(usual) === 0 && toAmount(budget.usual_mean ?? "0") === 0)
            ? "Nessuna spesa nei mesi prima"
            : `Di solito ${formatAmount(usual)} (${STATISTIC_LABELS[statistic]})`}
          {against !== null ? (
            <span className={`budget-compare budget-compare--${against.tone}`}> · budget {against.text}</span>
          ) : null}
        </span>
      </button>

      {open ? (
        <div className="budget-row__details" id={detailsId}>
          {budget.items.length > 0 ? (
            <ul className="budget-items">
              {budget.items.map((item) => (
                <li key={item.id}>
                  <ItemButton item={item} onOpen={() => props.onOpenItem(item)} />
                </li>
              ))}
            </ul>
          ) : null}
          {editing ? (
            <form
              className="budget-editor"
              onSubmit={(event) => {
                event.preventDefault();
                props.onSaveDefault();
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
                placeholder={usual !== null ? formatAmount(usual) : "0,00"}
                value={draft}
                onChange={(event) => props.onDraft(event.target.value)}
                autoFocus
              />
              <div className="budget-editor__actions">
                <button type="submit" className="button button--primary" disabled={busy || draft.trim() === ""}>
                  Da questo mese in poi
                </button>
                <button
                  type="button"
                  className="button"
                  disabled={busy || draft.trim() === ""}
                  onClick={props.onSaveOverride}
                >
                  Solo questo mese
                </button>
                {budget.override !== null ? (
                  <button type="button" className="button" disabled={busy} onClick={props.onClearOverride}>
                    Torna al default
                  </button>
                ) : null}
                {budget.default !== null ? (
                  <button type="button" className="button button--danger" disabled={busy} onClick={props.onClearDefault}>
                    Rimuovi da questo mese
                  </button>
                ) : null}
                <button type="button" className="button" onClick={props.onStopEditing}>
                  Annulla
                </button>
              </div>
            </form>
          ) : (
            <div className="budget-row__actions">
              <button type="button" className="button" onClick={props.onStartEditing}>
                {budget.source === null || budget.source === "items" ? "Imposta un tetto" : "Modifica budget"}
              </button>
              <button type="button" className="button" onClick={props.onAddItem}>
                Aggiungi voce
              </button>
              <button type="button" className="button" disabled={busy} onClick={props.onCopyPrevious}>
                Copia dal mese prima
              </button>
            </div>
          )}
        </div>
      ) : null}
    </li>
  );
}

function ItemButton({ item, category, onOpen }: { item: BudgetItem; category?: string; onOpen: () => void }) {
  return (
    <button
      type="button"
      className={item.fits === false ? "budget-item budget-item--out" : "budget-item"}
      onClick={onOpen}
      aria-label={`Modifica ${item.description}`}
    >
      <span className="budget-item__text">
        <span className="budget-item__name">{item.description}</span>
        <span className="budget-item__meta">
          {category !== undefined ? <span className="chip">{category}</span> : null}
          <span className={`chip chip--priority-${item.priority}`}>{PRIORITY_LABELS[item.priority]}</span>
          {item.date !== null ? <span>{formatDate(item.date)}</span> : null}
          {item.fits === false ? <span className="chip chip--warning">Non ci sta</span> : null}
          {item.note !== null ? <span className="budget-item__note">{item.note}</span> : null}
        </span>
      </span>
      <span className="budget-item__amount">{formatAmount(item.amount)}</span>
    </button>
  );
}

interface ItemsViewProps {
  data: BudgetMonth;
  busy: boolean;
  onAssign: (item: BudgetItem, categoryId: number) => void;
  onOpenItem: (item: BudgetItem, categoryId: number | null) => void;
}

/** Every item of the month in one list, the ones waiting for a category first. */
function ItemsView({ data, busy, onAssign, onOpenItem }: ItemsViewProps) {
  const rows = useMemo(
    () =>
      data.categories
        .flatMap((budget) => budget.items.map((item) => ({ item, budget })))
        .sort((a, b) => {
          const rank = PRIORITIES.indexOf(a.item.priority) - PRIORITIES.indexOf(b.item.priority);
          if (rank !== 0) return rank;
          if ((a.item.date === null) !== (b.item.date === null)) return a.item.date === null ? 1 : -1;
          return (a.item.date ?? "").localeCompare(b.item.date ?? "") || a.item.id - b.item.id;
        }),
    [data],
  );
  if (rows.length === 0 && data.unassigned.length === 0) {
    return <p className="state">Nessuna voce in {formatMonth(data.month)}: aggiungine una qui sopra.</p>;
  }
  return (
    <div className="budget-voices">
      {data.unassigned.length > 0 ? (
        <section className="budget-voices__group" aria-label="Da assegnare">
          <h3 className="budget-voices__title">
            Da assegnare <span className="count">{data.unassigned.length}</span>
          </h3>
          <ul className="budget-items">
            {data.unassigned.map((item) => (
              <li className="budget-assign" key={item.id}>
                <ItemButton item={item} onOpen={() => onOpenItem(item, null)} />
                <label className="visually-hidden" htmlFor={`assign-${item.id}`}>
                  Categoria per {item.description}
                </label>
                <select
                  id={`assign-${item.id}`}
                  className="input budget-assign__select"
                  value={0}
                  disabled={busy}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    if (value > 0) onAssign(item, value);
                  }}
                >
                  <option value={0}>Scegli la categoria…</option>
                  {data.categories.map((budget) => (
                    <option key={budget.id} value={budget.id}>
                      {categoryText(budget.category)}
                    </option>
                  ))}
                </select>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {rows.length > 0 ? (
        <section className="budget-voices__group" aria-label="Voci del mese">
          <h3 className="budget-voices__title">
            Voci del mese <span className="count">{rows.length}</span>
          </h3>
          <ul className="budget-items">
            {rows.map(({ item, budget }) => (
              <li key={item.id}>
                <ItemButton
                  item={item}
                  category={categoryText(budget.category)}
                  onOpen={() => onOpenItem(item, budget.id)}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

export function BudgetScreen({ refreshToken }: BudgetScreenProps) {
  const [month, setMonth] = useState(currentMonth);
  const [preferences, setPreferences] = useState<Preferences>(readPreferences);
  const [data, setData] = useState<BudgetMonth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [opened, setOpened] = useState<number | null>(null);
  const [editingBudget, setEditingBudget] = useState<number | null>(null);
  const [budgetDraft, setBudgetDraft] = useState("");
  const [pending, setPending] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [sheet, setSheet] = useState<ItemSheetState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const { months, statistic, view, showEmpty } = preferences;
  const budgets = data?.categories ?? [];

  const prefer = (change: Partial<Preferences>) => {
    setPreferences((current) => {
      const next = { ...current, ...change };
      writePreferences(next);
      return next;
    });
  };

  const load = useCallback(async (value: string, span: number, signal?: AbortSignal) => {
    setLoading(true);
    try {
      setData(await api.budgets(value, span, signal));
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
    void load(month, months, controller.signal);
    return () => controller.abort();
  }, [load, month, months, refreshToken]);

  // Every budget write answers with the month again, so a write is a request
  // and a replacement of the screen's data, never an adjustment made here.
  const write = async (budget: Budget, request: () => Promise<BudgetMonth>, done: string) => {
    if (pending !== null) return;
    setPending(budget.id);
    try {
      setData(await request());
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
      () => api.setBudget(budget.id, amount, month, months),
      `Budget di ${categoryText(budget.category)} salvato da ${formatMonth(month)} in poi`,
    );
  };

  const saveOverride = (budget: Budget) => {
    const amount = draftAmount();
    if (amount === null) return;
    void write(
      budget,
      () => api.setBudgetOverride(budget.id, amount, month, months),
      `Budget di ${categoryText(budget.category)} salvato solo per ${formatMonth(month)}`,
    );
  };

  const copyPrevious = async (budget: Budget) => {
    if (pending !== null) return;
    setPending(budget.id);
    const previous = shiftMonth(month, -1);
    try {
      const answer = await api.copyBudgetItems(budget.id, previous, month, months);
      setData(answer.budgets);
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

  /** Where a new item landed, read from the month the server answered with. */
  const landing = (answer: BudgetMonth, before: Set<number>): string => {
    if (answer.unassigned.some((item) => !before.has(item.id))) return "da assegnare";
    const home = answer.categories.find((budget) => budget.items.some((item) => !before.has(item.id)));
    return home === undefined ? "" : `in ${categoryText(home.category)}`;
  };

  const knownIds = (): Set<number> =>
    new Set([
      ...(data?.unassigned ?? []).map((item) => item.id),
      ...budgets.flatMap((budget) => budget.items.map((item) => item.id)),
    ]);

  const quickAdd = async (description: string, amount: string, categoryId: number | null) => {
    if (adding) return false;
    setAdding(true);
    const before = knownIds();
    try {
      const answer = await api.createBudgetItem(
        { category_id: categoryId, month, description, amount, date: null, priority: "important", note: null },
        months,
      );
      setData(answer);
      setNotice(`Voce aggiunta ${landing(answer, before)}`.trim());
      return true;
    } catch (caught) {
      setNotice(`Voce non aggiunta: ${errorMessage(caught)}`);
      return false;
    } finally {
      setAdding(false);
    }
  };

  const saveItem = async (draft: BudgetItemDraft, item: BudgetItem | null): Promise<string | null> => {
    try {
      const before = knownIds();
      let answer: BudgetMonth;
      if (item === null) {
        // A new item answers with the month it was planned for, which may not
        // be the one on screen: then the screen's month is read again.
        answer = await api.createBudgetItem(draft, months);
        setData(draft.month === month ? answer : await api.budgets(month, months));
      } else {
        answer = await api.updateBudgetItem(item.id, draft, month, months);
        setData(answer);
      }
      // An item saved into another month leaves this list; the notice says where it went.
      const elsewhere = draft.month !== month ? ` in ${formatMonth(draft.month)}` : "";
      const where = item === null && draft.month === month ? ` ${landing(answer, before)}` : "";
      setNotice(item === null ? `Voce aggiunta${elsewhere}${where}` : `Voce salvata${elsewhere}`);
      return null;
    } catch (caught) {
      return errorMessage(caught);
    }
  };

  const assign = async (item: BudgetItem, categoryId: number) => {
    if (pending !== null) return;
    setPending(-item.id);
    try {
      setData(
        await api.updateBudgetItem(
          item.id,
          {
            category_id: categoryId,
            month: item.month,
            description: item.description,
            amount: item.amount,
            date: item.date,
            priority: item.priority,
            note: item.note,
          },
          month,
          months,
        ),
      );
      const category = budgets.find((budget) => budget.id === categoryId);
      setNotice(`${item.description} in ${categoryText(category?.category ?? "")}`);
    } catch (caught) {
      setNotice(`Voce non spostata: ${errorMessage(caught)}`);
    } finally {
      setPending(null);
    }
  };

  const deleteItem = async (item: BudgetItem): Promise<string | null> => {
    try {
      setData(await api.deleteBudgetItem(item.id, months));
      setNotice(`Voce eliminata: ${item.description}`);
      return null;
    } catch (caught) {
      return errorMessage(caught);
    }
  };

  // A category without a ceiling and without items is hidden unless asked for:
  // with many categories, the list is the ones a person decided about.
  const visible = budgets.filter((budget) => showEmpty || budget.budget !== null);
  const hidden = budgets.length - visible.length;

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Budget</h1>
          <p className="screen__subtitle">
            Quanto vuoi spendere in un mese, e le spese che sai già di dover fare.{" "}
            <Help topic="budget" label="budget e voci" />
          </p>
        </div>
      </header>

      <section className="panel">
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
        <div className="budget-controls">
          <div className="filters__chips" role="group" aria-label="Confronta con">
            {(["median", "mean"] as const).map((value) => (
              <button
                key={value}
                type="button"
                className={statistic === value ? "chip chip--toggle chip--on" : "chip chip--toggle"}
                aria-pressed={statistic === value}
                onClick={() => prefer({ statistic: value })}
              >
                {value === "median" ? "Mediana" : "Media"}
              </button>
            ))}
          </div>
          <div className="filters__chips" role="group" aria-label="Mesi del confronto">
            {WINDOWS.map((count) => (
              <button
                key={count}
                type="button"
                className={months === count ? "chip chip--toggle chip--on" : "chip chip--toggle"}
                aria-pressed={months === count}
                onClick={() => prefer({ months: count })}
              >
                {count} mesi
              </button>
            ))}
          </div>
        </div>
        {data !== null ? <Summary data={data} statistic={statistic} /> : null}
      </section>

      <section className="panel">
        <h2 className="section-title">Aggiungi una spesa</h2>
        <QuickAdd
          budgets={budgets}
          busy={adding || data === null}
          onAdd={quickAdd}
          onMore={() => setSheet({ item: null, categoryId: null })}
        />
      </section>

      <section className="panel">
        <div className="budget-viewbar">
          <div className="filters__chips" role="tablist" aria-label="Vista">
            {(["categories", "items"] as const).map((value) => (
              <button
                key={value}
                type="button"
                role="tab"
                className={view === value ? "chip chip--toggle chip--on" : "chip chip--toggle"}
                aria-selected={view === value}
                onClick={() => prefer({ view: value })}
              >
                {value === "categories"
                  ? "Per categoria"
                  : `Per voce${data !== null && data.unassigned.length > 0 ? ` · ${data.unassigned.length} da assegnare` : ""}`}
              </button>
            ))}
          </div>
          {view === "categories" ? (
            <Toggle
              label="Anche senza budget"
              ariaLabel="Mostra le categorie senza budget"
              checked={showEmpty}
              onChange={(next) => prefer({ showEmpty: next })}
            />
          ) : null}
        </div>

        {error !== null ? (
          <div className="state state--error" role="alert">
            <p>Impossibile caricare i budget: {error}</p>
            <button type="button" className="button" onClick={() => void load(month, months)}>
              Riprova
            </button>
          </div>
        ) : loading && data === null ? (
          <p className="state" aria-busy="true">
            Caricamento…
          </p>
        ) : data === null ? null : view === "items" ? (
          <ItemsView
            data={data}
            busy={pending !== null}
            onAssign={(item, categoryId) => void assign(item, categoryId)}
            onOpenItem={(item, categoryId) => setSheet({ item, categoryId })}
          />
        ) : budgets.length === 0 ? (
          <p className="state">Nessuna categoria su cui impostare un budget.</p>
        ) : (
          <>
            {visible.length === 0 ? (
              <p className="state">
                Nessuna categoria ha un budget in {formatMonth(month)}: aggiungi una spesa qui sopra, o mostra
                anche quelle senza budget per impostarne uno.
              </p>
            ) : (
              <ul className="budget-list">
                {visible.map((budget) => (
                  <CategoryRow
                    key={budget.id}
                    budget={budget}
                    statistic={statistic}
                    open={opened === budget.id}
                    busy={pending === budget.id}
                    editing={editingBudget === budget.id}
                    draft={budgetDraft}
                    onToggle={() => {
                      setOpened(opened === budget.id ? null : budget.id);
                      setEditingBudget(null);
                    }}
                    onDraft={setBudgetDraft}
                    onStartEditing={() => {
                      setEditingBudget(budget.id);
                      setBudgetDraft(budget.source === "items" ? "" : (budget.budget ?? ""));
                    }}
                    onStopEditing={() => setEditingBudget(null)}
                    onSaveDefault={() => saveDefault(budget)}
                    onSaveOverride={() => saveOverride(budget)}
                    onClearOverride={() =>
                      void write(
                        budget,
                        () => api.setBudgetOverride(budget.id, null, month, months),
                        `${formatMonth(month)} torna al budget di default`,
                      )
                    }
                    onClearDefault={() =>
                      void write(
                        budget,
                        () => api.setBudget(budget.id, null, month, months),
                        `Budget di ${categoryText(budget.category)} rimosso da ${formatMonth(month)} in poi`,
                      )
                    }
                    onAddItem={() => setSheet({ item: null, categoryId: budget.id })}
                    onCopyPrevious={() => void copyPrevious(budget)}
                    onOpenItem={(item) => setSheet({ item, categoryId: budget.id })}
                  />
                ))}
              </ul>
            )}
            {hidden > 0 ? (
              <p className="hint">
                {hidden === 1 ? "Una categoria senza budget è nascosta" : `${hidden} categorie senza budget sono nascoste`}
                : «Anche senza budget» le mostra.
              </p>
            ) : null}
          </>
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
