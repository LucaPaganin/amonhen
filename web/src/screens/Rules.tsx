import { useMemo, useState } from "react";

import type { Category, Rule } from "../types";
import type { RulesController } from "../useRules";

/** One is a singular in Italian, and the count is read out loud in the row. */
function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

interface RulesScreenProps {
  rules: RulesController;
  categories: Category[];
  categoriesError: string | null;
  onReloadCategories: () => void;
}

export function RulesScreen({
  rules,
  categories,
  categoriesError,
  onReloadCategories,
}: RulesScreenProps) {
  const [pattern, setPattern] = useState("");
  const [category, setCategory] = useState("");
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [removed, setRemoved] = useState<string | null>(null);

  const total = useMemo(
    () => rules.rules.reduce((sum, rule) => sum + rule.count, 0),
    [rules.rules],
  );

  const needle = query.trim().toLowerCase();
  const visible = useMemo(
    () =>
      needle === ""
        ? rules.rules
        : rules.rules.filter(
            (rule) =>
              rule.pattern.toLowerCase().includes(needle) ||
              rule.category.toLowerCase().includes(needle),
          ),
    [rules.rules, needle],
  );

  const canAdd = pattern.trim() !== "" && category !== "" && !saving;

  // A rule that points at the review bucket would take movements out of the
  // queue without categorizing them; the API refuses it too.
  const options = categories.filter((item) => item.name !== "Uncategorized");

  const submit = async () => {
    if (!canAdd) return;
    setSaving(true);
    setRemoved(null);
    const saved = await rules.add(pattern.trim(), category);
    setSaving(false);
    if (saved) {
      setPattern("");
      setCategory("");
    }
  };

  const changeCategory = (rule: Rule, next: string) => {
    setRemoved(null);
    void rules.add(rule.pattern, next);
  };

  const confirmRemove = async (rule: Rule) => {
    const held = await rules.remove(rule.pattern);
    setConfirming(null);
    if (held !== null) {
      setRemoved(`Regola rimossa: ${plural(held, "movimento", "movimenti")} alle altre regole, o in coda`);
    }
  };

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Regole</h1>
          <p className="screen__subtitle">
            {rules.loading && rules.rules.length === 0
              ? "Caricamento…"
              : `${plural(rules.rules.length, "regola", "regole")} · ${plural(total, "movimento categorizzato", "movimenti categorizzati")}`}
          </p>
        </div>
        <div className="screen__actions">
          <button type="button" className="button" onClick={rules.reload} disabled={rules.loading}>
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

      {removed ? <p className="state">{removed}</p> : null}

      <section className="panel">
        <h2 className="section-title">Nuova regola</h2>
        {categoriesError ? (
          <div className="state state--error" role="alert">
            <p>Impossibile caricare le categorie: {categoriesError}</p>
            <button type="button" className="button" onClick={onReloadCategories}>
              Riprova
            </button>
          </div>
        ) : (
          <>
            <form
              className="filters"
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
            >
              <div className="field">
                <label htmlFor="rule-pattern">Testo nella descrizione</label>
                <input
                  id="rule-pattern"
                  className="input"
                  type="text"
                  autoComplete="off"
                  placeholder="es. addebito sdd, ipercoop, amazon prime"
                  value={pattern}
                  onChange={(event) => setPattern(event.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="rule-category">Categoria</label>
                <select
                  id="rule-category"
                  className="input"
                  value={category}
                  disabled={options.length === 0}
                  onChange={(event) => setCategory(event.target.value)}
                >
                  <option value="">Scegli una categoria</option>
                  {options.map((item) => (
                    <option key={item.id} value={item.name}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </div>
              <button type="submit" className="button button--primary" disabled={!canAdd}>
                {saving ? "Salvo…" : "Aggiungi"}
              </button>
            </form>
            <p className="chart-note">
              Vale per ogni movimento la cui descrizione contiene questo testo, senza badare alle
              maiuscole: «addebito sdd» li prende tutti, «amazon prime» solo quelli. La regola
              categorizza subito anche i movimenti già importati che aspettavano in coda.
            </p>
          </>
        )}
      </section>

      {rules.rules.length > 0 ? (
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
      ) : null}

      {rules.loading && rules.rules.length === 0 ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : rules.rules.length === 0 ? (
        <p className="state state--empty">
          Nessuna regola. Accettando una proposta dalla coda ne nasce una, oppure creane una qui.
        </p>
      ) : visible.length === 0 ? (
        <p className="state">Nessuna regola per questa ricerca.</p>
      ) : (
        <ul className="card-list">
          {visible.map((rule) => (
            <li className="card rule-row" key={rule.pattern}>
              <div className="rule-row__head">
                <span className="rule-row__pattern">{rule.pattern}</span>
                <span className="rule-row__count">{plural(rule.count, "movimento", "movimenti")}</span>
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
                    <p>Sicuro? La regola lascia {plural(rule.count, "movimento", "movimenti")} alle altre regole, o in coda</p>
                    <button
                      type="button"
                      className="button button--danger"
                      onClick={() => void confirmRemove(rule)}
                    >
                      Rimuovi
                    </button>
                    <button type="button" className="button" onClick={() => setConfirming(null)}>
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
      )}

      <p className="chart-note">
        Un movimento prende la categoria della regola che lo spiega; se due testi combaciano vince il
        più lungo. Correggere una regola sposta i movimenti che teneva, rimuoverla li lascia alla
        regola più ampia che combacia ancora, o in coda.
      </p>
    </section>
  );
}
