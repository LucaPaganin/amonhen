import { useCallback, useEffect, useId, useState } from "react";

import { api, errorMessage } from "../api";
import { formatAmount, formatDateWithYear, windowText } from "../format";
import type { DocumentRule, Invoice, InvoicePage, Transaction } from "../types";

/** The rule being written: two day counts and an optional word from the description. */
interface RuleDraft {
  correspondent: string;
  before: number;
  after: number;
  match: string;
  active: boolean;
}

/** The invoices and receipts Paperless holds, and the payment each one justifies. */
export function InvoicesScreen({ refreshToken }: { refreshToken: number }) {
  const [page, setPage] = useState<InvoicePage | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [linking, setLinking] = useState<Invoice | null>(null);
  const [rules, setRules] = useState<DocumentRule[]>([]);
  const [draft, setDraft] = useState<RuleDraft | null>(null);
  const [running, setRunning] = useState(false);
  const [savingRule, setSavingRule] = useState(false);

  const loadRules = useCallback(async () => {
    try {
      setRules((await api.documentRules()).rules);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void loadRules();
  }, [loadRules, refreshToken]);

  const runRules = async () => {
    setRunning(true);
    try {
      const result = await api.linkDocuments();
      const parts = [`${result.linked} collegati`];
      if (result.ambiguous.length > 0) parts.push(`${result.ambiguous.length} da scegliere a mano`);
      if (result.skipped > 0) parts.push(`${result.skipped} già a posto`);
      setNotice(`Regole: ${parts.join(", ")}.`);
      await reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  };

  const saveRule = async (rule: RuleDraft) => {
    setSavingRule(true);
    try {
      const written = await api.setDocumentRule(rule.correspondent.trim(), {
        before_days: rule.before, after_days: rule.after,
        match_text: rule.match.trim() === "" ? null : rule.match.trim(),
        active: rule.active,
      });
      setRules((rows) => [...rows.filter((row) => row.correspondent !== written.correspondent), written]
        .sort((a, b) => a.correspondent.localeCompare(b.correspondent)));
      setDraft(null);
      setNotice(`«${written.correspondent}»: ${written.window}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSavingRule(false);
    }
  };

  const removeRule = async (correspondent: string) => {
    try {
      await api.removeDocumentRule(correspondent);
      setRules((rows) => rows.filter((row) => row.correspondent !== correspondent));
      setNotice(`«${correspondent}»: regola rimossa, i suoi documenti si collegano a mano.`);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const load = useCallback(async (text: string) => {
    try {
      setPage(await api.invoices(text, 0));
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void load(query), 250);
    return () => clearTimeout(timer);
  }, [load, query, refreshToken]);

  const more = async () => {
    if (page === null) return;
    try {
      const next = await api.invoices(query, page.items.length);
      setPage({ ...next, items: [...page.items, ...next.items] });
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const reload = async (text = query) => {
    await load(text);
    if (linking !== null) setLinking(null);
  };

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Fatture</h1>
          <p className="screen__subtitle">
            Le fatture, le ricevute e le bollette che hai in Paperless, e il pagamento che le salda.
          </p>
        </div>
        <div className="screen__actions">
          <button type="button" className="button button--primary" disabled={running}
            onClick={() => void runRules()}>
            {running ? "Collego…" : "Collega le fatture"}
          </button>
        </div>
      </header>

      {error !== null ? (
        <div className="state state--error" role="alert">
          <p>Paperless non risponde: {error}</p>
          <button type="button" className="button" onClick={() => void load(query)}>
            Riprova
          </button>
        </div>
      ) : null}
      {notice !== null ? <p className="hint" role="status">{notice}</p> : null}

      {page === null && error === null ? (
        <p className="state" aria-busy="true">Caricamento…</p>
      ) : null}

      {page !== null && !page.configured ? (
        <p className="hint">
          Paperless non è configurato: servono AMONHEN_PAPERLESS_URL e AMONHEN_PAPERLESS_TOKEN.
        </p>
      ) : null}

      {page !== null && page.configured ? (
        <section className="panel">
          <details className="account-row__more" open={draft !== null}>
            <summary>
              Regole di abbinamento
              {rules.length === 0 ? " · nessuna: si collega a mano" : ` · ${rules.length}`}
            </summary>
            <p className="hint">
              Una regola dice quanto vicino al documento deve stare il movimento che lo paga, in giorni
              prima e dopo la data del documento: un pagamento in acconto sta prima, un addebito sta dopo.
              Se il movimento è uno solo, la regola lo collega; se sono due, decide una persona.
            </p>
            <ul className="flag-list">
              {rules.map((rule) => (
                <li key={rule.correspondent} className="flag-row account-row">
                  <div className="account-row__name">
                    {rule.correspondent}
                    <span className="hint">
                      {rule.window}
                      {rule.match_text === null ? "" : ` · descrizione contiene «${rule.match_text}»`}
                      {rule.active ? "" : " · spenta"}
                    </span>
                  </div>
                  <div className="account-row__actions">
                    <button type="button" className="button button--ghost"
                      onClick={() => setDraft({
                        correspondent: rule.correspondent, before: rule.before_days,
                        after: rule.after_days, match: rule.match_text ?? "", active: rule.active,
                      })}>
                      Modifica
                    </button>
                    <button type="button" className="button button--ghost"
                      onClick={() => void removeRule(rule.correspondent)}>
                      Elimina
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            {draft === null ? (
              <button type="button" className="button"
                onClick={() => setDraft({ correspondent: "", before: 0, after: 20, match: "", active: true })}>
                Aggiungi regola
              </button>
            ) : (
              <div className="services__picker">
                <div className="field">
                  <label htmlFor="rule-correspondent">Emittente, come lo chiama Paperless</label>
                  <input id="rule-correspondent" className="input" value={draft.correspondent}
                    list="rule-correspondents"
                    onChange={(event) => setDraft({ ...draft, correspondent: event.target.value })} />
                  <datalist id="rule-correspondents">
                    {page?.items.map((invoice) => invoice.correspondent).filter(
                      (name): name is string => name !== null && name !== "").filter(
                      (name, index, all) => all.indexOf(name) === index).map((name) => (
                        <option key={name} value={name} />
                      ))}
                  </datalist>
                </div>
                <div className="field">
                  <label htmlFor="rule-before">Giorni prima del documento</label>
                  <input id="rule-before" className="input" type="number" min={0} max={3650}
                    value={draft.before}
                    onChange={(event) => setDraft({ ...draft, before: Number(event.target.value) })} />
                </div>
                <div className="field">
                  <label htmlFor="rule-after">Giorni dopo il documento</label>
                  <input id="rule-after" className="input" type="number" min={0} max={3650}
                    value={draft.after}
                    onChange={(event) => setDraft({ ...draft, after: Number(event.target.value) })} />
                </div>
                <div className="field">
                  <label htmlFor="rule-match">Testo che la descrizione deve contenere (facoltativo)</label>
                  <input id="rule-match" className="input" value={draft.match}
                    placeholder="es. eni, iliad, lenti"
                    onChange={(event) => setDraft({ ...draft, match: event.target.value })} />
                </div>
                <p className="hint" role="status">
                  Il movimento deve stare {windowText(draft.before, draft.after)}.
                </p>
                <div className="account-row__actions">
                  <button type="button" className="button button--primary" disabled={savingRule}
                    onClick={() => void saveRule(draft)}>
                    {savingRule ? "Salvo…" : "Salva regola"}
                  </button>
                  <button type="button" className="button button--ghost" onClick={() => setDraft(null)}>
                    Annulla
                  </button>
                </div>
              </div>
            )}
          </details>

          <div className="field">
            <label htmlFor="invoices-search">Cerca per titolo</label>
            <input id="invoices-search" className="input" value={query}
              placeholder="es. Lenti, bolletta, Unipol"
              onChange={(event) => setQuery(event.target.value)} />
          </div>

          {page.items.length === 0 ? (
            <p className="state">Nessun documento con questa ricerca.</p>
          ) : (
            <ul className="flag-list">
              {page.items.map((invoice) => (
                <li key={invoice.paperless_id} className="flag-row account-row">
                  <div className="account-row__name">
                    {invoice.title}
                    <span className="hint">
                      {invoice.created === null ? "" : `${formatDateWithYear(invoice.created)} · `}
                      {invoice.kind ?? "documento"}
                      {invoice.correspondent === null ? "" : ` · ${invoice.correspondent}`}
                      {invoice.amount === null ? "" : ` · ${formatAmount(invoice.amount)}`}
                      {ruleOf(rules, invoice.correspondent) === null
                        ? ""
                        : ` · ${ruleOf(rules, invoice.correspondent)!.window}`}
                    </span>
                  </div>
                  <div className="account-row__balance">
                    {invoice.movements.length === 0 ? "da collegare" : ""}
                  </div>
                  <div className="invoices__links">
                    {invoice.movements.map((movement) => (
                      <span key={movement.id} className="services__payment">
                        <span>
                          {formatDateWithYear(movement.date)} · {formatAmount(movement.amount)} ·{" "}
                          {movement.description.slice(0, 40)}
                        </span>
                        <button type="button" className="button button--ghost" onClick={async () => {
                          try {
                            await api.unlinkDocument(movement.id, invoice.paperless_id);
                            setNotice(`«${invoice.title}» scollegata dal movimento del ${formatDateWithYear(movement.date)}`);
                            await reload();
                          } catch (err) {
                            setError(errorMessage(err));
                          }
                        }}>
                          Scollega
                        </button>
                      </span>
                    ))}
                    {linking?.paperless_id === invoice.paperless_id ? null : (
                      <button type="button" className="button"
                        onClick={() => setLinking(invoice)}>
                        {invoice.movements.length === 0 ? "Collega a un movimento" : "Collega un altro movimento"}
                      </button>
                    )}
                    {linking?.paperless_id === invoice.paperless_id ? (
                      <MovementPicker
                        invoice={invoice}
                        onCancel={() => setLinking(null)}
                        onLinked={async (movement) => {
                          setNotice(`«${invoice.title}» collegata al movimento del ${formatDateWithYear(movement.date)}`);
                          await reload();
                        }}
                        onError={setError}
                      />
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {page.items.length < page.total ? (
            <button type="button" className="button button--block" onClick={() => void more()}>
              Carica altri ({page.total - page.items.length})
            </button>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

/** The rule of this issuer, when it has one: its window explains a row that stayed alone. */
function ruleOf(rules: DocumentRule[], correspondent: string | null): DocumentRule | null {
  if (correspondent === null) return null;
  return rules.find((rule) => rule.correspondent === correspondent && rule.active) ?? null;
}

/** Finds the movement that pays this document: same issuer, same days, to read. */
function MovementPicker({
  invoice,
  onLinked,
  onCancel,
  onError,
}: {
  invoice: Invoice;
  onLinked: (movement: Transaction) => void;
  onCancel: () => void;
  onError: (message: string) => void;
}) {
  const [query, setQuery] = useState(invoice.correspondent ?? "");
  const [found, setFound] = useState<Transaction[] | null>(null);
  const fieldId = useId();

  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      api
        .transactions({ search: query, limit: 10 })
        .then((page) => live && setFound(page.items))
        .catch((err) => live && onError(errorMessage(err)));
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [query, onError]);

  const attach = async (movement: Transaction) => {
    try {
      await api.linkDocument(movement.id, invoice.paperless_id);
      onLinked(movement);
    } catch (err) {
      onError(errorMessage(err));
    }
  };

  return (
    <div className="services__picker">
      <div className="field">
        <label htmlFor={`${fieldId}-q`}>Movimento che la paga</label>
        <input id={`${fieldId}-q`} className="input" autoFocus value={query}
          placeholder="controparte, descrizione o importo"
          onChange={(event) => setQuery(event.target.value)} />
      </div>
      {found === null ? (
        <p className="hint" aria-busy="true">Cerco…</p>
      ) : found.length === 0 ? (
        <p className="hint">Nessun movimento con questa ricerca.</p>
      ) : (
        <ul className="trash-list">
          {found.map((movement) => (
            <li key={movement.id} className="services__payment">
              <span>
                {formatDateWithYear(movement.date)} · {formatAmount(movement.amount)} ·{" "}
                {movement.counterparty ?? movement.description.slice(0, 48)}
              </span>
              <button type="button" className="button button--primary"
                onClick={() => void attach(movement)}>
                Collega
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="account-row__actions">
        <button type="button" className="button button--ghost" onClick={onCancel}>
          Chiudi
        </button>
      </div>
    </div>
  );
}
