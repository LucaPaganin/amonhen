import { useMemo, useState } from "react";

import { api, errorMessage } from "../api";
import { bucketName, categoryText } from "../category";
import { RuleSheet, draftOf } from "../components/RuleSheet";
import { Toggle } from "../components/Toggle";
import { formatAmount } from "../format";
import type { Category, Rule, RuleDraft } from "../types";
import type { CategoryFlags } from "../useCategories";
import type { RulesController } from "../useRules";

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

/** What a rule that does not assign a category does, said in a line. */
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

interface CategoryRulesScreenProps {
  rules: RulesController;
  categories: Category[];
  categoriesError: string | null;
  onReloadCategories: () => void;
  updateCategoryFlags: (id: number, flags: CategoryFlags) => Promise<string | null>;
}

/**
 * Where a category is defined and where what falls into it is decided: one
 * entry per category carries its two flags and the rules that assign it, which
 * open inside it. A category and the rules that fill it are the same decision
 * seen from its two ends, so they are one screen and one list.
 */
function needleOf(query: string): string {
  return query.trim().toLowerCase();
}

export function CategoryRulesScreen({
  rules,
  categories,
  categoriesError,
  onReloadCategories,
  updateCategoryFlags,
}: CategoryRulesScreenProps) {
  const [newCategory, setNewCategory] = useState("");
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState<number[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingFor, setSavingFor] = useState<string | null>(null);
  // The form's own failure — a pattern the ledger refuses — belongs where the
  // text was typed: the shared box sits at the top of a screen the reader has
  // scrolled past to write the rule.
  const [failedFor, setFailedFor] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [confirming, setConfirming] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // The rule open in the editor: a new one, or a saved one being changed.
  const [editing, setEditing] = useState<{ title: string; draft: RuleDraft } | null>(null);

  // The rules that do something other than assign a category have no category
  // to sit under, so they are a list of their own above the categories.
  const actionRules = useMemo(
    () =>
      rules.rules.filter(
        (rule) =>
          rule.action !== "category" &&
          (needleOf(query) === "" ||
            rule.pattern.toLowerCase().includes(needleOf(query)) ||
            (rule.target ?? "").toLowerCase().includes(needleOf(query))),
      ),
    [rules.rules, query],
  );

  const total = useMemo(
    () => rules.rules.reduce((sum, rule) => sum + rule.count, 0),
    [rules.rules],
  );

  const needle = query.trim().toLowerCase();

  // Each category is an entry, and the texts that assign it are what opens
  // inside: a search keeps the categories it matched, and inside them only the
  // rules that matched, so one pattern in forty-five is still found — and a
  // category is on the screen whether or not a rule points at it yet.
  const entries = useMemo(
    () =>
      categories
        .map((item) => {
          const own = rules.rules.filter(
            (rule) => rule.action === "category" && rule.category === item.name,
          );
          const named = needle !== "" && categoryText(item.name).toLowerCase().includes(needle);
          const shown =
            needle === "" || named
              ? own
              : own.filter((rule) => rule.pattern.toLowerCase().includes(needle));
          return {
            category: item,
            rules: shown,
            movements: shown.reduce((sum, rule) => sum + rule.count, 0),
            visible: needle === "" || named || shown.length > 0,
          };
        })
        .filter((entry) => entry.visible)
        .sort((left, right) =>
          categoryText(left.category.name).localeCompare(categoryText(right.category.name), "it"),
        ),
    [categories, rules.rules, needle],
  );

  // A rule that points at the review bucket would take movements out of the
  // queue without categorizing them; the API refuses it too.
  const options = categories.filter((item) => item.name !== bucketName());

  // Creating a category categorizes nothing by itself: it is a place movements
  // can be pointed at, and they get there through a proposal, a rule or a hand.
  const createCategory = async () => {
    const name = newCategory.trim();
    if (name === "" || creating) return;
    setCreating(true);
    setNotice(null);
    try {
      await api.createCategory(name);
      setNewCategory("");
      onReloadCategories();
      setNotice(`Categoria creata: ${name}`);
    } catch (caught) {
      setNotice(`Categoria non creata: ${errorMessage(caught)}`);
    } finally {
      setCreating(false);
    }
  };

  const toggleFlag = async (item: Category, flag: "episodic" | "essential", next: boolean) => {
    if (pending.includes(item.id)) return;
    setNotice(null);
    setPending((current) => [...current, item.id]);
    const message = await updateCategoryFlags(
      item.id,
      flag === "episodic" ? { episodic: next } : { essential: next },
    );
    setPending((current) => current.filter((id) => id !== item.id));
    if (message !== null) setNotice(`Categoria non aggiornata: ${message}`);
  };

  // The group is the form: a rule assigns the category it sits under, so the
  // text goes where the rules it will join are, and the category is the one
  // whose head was opened.
  const addRule = async (item: Category) => {
    const text = (drafts[item.name] ?? "").trim();
    if (text === "" || savingFor !== null) return;
    setSavingFor(item.name);
    setNotice(null);
    setFailedFor(null);
    const failed = await rules.add({ ...EMPTY_DRAFT, pattern: text, target: item.name });
    setSavingFor(null);
    setFailedFor(failed === null ? null : item.name);
    if (failed === null) setDrafts((current) => ({ ...current, [item.name]: "" }));
  };

  const changeCategory = (rule: Rule, next: string) => {
    setNotice(null);
    setFailedFor(null);
    void rules.add({ ...draftOf(rule), target: next });
  };

  const confirmRemove = async (rule: Rule) => {
    setFailedFor(null);
    const held = await rules.remove(rule.id);
    setConfirming(null);
    if (held === null) return;
    setNotice(
      rule.action === "delete"
        ? `Regola rimossa: ${plural(held, "movimento cancellato", "movimenti cancellati")} da lei restano nel cestino, e ora si possono ripristinare`
        : `Regola rimossa: ${plural(held, "movimento", "movimenti")} alle altre regole, o in coda`,
    );
  };

  const saveEdited = async (draft: RuleDraft): Promise<string | null> => {
    const failed = await rules.add(draft);
    if (failed !== null) return failed;
    setEditing(null);
    setNotice(`Regola salvata: «${draft.pattern}»`);
    onReloadCategories();
    return null;
  };

  const removeControls = (rule: Rule) =>
    confirming === rule.id ? (
      <div className="rule-row__confirm">
        <p>
          {rule.action === "delete"
            ? "Sicuro? I movimenti che ha cancellato restano nel cestino, e i prossimi non verranno più tolti"
            : `Sicuro? La regola lascia ${plural(rule.count, "movimento", "movimenti")} alle altre regole, o in coda`}
        </p>
        <button type="button" className="button button--danger" onClick={() => void confirmRemove(rule)}>
          Rimuovi
        </button>
        <button type="button" className="button" onClick={() => setConfirming(null)}>
          Annulla
        </button>
      </div>
    ) : (
      <>
        <button
          type="button"
          className="button"
          onClick={() => setEditing({ title: `La regola «${rule.pattern}»`, draft: draftOf(rule) })}
        >
          Modifica
        </button>
        <button type="button" className="button button--danger" onClick={() => setConfirming(rule.id)}>
          Rimuovi
        </button>
      </>
    );

  const reload = () => {
    rules.reload();
    onReloadCategories();
  };

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Categorie e regole</h1>
          <p className="screen__subtitle">
            {rules.loading && rules.rules.length === 0
              ? "Caricamento…"
              : `${plural(categories.length, "categoria", "categorie")} · ${plural(rules.rules.length, "regola", "regole")} · ${plural(total, "movimento", "movimenti")}`}
          </p>
        </div>
        <div className="screen__actions">
          <button
            type="button"
            className="button button--primary"
            onClick={() => setEditing({ title: "Nuova regola", draft: EMPTY_DRAFT })}
          >
            Nuova regola
          </button>
          <button type="button" className="button" onClick={reload} disabled={rules.loading}>
            Aggiorna
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

      {rules.operationError !== null && failedFor === null ? (
        <div className="state state--error" role="alert">
          <p>{rules.operationError}</p>
        </div>
      ) : null}

      {notice !== null ? <p className="state">{notice}</p> : null}

      <form
        className="filters filters--row"
        onSubmit={(event) => {
          event.preventDefault();
          void createCategory();
        }}
      >
        <div className="field">
          <label htmlFor="new-category">Nuova categoria</label>
          <input
            id="new-category"
            className="input"
            type="text"
            autoComplete="off"
            placeholder="es. Salute, Animali, Regali"
            value={newCategory}
            onChange={(event) => setNewCategory(event.target.value)}
          />
        </div>
        <button
          type="submit"
          className="button button--primary"
          disabled={newCategory.trim() === "" || creating}
        >
          {creating ? "Creo…" : "Aggiungi"}
        </button>
      </form>
      <p className="chart-note">
        Una categoria non categorizza niente da sola: è il posto dove i movimenti possono finire.
        <em>Spesa rara</em> dice che ci finisce qualcosa che capita poco (un viaggio, una
        riparazione), che va nella riserva invece che nella spesa tipica; <em>Irrinunciabile</em>
        che è spesa che non taglieresti.
      </p>

      <div className="filters">
        <input
          className="input"
          type="search"
          placeholder="Cerca testo o categoria…"
          aria-label="Cerca fra le regole"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      {actionRules.length > 0 ? (
        <section className="card rule-group" aria-labelledby="action-rules-title">
          <div className="rule-group__head">
            <h2 className="rule-group__category" id="action-rules-title">
              Cancellano o registrano un giroconto
            </h2>
          </div>
          <ul className="rule-group__rules">
            {actionRules.map((rule) => {
              const narrowed = conditionsText(rule);
              return (
                <li className="rule-row" key={rule.id}>
                  <div className="rule-row__head">
                    <span className="rule-row__pattern">{rule.pattern}</span>
                    <span className="rule-row__count">
                      {rule.action === "delete"
                        ? `${plural(rule.count, "movimento", "movimenti")} nel cestino`
                        : plural(rule.count, "movimento", "movimenti")}
                    </span>
                  </div>
                  <p className="rule-row__does">
                    {actionText(rule)}
                    {narrowed === null ? "" : ` · ${narrowed}`}
                  </p>
                  <div className="rule-row__controls">{removeControls(rule)}</div>
                </li>
              );
            })}
          </ul>
        </section>
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
      ) : categories.length === 0 ? (
        <p className="state state--empty">
          Nessuna categoria. Scrivine una qui sopra: è il posto dove i movimenti possono finire.
        </p>
      ) : entries.length === 0 ? (
        <p className="state">Nessuna regola per questa ricerca.</p>
      ) : (
        <ul className="card-list">
          {entries.map((entry) => {
            const name = entry.category.name;
            const open = expanded[name] ?? needle !== "";
            const busy = pending.includes(entry.category.id);
            return (
              <li className="card rule-group" key={entry.category.id}>
                <div className="rule-group__head">
                  <button
                    type="button"
                    className="rule-group__toggle"
                    aria-expanded={open}
                    onClick={() => setExpanded({ ...expanded, [name]: !open })}
                  >
                    <span className="rule-group__chevron" aria-hidden="true">
                      {open ? "▾" : "▸"}
                    </span>
                    <span className="rule-group__category">{categoryText(name)}</span>
                    <span className="rule-group__count">
                      {plural(entry.rules.length, "regola", "regole")} ·{" "}
                      {plural(entry.movements, "movimento", "movimenti")}
                    </span>
                  </button>
                  <div className="rule-group__flags">
                    <Toggle
                      label="Spesa rara"
                      ariaLabel={`Spesa rara ${name}`}
                      checked={entry.category.episodic}
                      disabled={busy}
                      onChange={(next) => void toggleFlag(entry.category, "episodic", next)}
                    />
                    <Toggle
                      label="Irrinunciabile"
                      ariaLabel={`Irrinunciabile ${name}`}
                      checked={entry.category.essential}
                      disabled={busy}
                      onChange={(next) => void toggleFlag(entry.category, "essential", next)}
                    />
                  </div>
                </div>

                {open ? (
                  <>
                    {
                    entry.rules.length === 0 ? (
                      <p className="rule-group__empty">
                        Nessuna regola per questa categoria: si scrive qui sotto, o si chiede
                        mentre si accetta una proposta in coda.
                      </p>
                    ) : (
                      <ul className="rule-group__rules">
                        {entry.rules.map((rule) => (
                          <li className="rule-row" key={rule.id}>
                            <div className="rule-row__head">
                              <span className="rule-row__pattern">{rule.pattern}</span>
                              <span className="rule-row__count">
                                {plural(rule.count, "movimento", "movimenti")}
                              </span>
                            </div>
                            {conditionsText(rule) === null ? null : (
                              <p className="rule-row__does">{conditionsText(rule)}</p>
                            )}
                            <div className="rule-row__controls">
                              <select
                                className="input"
                                aria-label={`Categoria per ${rule.pattern}`}
                                value={rule.category ?? ""}
                                disabled={options.length === 0}
                                onChange={(event) => changeCategory(rule, event.target.value)}
                              >
                                {options.map((item) => (
                                  <option key={item.id} value={item.name}>
                                    {item.name}
                                  </option>
                                ))}
                              </select>

                              {removeControls(rule)}
                            </div>
                          </li>
                        ))}
                      </ul>
                    )
                    }
                    <form
                      className="rule-add"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void addRule(entry.category);
                      }}
                    >
                      <label className="visually-hidden" htmlFor={`add-${entry.category.id}`}>
                        Testo di una nuova regola per {categoryText(name)}
                      </label>
                      <input
                        id={`add-${entry.category.id}`}
                        className="input"
                        type="text"
                        autoComplete="off"
                        placeholder="Nuova regola: testo, o /espressione/"
                        value={drafts[name] ?? ""}
                        onChange={(event) =>
                          setDrafts((current) => ({ ...current, [name]: event.target.value }))
                        }
                      />
                      <button
                        type="submit"
                        className="button button--primary"
                        disabled={(drafts[name] ?? "").trim() === "" || savingFor !== null}
                      >
                        {savingFor === name ? "Salvo…" : "Aggiungi"}
                      </button>
                    </form>
                    {failedFor === name && rules.operationError !== null ? (
                      <p className="rule-add__error" role="alert">
                        {rules.operationError}
                      </p>
                    ) : null}
                  </>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      <p className="chart-note">
        Una regola vale per ogni movimento la cui descrizione contiene il suo testo, senza badare
        alle maiuscole: «addebito sdd» li prende tutti, «amazon prime» solo quelli, e se due testi
        combaciano vince il più lungo, testo o espressione che sia. Fra barre è invece
        un'espressione regolare — /amazon (eu|payments)/ prende una famiglia che la banca scrive in
        troppi modi. Correggere una regola sposta i movimenti che teneva; rimuoverla li lascia alla
        regola più ampia che combacia ancora, o in coda. Una regola si può restringere a un conto e a
        un intervallo di importi, e a parità di testo vince quella più ristretta; oltre ad assegnare
        una categoria può cancellare i movimenti, che finiscono nel cestino, o registrarli come
        giroconto verso una destinazione. Se più regole combaciano, cancellare vince su giroconto e
        giroconto su categoria.
      </p>

      {editing === null ? null : (
        <RuleSheet
          title={editing.title}
          initial={editing.draft}
          categories={categories}
          onSave={saveEdited}
          onClose={() => setEditing(null)}
        />
      )}

    </section>
  );
}
