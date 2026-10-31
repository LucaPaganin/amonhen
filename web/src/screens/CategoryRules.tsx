import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, errorMessage } from "../api";
import { bucketName, categoryText } from "../category";
import { Help } from "../components/Help";
import { RuleSheet, draftOf } from "../components/RuleSheet";
import { Toggle } from "../components/Toggle";
import { formatAmount } from "../format";
import type { Category, Rule, RuleAction, RuleDraft } from "../types";
import type { CategoryFlags } from "../useCategories";
import type { RulesController } from "../useRules";
import { useTags } from "../useTags";

/** One is a singular in Italian, and the count is read out loud in the row. */
function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

/** What narrows a rule besides its text, in the words the row prints. */
function conditionsText(rule: Rule): string | null {
  const parts: string[] = [];
  if (rule.account !== null) parts.push(`solo ${rule.account}`);
  if (rule.amount_min !== null && rule.amount_max !== null) {
    parts.push(
      rule.amount_min === rule.amount_max
        ? `di ${formatAmount(rule.amount_min)}`
        : `da ${formatAmount(rule.amount_min)} a ${formatAmount(rule.amount_max)}`,
    );
  } else if (rule.amount_min !== null) {
    parts.push(`da ${formatAmount(rule.amount_min)} in su`);
  } else if (rule.amount_max !== null) {
    parts.push(`fino a ${formatAmount(rule.amount_max)}`);
  }
  return parts.length === 0 ? null : parts.join(" · ");
}

/** What a rule with no category or tag to sit under does, said in a line. */
function actionText(rule: Rule): string {
  return rule.action === "delete" ? "Cancella" : `Giroconto verso ${rule.target ?? ""}`;
}

const EMPTY_DRAFT: RuleDraft = {
  pattern: "",
  action: "category",
  target: null,
  account_id: null,
  amount_min: null,
  amount_max: null,
};

interface RuleRowsProps {
  rules: Rule[];
  onOpen: (rule: Rule) => void;
  /** What the row says beyond its text and conditions, where that is not obvious. */
  does?: (rule: Rule) => string;
}

