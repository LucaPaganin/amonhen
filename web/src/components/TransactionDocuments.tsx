import { useEffect, useId, useState } from "react";

import { api, errorMessage } from "../api";
import { formatDateWithYear } from "../format";
import type { PaperlessHit, Transaction, TransactionDocument } from "../types";

/** The paperwork behind a movement: what Paperless holds for it, found by a search. */
export function TransactionDocuments({
  transaction,
  onChanged,
}: {
  transaction: Transaction;
  onChanged: (transaction: Transaction) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PaperlessHit[] | null>(null);
  const [configured, setConfigured] = useState(true);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fieldId = useId();

  // What a person remembers first: who was paid.
  useEffect(() => {
    if (!open) return;
    setQuery(transaction.counterparty ?? transaction.merchant ?? transaction.description);
  }, [open, transaction.counterparty, transaction.merchant, transaction.description]);

  useEffect(() => {
    if (!open) return;
    let live = true;
    const timer = setTimeout(() => {
      setBusy(true);
      api
        .searchDocuments(query)
        .then((found) => {
          if (!live) return;
          setConfigured(found.configured);
          setHits(found.items);
          setProblem(null);
        })
        .catch((err) => live && setProblem(errorMessage(err)))
        .finally(() => live && setBusy(false));
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [open, query]);

  const attach = async (hit: PaperlessHit) => {
    try {
      onChanged(await api.linkDocument(transaction.id, hit.paperless_id));
      setOpen(false);
      setHits(null);
      setProblem(null);
    } catch (err) {
      setProblem(errorMessage(err));
    }
  };

  const detach = async (document: TransactionDocument) => {
    try {
      onChanged(await api.unlinkDocument(transaction.id, document.paperless_id));
    } catch (err) {
      setProblem(errorMessage(err));
    }
  };

  return (
    <section className="txn-documents">
      <h3 className="section-title">Fatture e ricevute</h3>
      {transaction.documents.length === 0 ? (
        <p className="hint">Nessun documento collegato.</p>
      ) : (
        <ul className="trash-list">
          {transaction.documents.map((document) => (
            <li key={document.paperless_id} className="services__payment">
              <span>
                {document.created === null ? "" : `${formatDateWithYear(document.created)} · `}
                {document.title}
                {document.kind === null ? "" : <span className="hint"> · {document.kind}</span>}
              </span>
              <button type="button" className="button button--ghost"
                onClick={() => void detach(document)}>
                Scollega
              </button>
            </li>
          ))}
        </ul>
      )}

      {!open ? (
        <div className="account-row__actions">
          <button type="button" className="button" onClick={() => setOpen(true)}>
            Collega una fattura
          </button>
        </div>
      ) : (
        <div className="services__picker">
          <div className="field">
            <label htmlFor={`${fieldId}-q`}>Cerca in Paperless</label>
            <input id={`${fieldId}-q`} className="input" autoFocus value={query}
              placeholder="emittente, importo o mese"
              onChange={(event) => setQuery(event.target.value)} />
          </div>
          {problem !== null ? <p className="account-form__error" role="alert">{problem}</p> : null}
          {!configured ? (
            <p className="hint">
              Paperless non è configurato: servono AMONHEN_PAPERLESS_URL e AMONHEN_PAPERLESS_TOKEN.
            </p>
          ) : hits === null ? (
            <p className="hint" aria-busy="true">Cerco…</p>
          ) : hits.length === 0 ? (
            <p className="hint">Nessun documento con questa ricerca.</p>
          ) : (
            <ul className="trash-list">
              {hits.map((hit) => (
                <li key={hit.paperless_id} className="services__payment">
                  <span>
                    {hit.created === null ? "" : `${formatDateWithYear(hit.created)} · `}
                    {hit.title}
                    {hit.correspondent === null ? "" : <span className="hint"> · {hit.correspondent}</span>}
                    {hit.kind === null ? "" : <span className="hint"> · {hit.kind}</span>}
                  </span>
                  <button type="button" className="button button--primary"
                    onClick={() => void attach(hit)}>
                    Collega
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="account-row__actions">
            <span className="hint">{busy ? "aggiorno…" : ""}</span>
            <button type="button" className="button button--ghost" onClick={() => {
              setOpen(false);
              setHits(null);
            }}>
              Chiudi
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
