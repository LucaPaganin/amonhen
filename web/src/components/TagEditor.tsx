import { useEffect, useId, useState } from "react";

import { errorMessage } from "../api";
import { useTags } from "../useTags";

interface TagEditorProps {
  /** What the movement carries now. */
  current: string[];
  onSave: (tags: string[]) => Promise<void>;
}

/** The tags of one movement: a chip to take one off, a field to add one. */
export function TagEditor({ current, onSave }: TagEditorProps) {
  const fieldId = useId();
  const { tags, reload } = useTags();
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The list may have grown under a movement opened earlier.
  useEffect(() => {
    setDraft("");
    setError(null);
    reload();
  }, [current, reload]);

  const save = async (next: string[]) => {
    setSaving(true);
    setError(null);
    try {
      await onSave(next);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  };

  const name = draft.trim();

  return (
    <form
      className="sheet__new"
      onSubmit={(event) => {
        event.preventDefault();
        if (name !== "" && !current.includes(name)) void save([...current, name]);
      }}
    >
      <label className="sheet__new-label" htmlFor={fieldId}>
        Tag
      </label>
      {current.length === 0 ? null : (
        <div className="filters__chips">
          {current.map((tag) => (
            <button
              key={tag}
              type="button"
              className="chip chip--toggle chip--tag"
              aria-label={`Togli il tag ${tag}`}
              disabled={saving}
              onClick={() => void save(current.filter((item) => item !== tag))}
            >
              {tag} ✕
            </button>
          ))}
        </div>
      )}
      <div className="sheet__new-row">
        <input
          id={fieldId}
          className="input"
          type="text"
          autoComplete="off"
          list={`${fieldId}-tags`}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <datalist id={`${fieldId}-tags`}>
          {tags.map((item) => (
            <option key={item.id} value={item.name} />
          ))}
        </datalist>
        <button type="submit" className="button" disabled={saving || name === ""}>
          {saving ? "Salvo…" : "Aggiungi"}
        </button>
      </div>
      {error === null ? null : (
        <p className="state state--error" role="alert">
          Tag non salvato: {error}
        </p>
      )}
    </form>
  );
}
