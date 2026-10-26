import { useEffect, useId, useRef, useState } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { bucketName, categoryText } from "../category";
import { formatAmount, formatDate } from "../format";
import type { Account, Category, RuleAction, RuleDraft, RulePreview } from "../types";

interface RuleSheetProps {
  title: string;
  /** What the editor starts from: a merchant's text and category, or a saved rule. */
  initial: RuleDraft;
  categories: Category[];
  /** Saves the rule; answers the error to show, or null once it is saved. */
  onSave: (draft: RuleDraft) => Promise<string | null>;
  onClose: () => void;
}

const ACTIONS: { value: RuleAction; label: string }[] = [
  { value: "category", label: "Assegna una categoria" },
  { value: "transfer", label: "È un giroconto" },
  { value: "delete", label: "Cancella il movimento" },
];

/**
 * One rule, written or changed: the text the description contains, the
 * conditions that narrow it, and what follows. Mounted only while open — each
 * opening starts from `initial` — and the preview is asked of the server, which
 * is where the matching lives: the list under the form is what the rule would
 * take if it were saved now. A deleting rule empties those movements into the
 * trash on save, so its button says how many.
 */
export function RuleSheet({ title, initial, categories, onSave, onClose }: RuleSheetProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const fieldId = useId();
  const [draft, setDraft] = useState<RuleDraft>(initial);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [destinations, setDestinations] = useState<string[]>([]);
  // Real accounts added by hand: the rule writes the other half of the movement
  // there, so their balance follows the transfers.
  const [handAccounts, setHandAccounts] = useState<string[]>([]);
  const [preview, setPreview] = useState<RulePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!dialogRef.current?.open) dialogRef.current?.showModal();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    api
      .accounts(controller.signal)
      .then(setAccounts)
      .catch(() => undefined);
    api
      .transferLabels(controller.signal)
      .then((labels) => {
        setHandAccounts(labels.accounts);
        setDestinations([...new Set([...labels.accounts, ...labels.configured, ...labels.recorded])]);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  // Only the text and the conditions decide what a rule takes; the action does not.
  const { pattern, account_id, amount_min, amount_max } = draft;
  useEffect(() => {
    if (pattern.trim() === "") {
      setPreview(null);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .previewRule({ pattern, action: "delete", target: null, account_id, amount_min, amount_max })
        .then((found) => {
          if (controller.signal.aborted) return;
          setPreview(found);
          setPreviewError(null);
        })
        .catch((error) => {
          if (controller.signal.aborted || isAbortError(error)) return;
          setPreview(null);
          setPreviewError(errorMessage(error));
        });
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [pattern, account_id, amount_min, amount_max]);

  const set = (next: Partial<RuleDraft>) => setDraft((current) => ({ ...current, ...next }));

  const chooseAction = (action: RuleAction) => {
    // The target means something else for each action: a category is not a
    // destination, and a deletion has none.
    const target =
      action === initial.action ? initial.target : action === "category" ? draft.target : null;
    set({ action, target: action === "delete" ? null : target });
  };

  const options = categories.filter((item) => item.name !== bucketName());
  const ready =
    draft.pattern.trim() !== "" &&
    (draft.action === "delete" || (draft.target ?? "").trim() !== "") &&
    previewError === null;

  const save = async () => {
    if (!ready || saving) return;
    setSaving(true);
    setSaveError(null);
    const message = await onSave({
      ...draft,
      pattern: draft.pattern.trim(),
      target: draft.action === "delete" ? null : (draft.target ?? "").trim(),
      amount_min: (draft.amount_min ?? "").trim() || null,
      amount_max: (draft.amount_max ?? "").trim() || null,
    });
    setSaving(false);
    if (message !== null) setSaveError(message);
  };

  const count = preview?.count ?? 0;
  const movements = `${count} ${count === 1 ? "movimento" : "movimenti"}`;
  const saveLabel =
    draft.action === "delete"
      ? `Cancella ${movements} e salva la regola`
      : draft.id
        ? "Salva le modifiche"
        : "Salva la regola";

  return (
    <dialog
      ref={dialogRef}
      className="sheet"
      aria-labelledby={`${fieldId}-title`}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === dialogRef.current) onClose();
      }}
    >
      <div className="sheet__panel">
        <header className="sheet__header">
          <h2 className="sheet__title" id={`${fieldId}-title`}>
            {title}
          </h2>
          <button type="button" className="button button--ghost" onClick={onClose} aria-label="Chiudi">
            ✕
          </button>
        </header>

        <form
          className="rule-sheet"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="field">
            <label htmlFor={`${fieldId}-pattern`}>Se la descrizione contiene</label>
            <input
              id={`${fieldId}-pattern`}
              className="input"
              type="text"
              autoComplete="off"
              value={draft.pattern}
              placeholder="testo, o /espressione/"
              onChange={(event) => set({ pattern: event.target.value })}
            />
          </div>

          <div className="rule-sheet__pair">
            <div className="field">
              <label htmlFor={`${fieldId}-account`}>Sul conto</label>
              <select
                id={`${fieldId}-account`}
                className="input"
                value={draft.account_id ?? ""}
                onChange={(event) =>
                  set({ account_id: event.target.value === "" ? null : Number(event.target.value) })
                }
              >
                <option value="">Qualsiasi conto</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <span className="field__label" id={`${fieldId}-amount`}>
                Importo (senza segno)
              </span>
              <div className="rule-sheet__range" role="group" aria-labelledby={`${fieldId}-amount`}>
                <input
                  className="input"
                  type="text"
                  inputMode="decimal"
                  aria-label="Importo minimo"
                  placeholder="da"
                  value={draft.amount_min ?? ""}
                  onChange={(event) => set({ amount_min: event.target.value })}
                />
                <input
                  className="input"
                  type="text"
                  inputMode="decimal"
                  aria-label="Importo massimo"
                  placeholder="a"
                  value={draft.amount_max ?? ""}
                  onChange={(event) => set({ amount_max: event.target.value })}
                />
              </div>
            </div>
          </div>

          <fieldset className="rule-sheet__actions">
            <legend>Allora</legend>
            {ACTIONS.map((option) => (
              <label key={option.value} className="rule-sheet__action">
                <input
                  type="radio"
                  name={`${fieldId}-action`}
                  value={option.value}
                  checked={draft.action === option.value}
                  onChange={() => chooseAction(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </fieldset>

          {draft.action === "category" ? (
            <div className="field">
              <label htmlFor={`${fieldId}-category`}>Categoria</label>
              <select
                id={`${fieldId}-category`}
                className="input"
                value={draft.target ?? ""}
                onChange={(event) => set({ target: event.target.value })}
              >
                <option value="" disabled>
                  Scegli…
                </option>
                {options.map((item) => (
                  <option key={item.id} value={item.name}>
                    {categoryText(item.name)}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          {draft.action === "transfer" ? (
            <div className="field">
              <label htmlFor={`${fieldId}-destination`}>Verso</label>
              <input
                id={`${fieldId}-destination`}
                className="input"
                type="text"
                autoComplete="off"
                list={`${fieldId}-destinations`}
                placeholder="es. Conto deposito"
                value={draft.target ?? ""}
                onChange={(event) => set({ target: event.target.value })}
              />
              <datalist id={`${fieldId}-destinations`}>
                {destinations.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
              {handAccounts.includes((draft.target ?? "").trim()) ? (
                <p className="hint">
                  È un conto creato a mano: la regola ci scrive il movimento opposto e li collega
                  come giroconto, così il suo saldo segue i giroconti.
                </p>
              ) : (
                <p className="hint">
                  Esce dalle spese e dalle entrate e resta registrato su quella destinazione, come
                  un giroconto verso un conto che qui non è collegato.
                </p>
              )}
            </div>
          ) : null}

          {draft.action === "delete" ? (
            <p className="hint">
              I movimenti qui sotto vanno nel cestino del loro conto, e quelli che arriveranno con i
              prossimi sync ci finiscono da soli. Finché la regola c&apos;è non si ripristinano.
            </p>
          ) : null}

          <section className="rule-sheet__preview" aria-live="polite">
            {previewError !== null ? (
              <p className="state state--error" role="alert">
                {previewError}
              </p>
            ) : preview === null ? (
              <p className="hint">Scrivi un testo per vedere quali movimenti prende.</p>
            ) : (
              <>
                <p className="rule-sheet__count">
                  {draft.action === "delete" ? "Cancella " : "Combacia con "}
                  <strong>{movements}</strong>
                  {preview.count > preview.items.length ? `, i ${preview.items.length} più recenti:` : ""}
                </p>
                {preview.items.length > 0 ? (
                  <ul className="rule-sheet__items">
                    {preview.items.map((item) => (
                      <li key={item.id} className="rule-sheet__item">
                        <span className="rule-sheet__item-text">
                          <span className="rule-sheet__item-description">{item.description}</span>
                          <span className="rule-sheet__item-meta">
                            {formatDate(item.date)} · {item.account}
                          </span>
                        </span>
                        <span className="rule-sheet__item-amount">{formatAmount(item.amount)}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            )}
          </section>

          {saveError !== null ? (
            <p className="state state--error" role="alert">
              Regola non salvata: {saveError}
            </p>
          ) : null}

          <div className="card__actions">
            <button
              type="submit"
              className={draft.action === "delete" ? "button button--danger" : "button button--primary"}
              disabled={!ready || saving}
            >
              {saving ? "Salvo…" : saveLabel}
            </button>
            <button type="button" className="button" onClick={onClose} disabled={saving}>
              Annulla
            </button>
          </div>
        </form>
      </div>
    </dialog>
  );
}

/** A saved rule as the editor writes it back. */
export function draftOf(rule: {
  id: number;
  pattern: string;
  action: RuleAction;
  target: string | null;
  account_id: number | null;
  amount_min: string | null;
  amount_max: string | null;
}): RuleDraft {
  return {
    id: rule.id,
    pattern: rule.pattern,
    action: rule.action,
    target: rule.target,
    account_id: rule.account_id,
    amount_min: rule.amount_min,
    amount_max: rule.amount_max,
  };
}

/** A new category rule for a merchant, the way the movement sheets start one. */
export function merchantDraft(merchant: string, category: string): RuleDraft {
  return {
    pattern: merchant,
    action: "category",
    target: category,
    account_id: null,
    amount_min: null,
    amount_max: null,
  };
}
