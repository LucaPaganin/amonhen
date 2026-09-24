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
  /** Writes the movement's local note; the only field of it a person may set. */
  onSaveNotes?: (notes: string) => Promise<void>;
  /** Takes the movement out of the ledger; the caller closes and reports it. */
  onDelete?: () => Promise<void>;
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
  onSaveNotes,
  onDelete,
  onTransfer,
}: CategoryPickerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [rule, setRule] = useState(false);
  const [newCategory, setNewCategory] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [splitMode, setSplitMode] = useState(false);
  const [noteDraft, setNoteDraft] = useState("");
  const [savedNote, setSavedNote] = useState<string | null>(null);
  const [savingNote, setSavingNote] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // The draft starts from what the movement carries, and what was saved is kept
  // here rather than read back from the prop: the caller may not have refetched
  // the row yet, and a save button that stays lit after saving is a lie.
  useEffect(() => {
    setNoteDraft(transaction?.notes ?? "");
    setSavedNote(transaction?.notes ?? null);
    setNoteError(null);
    setConfirmingDelete(false);
    setDeleteError(null);
  }, [transaction?.id, transaction?.notes]);

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

  const saveNote = async () => {
    if (transaction === null || onSaveNotes === undefined || savingNote) return;
    const notes = noteDraft.trim();
    setSavingNote(true);
    setNoteError(null);
    try {
      await onSaveNotes(notes);
      setSavedNote(notes === "" ? null : notes);
    } catch (error) {
      setNoteError(errorMessage(error));
    } finally {
      setSavingNote(false);
    }
  };

  const deleteMovement = async () => {
    if (onDelete === undefined || deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await onDelete();
    } catch (error) {
      setDeleteError(errorMessage(error));
      setDeleting(false);
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
            {transaction !== null && onSaveNotes !== undefined ? (
              <form
                className="sheet__new sheet__note"
                onSubmit={(event) => {
                  event.preventDefault();
                  void saveNote();
                }}
              >
                <label className="sheet__new-label" htmlFor={`${titleId}-note`}>
                  Nota
                </label>
                <div className="sheet__new-row">
                  <input
                    id={`${titleId}-note`}
                    className="input"
                    type="text"
                    value={noteDraft}
                    placeholder="Es. rimborso a metà"
                    autoComplete="off"
                    onChange={(event) => setNoteDraft(event.target.value)}
                  />
                  <button
                    type="submit"
                    className="button"
                    disabled={savingNote || noteDraft.trim() === (savedNote ?? "")}
                  >
                    {savingNote ? "Salvo…" : "Salva nota"}
                  </button>
                </div>
                <p className="hint">
                  La nota è tua: il sync non la tocca e nessun altro campo si modifica.
                </p>
                {noteError !== null ? (
                  <p className="state state--error" role="alert">
                    Nota non salvata: {noteError}
                  </p>
                ) : null}
              </form>
            ) : null}

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

            {onDelete === undefined ? null : (
              <div className="sheet__new">
                {confirmingDelete ? (
                  <>
                    <p className="hint">
                      Esce dal ledger e resta nel cestino del conto, in Conti, da dove si riporta.
                    </p>
                    <div className="sheet__new-row">
                      <button
                        type="button"
                        className="button button--danger"
                        onClick={() => void deleteMovement()}
                        disabled={deleting}
                      >
                        {deleting ? "Cancello…" : "Sì, cancella"}
                      </button>
                      <button
                        type="button"
                        className="button"
                        onClick={() => setConfirmingDelete(false)}
                        disabled={deleting}
                      >
                        No, lascia stare
                      </button>
                    </div>
                  </>
                ) : (
                  <button
                    type="button"
                    className="button button--danger button--block"
                    onClick={() => setConfirmingDelete(true)}
                  >
                    Cancella il movimento
                  </button>
                )}
                {deleteError !== null ? (
                  <p className="state state--error" role="alert">
                    Movimento non cancellato: {deleteError}
                  </p>
                ) : null}
              </div>
            )}
          </>
        )}
      </div>
    </dialog>
  );
}