/** A rule is a line: its text and how many it holds. The rest opens on a tap. */
function RuleRows({ rules, onOpen, does }: RuleRowsProps) {
  return (
    <ul className="rule-lines">
      {rules.map((rule) => {
        const detail = [does?.(rule), conditionsText(rule)].filter(Boolean).join(" · ");
        return (
          <li key={rule.id}>
            <button type="button" className="rule-line" onClick={() => onOpen(rule)}>
              <span className="rule-line__text">
                <span className="rule-row__pattern">{rule.pattern}</span>
                {detail === "" ? null : <span className="rule-line__detail">{detail}</span>}
              </span>
              <span className="rule-row__count">{rule.count}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

interface LabelRowProps {
  name: string;
  movements: number;
  episodic: boolean;
  essential: boolean;
  open: boolean;
  onToggle: () => void;
  busy: boolean;
  onFlag: (flags: CategoryFlags) => void;
  rules: Rule[];
  onOpenRule: (rule: Rule) => void;
  onAddRule: (text: string) => Promise<boolean>;
  /** The rule's failure, shown where its text was typed. */
  error: string | null;
  children?: ReactNode;
}

/**
 * A category and a tag are the same thing on this screen: a name, how many
 * movements it holds, the two flags, the texts that fill it. One control, so
 * "rare" is learnt once.
 */
function LabelRow({
  name,
  movements,
  episodic,
  essential,
  open,
  onToggle,
  busy,
  onFlag,
  rules,
  onOpenRule,
  onAddRule,
  error,
  children,
}: LabelRowProps) {
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);

  const add = async () => {
    if (text.trim() === "" || saving) return;
    setSaving(true);
    if (await onAddRule(text.trim())) setText("");
    setSaving(false);
  };

  return (
    <li className="label-row">
      <button type="button" className="label-row__head" aria-expanded={open} onClick={onToggle}>
        <span className="label-row__name">{name}</span>
        {episodic ? <span className="chip chip--tag">Spesa rara</span> : null}
        {essential ? <span className="chip chip--tag">Irrinunciabile</span> : null}
        <span className="label-row__count">{movements}</span>
      </button>

      {open ? (
        <div className="label-row__body">
          <div className="rule-group__flags">
            <Toggle
              label="Spesa rara"
              ariaLabel={`Spesa rara ${name}`}
              checked={episodic}
              disabled={busy}
              onChange={(next) => onFlag({ episodic: next })}
            />
            <Toggle
              label="Irrinunciabile"
              ariaLabel={`Irrinunciabile ${name}`}
              checked={essential}
              disabled={busy}
              onChange={(next) => onFlag({ essential: next })}
            />
          </div>
          {rules.length === 0 ? null : <RuleRows rules={rules} onOpen={onOpenRule} />}
          <form
            className="rule-add"
            onSubmit={(event) => {
              event.preventDefault();
              void add();
            }}
          >
            <input
              className="input"
              type="text"
              autoComplete="off"
              aria-label={`Testo di una nuova regola per ${name}`}
              placeholder="Nuova regola: testo, o /espressione/"
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
            <button type="submit" className="button" disabled={text.trim() === "" || saving}>
              {saving ? "Salvo…" : "Aggiungi"}
            </button>
          </form>
          {error === null ? null : (
            <p className="rule-add__error" role="alert">
              {error}
            </p>
          )}
          {children}
        </div>
      ) : null}
    </li>
  );
}

interface CategoryRulesScreenProps {
  rules: RulesController;
  categories: Category[];
  categoriesError: string | null;
  onReloadCategories: () => void;
  updateCategoryFlags: (id: number, flags: CategoryFlags) => Promise<string | null>;
}

/**
 * Where a category or a tag is defined and where what falls into it is decided.
 * The list is the categories; what is not a category sits in two closed blocks
 * under it, and every explanation lives in the Guide.
 */
export function CategoryRulesScreen({
  rules,
  categories,
  categoriesError,
  onReloadCategories,
  updateCategoryFlags,
}: CategoryRulesScreenProps) {
  const tags = useTags();
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState<"category" | "tag" | null>(null);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  // One row open at a time, whichever list it is in: a key per kind and name.
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [failedFor, setFailedFor] = useState<string | null>(null);
  const [confirmingTag, setConfirmingTag] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // The rule open in the editor: a new one, or a saved one being changed.
  const [editing, setEditing] = useState<{ title: string; draft: RuleDraft } | null>(null);

  const needle = query.trim().toLowerCase();
  const matches = (text: string | null) => (text ?? "").toLowerCase().includes(needle);

  const rulesOf = (action: RuleAction, target: string) =>
    rules.rules.filter((rule) => rule.action === action && rule.target === target);

  // A search keeps the names it matched, and inside the others only the texts
  // it matched, so one pattern in a hundred is still found.
  const entry = <T extends { name: string }>(item: T, action: RuleAction, shownName: string) => {
    const own = rulesOf(action, item.name);
    const named = needle === "" || matches(shownName);
    const shown = named ? own : own.filter((rule) => matches(rule.pattern));
    return { item, own, shown, visible: named || shown.length > 0 };
  };

  const categoryEntries = useMemo(
    () =>
      categories
        .filter((item) => item.name !== bucketName())
        .map((item) => entry(item, "category", categoryText(item.name)))
        .filter((row) => row.visible)
        .sort((left, right) =>
          categoryText(left.item.name).localeCompare(categoryText(right.item.name), "it"),
        ),
    [categories, rules.rules, needle],
  );

  const tagEntries = useMemo(
    () =>
      tags.tags.map((item) => entry(item, "tag", item.name)).filter((row) => row.visible),
    [tags.tags, rules.rules, needle],
  );

  const otherRules = useMemo(
    () =>
      rules.rules.filter(
        (rule) =>
          (rule.action === "delete" || rule.action === "transfer") &&
          (needle === "" || matches(rule.pattern) || matches(rule.target)),
      ),
    [rules.rules, needle],
  );

  const toggleRow = (key: string) => {
    setFailedFor(null);
    setConfirmingTag(null);
    setOpenRow(openRow === key ? null : key);
  };

  const create = async () => {
    const name = newName.trim();
    if (name === "" || busy || creating === null) return;
    setBusy(true);
    setNotice(null);
    try {
      if (creating === "category") {
        await api.createCategory(name);
        onReloadCategories();
        setOpenRow(`category:${name}`);
      } else {
        await api.createTag(name);
        tags.reload();
        setOpenRow(`tag:${name}`);
      }
      setNewName("");
      setCreating(null);
    } catch (caught) {
      setNotice(`Non creato: ${errorMessage(caught)}`);
    } finally {
      setBusy(false);
    }
  };

  const setFlags = async (update: () => Promise<string | null>) => {
    setBusy(true);
    setNotice(null);
    const message = await update();
    setBusy(false);
    if (message !== null) setNotice(`Non aggiornato: ${message}`);
  };

  const addRule = async (key: string, action: RuleAction, target: string, text: string) => {
    setFailedFor(null);
    const failed = await rules.add({ ...EMPTY_DRAFT, pattern: text, action, target });
    setFailedFor(failed === null ? null : key);
    if (failed === null && action === "tag") tags.reload();
    return failed === null;
  };

  const openRule = (rule: Rule) =>
    setEditing({ title: `La regola «${rule.pattern}»`, draft: draftOf(rule) });

  const saveEdited = async (draft: RuleDraft): Promise<string | null> => {
    const failed = await rules.add(draft);
    if (failed !== null) return failed;
    setEditing(null);
    setNotice(`Regola salvata: «${draft.pattern}»`);
    onReloadCategories();
    tags.reload();
    return null;
  };

  const removeEdited = async (id: number): Promise<string | null> => {
    const held = await rules.remove(id);
    if (held === null) return rules.operationError ?? "regola non rimossa";
    setEditing(null);
    setNotice(`Regola rimossa: ${plural(held, "movimento lasciato", "movimenti lasciati")} alle altre regole`);
    tags.reload();
    return null;
  };

  const deleteTag = async (id: number, name: string) => {
    setBusy(true);
    try {
      await api.deleteTag(id);
      setConfirmingTag(null);
      setOpenRow(null);
      setNotice(`Tag eliminato: ${name}`);
      tags.reload();
      rules.reload();
    } catch (caught) {
      setNotice(`Tag non eliminato: ${errorMessage(caught)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">
            Categorie e regole <Help topic="rule" label="regola" />
          </h1>
        </div>
        <div className="screen__actions">
          <button
            type="button"
            className="button"
            aria-expanded={creating === "category"}
            onClick={() => setCreating(creating === "category" ? null : "category")}
          >
            Nuova categoria
          </button>
          <button
            type="button"
            className="button button--primary"
            onClick={() => setEditing({ title: "Nuova regola", draft: EMPTY_DRAFT })}
          >
            Nuova regola
          </button>
        </div>
      </header>

      {rules.loadError ? (
        <div className="state state--error" role="alert">
          <p>{rules.loadError}</p>
          <button type="button" className="button" onClick={rules.reload}>
            Riprova
          </button>
        </div>
      ) : null}

      {notice !== null ? <p className="state">{notice}</p> : null}

      <input
        className="input"
        type="search"
        placeholder="Cerca categoria, tag o testo…"
        aria-label="Cerca fra categorie, tag e regole"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />

      {creating === "category" ? (
        <form
          className="rule-add"
          onSubmit={(event) => {
            event.preventDefault();
            void create();
          }}
        >
          <input
            className="input"
            type="text"
            autoComplete="off"
            aria-label="Nome della nuova categoria"
            placeholder="Nome della categoria"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            autoFocus
          />
          <button type="submit" className="button button--primary" disabled={newName.trim() === "" || busy}>
            Crea
          </button>
        </form>
      ) : null}

      {categoriesError !== null ? (
        <div className="state state--error" role="alert">
          <p>Impossibile caricare le categorie: {categoriesError}</p>
          <button type="button" className="button" onClick={onReloadCategories}>
            Riprova
          </button>
        </div>
      ) : rules.loading && rules.rules.length === 0 ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : categoryEntries.length === 0 ? (
        <p className="state">Nessuna categoria per questa ricerca.</p>
      ) : (
        <ul className="flag-list">
          {categoryEntries.map(({ item, own, shown }) => {
            const key = `category:${item.name}`;
            return (
              <LabelRow
                key={item.id}
                name={categoryText(item.name)}
                movements={own.reduce((sum, rule) => sum + rule.count, 0)}
                episodic={item.episodic}
                essential={item.essential}
                open={openRow === key || (needle !== "" && shown.length > 0)}
                onToggle={() => toggleRow(key)}
                busy={busy}
                onFlag={(flags) => void setFlags(() => updateCategoryFlags(item.id, flags))}
                rules={shown}
                onOpenRule={openRule}
                onAddRule={(text) => addRule(key, "category", item.name, text)}
                error={failedFor === key ? rules.operationError : null}
              />
            );
          })}
        </ul>
      )}

      <details className="manage-block" open={needle !== "" && tagEntries.length > 0 ? true : undefined}>
        <summary>
          Tag <span className="count">{tags.tags.length}</span>
        </summary>
        <div className="manage-block__body">
          <div className="manage-block__actions">
            <Help topic="tag" label="tag" />
            <button
              type="button"
              className="button"
              aria-expanded={creating === "tag"}
              onClick={() => setCreating(creating === "tag" ? null : "tag")}
            >
              Nuovo tag
            </button>
          </div>
          {creating === "tag" ? (
            <form
              className="rule-add"
              onSubmit={(event) => {
                event.preventDefault();
                void create();
              }}
            >
              <input
                className="input"
                type="text"
                autoComplete="off"
                aria-label="Nome del nuovo tag"
                placeholder="Nome del tag"
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
              <button type="submit" className="button button--primary" disabled={newName.trim() === "" || busy}>
                Crea
              </button>
            </form>
          ) : null}
          {tagEntries.length === 0 ? null : (
            <ul className="flag-list">
              {tagEntries.map(({ item, shown }) => {
                const key = `tag:${item.name}`;
                return (
                  <LabelRow
                    key={item.id}
                    name={item.name}
                    movements={item.movements}
                    episodic={item.episodic}
                    essential={item.essential}
                    open={openRow === key || (needle !== "" && shown.length > 0)}
                    onToggle={() => toggleRow(key)}
                    busy={busy}
                    onFlag={(flags) => void setFlags(() => tags.updateFlags(item.id, flags))}
                    rules={shown}
                    onOpenRule={openRule}
                    onAddRule={(text) => addRule(key, "tag", item.name, text)}
                    error={failedFor === key ? rules.operationError : null}
                  >
                    {confirmingTag === item.id ? (
                      <div className="rule-row__confirm">
                        <p>Sicuro? Il tag sparisce da {plural(item.movements, "movimento", "movimenti")}, con le sue regole</p>
                        <button
                          type="button"
                          className="button button--danger"
                          onClick={() => void deleteTag(item.id, item.name)}
                          disabled={busy}
                        >
                          Elimina
                        </button>
                        <button type="button" className="button" onClick={() => setConfirmingTag(null)}>
                          No
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="button button--danger"
                        onClick={() => setConfirmingTag(item.id)}
                      >
                        Elimina il tag
                      </button>
                    )}
                  </LabelRow>
                );
              })}
            </ul>
          )}
        </div>
      </details>

      <details className="manage-block" open={needle !== "" && otherRules.length > 0 ? true : undefined}>
        <summary>
          Altre regole <span className="count">{otherRules.length}</span>
        </summary>
        <div className="manage-block__body">
          <RuleRows rules={otherRules} onOpen={openRule} does={actionText} />
        </div>
      </details>

      {editing === null ? null : (
        <RuleSheet
          title={editing.title}
          initial={editing.draft}
          categories={categories}
          onSave={saveEdited}
          onRemove={
            typeof editing.draft.id === "number"
              ? () => removeEdited(editing.draft.id as number)
              : undefined
          }
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}
