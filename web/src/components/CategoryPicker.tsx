import { useEffect, useId, useRef, useState } from "react";
import type { MouseEvent } from "react";

import { errorMessage } from "../api";
import type { SplitInput } from "../api";
import type { Category, Transaction } from "../types";
import { SplitEditor } from "./SplitEditor";
import { categoryText } from "../category";

interface CategoryPickerProps {
  open: boolean;
  title: string;
  merchant: string | null;
  categories: Category[];
  categoriesError: string | null;
  onReloadCategories: () => void;
  onCreateCategory: (name: string) => Promise<void>;
  onSelect: (category: string, options: { rule: boolean }) => void;
  onClose: () => void;
  transaction?: Transaction | null;
  onSaveSplits?: (splits: SplitInput[]) => Promise<void>;
  /** Opens the transfer panel: this row may be money moved between own accounts. */
  onTransfer?: () => void;
}

export function CategoryPicker({
  open,
  title,
  merchant,
  categories,
  categoriesError,
  onReloadCategories,
  onCreateCategory,
  onSelect,
  onClose,
  transaction = null,
  onSaveSplits,
  onTransfer,
}: CategoryPickerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [rule, setRule] = useState(false);
  const [newCategory, setNewCategory] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [splitMode, setSplitMode] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setRule(false);
      setNewCategory("");
      setCreateError(null);
      setSplitMode(false);
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  const handleCreate = async () => {
    const name = newCategory.trim();
    if (!name || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      await onCreateCategory(name);
      onSelect(name, { rule });
    } catch (error) {
      setCreateError(errorMessage(error));
    } finally {
      setCreating(false);
    }
  };

  const handleBackdropClick = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === dialogRef.current) onClose();
  };

  const canSplit =
    transaction !== null && transaction.transfer === null && onSaveSplits !== undefined && categories.length > 0;
  const canTransfer =
    transaction !== null && transaction.transfer === null && onTransfer !== undefined;

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
            {splitMode ? (merchant ? `Dividi «${merchant}»` : "Dividi il movimento") : title}
          </h2>
          <button type="button" className="button button--ghost" onClick={onClose} aria-label="Chiudi">
            ✕
          </button>
        </header>

        {splitMode && transaction !== null && onSaveSplits ? (
          <SplitEditor
            transaction={transaction}
            categories={categories}
            onSave={onSaveSplits}
            onCancel={() => setSplitMode(false)}
          />
        ) : (
          <>
            {canSplit ? (
              <button type="button" className="button button--block" onClick={() => setSplitMode(true)}>
                Dividi in più categorie
              </button>
            ) : null}

            {canTransfer ? (
              <button type="button" className="button button--block" onClick={onTransfer}>
                È un giroconto
              </button>
            ) : null}

            {merchant ? (
              <label className="sheet__rule">
                <input
                  type="checkbox"
                  checked={rule}
                  onChange={(event) => setRule(event.target.checked)}
                />
                <span>Crea una regola per «{merchant}»</span>
              </label>
            ) : null}

            {categoriesError ? (
              <div className="state state--error" role="alert">
                <p>Impossibile caricare le categorie: {categoriesError}</p>
                <button type="button" className="button" onClick={onReloadCategories}>
                  Riprova
                </button>
              </div>
            ) : categories.length === 0 ? (
              <p className="state">Nessuna categoria disponibile.</p>
            ) : (
              <ul className="sheet__list">
                {categories.map((category) => (
                  <li key={category.id}>
                    <button
                      type="button"
                      className="sheet__option"
                      onClick={() => onSelect(category.name, { rule })}
                    >
                      {categoryText(category.name)}
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <form
              className="sheet__new"
              onSubmit={(event) => {
                event.preventDefault();
                void handleCreate();
              }}
            >
              <label className="sheet__new-label" htmlFor={`${titleId}-new`}>
                Nuova categoria
              </label>
              <div className="sheet__new-row">
                <input
                  id={`${titleId}-new`}
                  className="input"
                  type="text"
                  value={newCategory}
                  placeholder="Es. Spesa"
                  autoComplete="off"
                  onChange={(event) => setNewCategory(event.target.value)}
                />
                <button type="submit" className="button" disabled={creating || newCategory.trim() === ""}>
                  {creating ? "Creo…" : "Crea e assegna"}
                </button>
              </div>
              {createError ? (
                <p className="state state--error" role="alert">
                  Categoria non creata: {createError}
                </p>
              ) : null}
            </form>
          </>
        )}
      </div>
    </dialog>
  );
}
