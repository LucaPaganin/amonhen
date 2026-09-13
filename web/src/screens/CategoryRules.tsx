import { useMemo, useState } from "react";

import { api, errorMessage } from "../api";
import { bucketName, categoryText } from "../category";
import { Toggle } from "../components/Toggle";
import type { Category, Rule } from "../types";
import type { CategoryFlags } from "../useCategories";
import type { RulesController } from "../useRules";

/** One is a singular in Italian, and the count is read out loud in the row. */
function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

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
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [confirming, setConfirming] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
          const own = rules.rules.filter((rule) => rule.category === item.name);
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
    const saved = await rules.add(text, item.name);
    setSavingFor(null);
    if (saved) setDrafts((current) => ({ ...current, [item.name]: "" }));
  };

  const changeCategory = (rule: Rule, next: string) => {
    setNotice(null);
    void rules.add(rule.pattern, next);
  };

  const confirmRemove = async (rule: Rule) => {
    const held = await rules.remove(rule.pattern);
    setConfirming(null);
    if (held !== null) {
      setNotice(`Regola rimossa: ${plural(held, "movimento", "movimenti")} alle altre regole, o in coda`);
    }
  };

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

      {rules.operationError ? (
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
        <em>Episodica</em> dice che ci finisce un fatto raro, la cui spesa si accantona invece di
        entrare nella media; <em>Incomprimibile</em> che è la parte di spesa che non si taglierebbe.
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
                      label="Episodica"
                      ariaLabel={`Episodica ${name}`}
                      checked={entry.category.episodic}
                      disabled={busy}
                      onChange={(next) => void toggleFlag(entry.category, "episodic", next)}
                    />
                    <Toggle
                      label="Incomprimibile"
                      ariaLabel={`Incomprimibile ${name}`}
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
                        Nessuna regola per questa categoria: ne nasce una accettando una proposta in
                        coda, oppure si scrive qui sotto.
                      </p>
                    ) : (
                      <ul className="rule-group__rules">
                        {entry.rules.map((rule) => (
                          <li className="rule-row" key={rule.pattern}>
                            <div className="rule-row__head">
                              <span className="rule-row__pattern">{rule.pattern}</span>
                              <span className="rule-row__count">
                                {plural(rule.count, "movimento", "movimenti")}
                              </span>
                            </div>
                            <div className="rule-row__controls">
                              <select
                                className="input"
                                aria-label={`Categoria per ${rule.pattern}`}
                                value={rule.category}
                                disabled={options.length === 0}
                                onChange={(event) => changeCategory(rule, event.target.value)}
                              >
                                {options.map((item) => (
                                  <option key={item.id} value={item.name}>
                                    {item.name}
                                  </option>
                                ))}
                              </select>

                              {confirming === rule.pattern ? (
                                <div className="rule-row__confirm">
                                  <p>
                                    Sicuro? La regola lascia{" "}
                                    {plural(rule.count, "movimento", "movimenti")} alle altre regole, o
                                    in coda
                                  </p>
                                  <button
                                    type="button"
                                    className="button button--danger"
                                    onClick={() => void confirmRemove(rule)}
                                  >
                                    Rimuovi
                                  </button>
                                  <button
                                    type="button"
                                    className="button"
                                    onClick={() => setConfirming(null)}
                                  >
                                    Annulla
                                  </button>
                                </div>
                              ) : (
                                <button
                                  type="button"
                                  className="button button--danger"
                                  onClick={() => setConfirming(rule.pattern)}
                                >
                                  Rimuovi
                                </button>
                              )}
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
                        placeholder="Nuova regola: testo nella descrizione"
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
        combaciano vince il più lungo. Correggere una regola sposta i movimenti che teneva;
        rimuoverla li lascia alla regola più ampia che combacia ancora, o in coda.
      </p>

    </section>
  );
}
