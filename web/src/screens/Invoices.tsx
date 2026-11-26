import { useCallback, useEffect, useId, useState } from "react";

import { api, errorMessage } from "../api";
import { formatAmount, formatDateWithYear } from "../format";
import type { Invoice, InvoicePage, Transaction } from "../types";

/** The invoices and receipts Paperless holds, and the payment each one justifies. */
export function InvoicesScreen({ refreshToken }: { refreshToken: number }) {
  const [page, setPage] = useState<InvoicePage | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [linking, setLinking] = useState<Invoice | null>(null);

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
