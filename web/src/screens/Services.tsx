import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { MouseEvent } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { Help } from "../components/Help";
import { Toggle } from "../components/Toggle";
import { formatAmount, formatDateWithYear } from "../format";
import type {
  CalendarWindow,
  PaymentCandidatePage,
  ServiceDetail,
  ServiceDraft,
  ServiceSession,
  ServiceSummary,
  SessionState,
} from "../types";

const KINDS = { lezione: "Lezione", seduta: "Seduta", altro: "Altro" } as const;

const STATES: Record<SessionState, string> = {
  pagata: "pagata",
  parziale: "in parte",
  da_pagare: "da pagare",
  futura: "futura",
  annullata: "annullata",
  chiusa: "chiusa a mano",
};

/** What the screen says before the ledger answers: 90 days each way. */
const DEFAULT_WINDOW: CalendarWindow = { start: "", end: "", lookback_days: 90, ahead_days: 90 };

const EMPTY: ServiceDraft = {
  name: "",
  kind: "lezione",
  direction: "entrata",
  rate: "",
  calendar_id: "",
  title_pattern: "",
  match_text: null,
  billing: "sessione",
  default_hours: "1.00",
  recalculate: false,
  lookback_days: null,
  ahead_days: null,
  active: true,
};

/** The balance as a sentence, so its sign never has to be decoded. */
function balanceLine(service: ServiceSummary): string {
  const balance = Number(service.balance);
  if (balance === 0) return "In pari";
  const amount = formatAmount(Math.abs(balance));
  if (service.direction === "entrata") return balance > 0 ? `Ti deve ${amount}` : `Ha pagato ${amount} in anticipo`;
  return balance > 0 ? `Devi ${amount}` : `Hai pagato ${amount} in anticipo`;
}

function day(start: string): string {
  return formatDateWithYear(start.slice(0, 10));
}

/** Desiderata 5.17: services with an agreed price, their sessions from the calendar, and what is left to pay. */
export function ServicesScreen({ refreshToken }: { refreshToken: number }) {
  const [services, setServices] = useState<ServiceSummary[] | null>(null);
  const [configured, setConfigured] = useState(true);
  const [window, setWindow] = useState<CalendarWindow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<ServiceDetail | null>(null);
  const [editing, setEditing] = useState<{ id: number | null; draft: ServiceDraft } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const list = await api.services(signal);
      setServices(list.services);
      setConfigured(list.calendar_configured);
      setWindow(list.default_window);
      setError(null);
    } catch (err) {
      if (!isAbortError(err)) setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, refreshToken]);

  const show = async (id: number) => {
    try {
      setOpen(await api.service(id));
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const changed = (detail: ServiceDetail) => {
    setOpen(detail);
    void load();
  };

  const readCalendars = async () => {
    setSyncing(true);
    try {
      const outcome = await api.syncCalendars();
      setServices(outcome.services);
      const problems = outcome.calendars.filter((item) => item.error !== null);
      const written = outcome.calendars.reduce((total, item) => total + item.written, 0);
      const events = outcome.calendars.reduce((total, item) => total + item.events, 0);
      setWindow(outcome.default_window);
      setNotice(
        problems.length > 0
          ? problems.map((item) => `${item.calendar_id}: ${item.error}`).join(" · ")
          : `${events} eventi letti dal calendario, ${written} sessioni`,
      );
      if (open !== null) setOpen(await api.service(open.id));
    } catch (err) {
      setNotice(errorMessage(err));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Servizi</h1>
          <p className="screen__subtitle">
            Lezioni e sedute dal calendario, e quanto resta da pagare. <Help topic="service" label="servizio" />
          </p>
        </div>
      </header>

      {error !== null ? (
        <div className="state state--error" role="alert">
          <p>Impossibile caricare i servizi: {error}</p>
          <button type="button" className="button" onClick={() => void load()}>
            Riprova
          </button>
        </div>
      ) : null}
      {services === null && error === null ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : null}

      {services === null ? null : (
        <section className="panel">
          <div className="account-row__actions">
            <button type="button" className="button button--primary" onClick={() => setEditing({ id: null, draft: EMPTY })}>
              Nuovo servizio
            </button>
            {services.length > 0 && configured ? (
              <button type="button" className="button" disabled={syncing} onClick={() => void readCalendars()}>
                {syncing ? "Lettura…" : "Leggi i calendari"}
              </button>
            ) : null}
          </div>
          {configured ? null : (
            <p className="hint">
              Nessun service account Google configurato: le sessioni arriveranno quando c'è
              AMONHEN_GOOGLE_SERVICE_ACCOUNT_FILE.
            </p>
          )}
          {notice !== null ? <p className="hint" role="status">{notice}</p> : null}
          {window !== null && configured && services.length > 0 ? (
            <p className="hint">
              Di default una lettura chiede al calendario dal {formatDateWithYear(window.start)} al{" "}
              {formatDateWithYear(window.end)} ({window.lookback_days} giorni indietro,{" "}
              {window.ahead_days} avanti); ogni servizio può avere i suoi.
            </p>
          ) : null}
          {services.length === 0 ? (
            <p className="state">Nessun servizio ancora.</p>
          ) : (
            <ul className="flag-list">
              {services.map((service) => (
                <li className="flag-row account-row" key={service.id}>
                  <button
                    type="button"
                    className="account-row__name services__open"
                    aria-expanded={open?.id === service.id}
                    onClick={() => (open?.id === service.id ? setOpen(null) : void show(service.id))}
                  >
                    {service.name}
                    <span className="hint">
                      {KINDS[service.kind]} · {service.direction === "entrata" ? "dai" : "ricevi"} ·{" "}
                      {service.sessions_unpaid === 0
                        ? `${service.sessions_due} sessioni, tutte coperte`
                        : `${service.sessions_unpaid} di ${service.sessions_due} sessioni non coperte`}
                      {service.lookback_days === null && service.ahead_days === null
                        ? ""
                        : ` · finestra ${service.lookback_days ?? 90}/${service.ahead_days ?? 90} giorni`}
                      {service.active ? "" : " · inattivo"}
                    </span>
                  </button>
                  <span className="account-row__balance">{balanceLine(service)}</span>
                  {open?.id === service.id ? (
                    <ServiceBody
                      detail={open}
                      onChanged={changed}
                      onEdit={() => setEditing({ id: open.id, draft: draftOf(open) })}
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <ServiceSheet
        state={editing}
        defaultWindow={window ?? DEFAULT_WINDOW}
        onClose={() => setEditing(null)}
        onSaved={(detail) => {
          setEditing(null);
          changed(detail);
        }}
      />
    </section>
  );
}

function draftOf(service: ServiceSummary): ServiceDraft {
  const { name, kind, direction, rate, calendar_id, title_pattern, match_text, billing, default_hours, lookback_days, ahead_days, active } = service;
  return {
    name, kind, direction, rate, calendar_id, title_pattern, match_text, billing, default_hours,
    recalculate: false, lookback_days, ahead_days, active,
  };
}

/** One service opened: the sessions with their coverage, the payments, and a link by hand. */
function ServiceBody({
  detail,
  onChanged,
  onEdit,
}: {
  detail: ServiceDetail;
  onChanged: (detail: ServiceDetail) => void;
  onEdit: () => void;
}) {
  const [page, setPage] = useState<PaymentCandidatePage | null>(null);
  const [picking, setPicking] = useState(false);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const pickerId = useId();

  // The search runs while it is typed: a short page the person narrows down is
  // the point, not a wall of movements to scroll.
  useEffect(() => {
    if (!picking) return;
    setSearching(true);
    const timer = setTimeout(() => {
      api.paymentCandidates(detail.id, query, 0)
        .then((found) => {
          setPage(found);
          setProblem(null);
        })
        .catch((err) => setProblem(errorMessage(err)))
        .finally(() => setSearching(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [picking, query, detail.id]);

  const more = async () => {
    if (page === null) return;
    try {
      const next = await api.paymentCandidates(detail.id, query, page.items.length);
      setPage({ items: [...page.items, ...next.items], total: next.total });
    } catch (err) {
      setProblem(errorMessage(err));
    }
  };

  const run = async (action: () => Promise<ServiceDetail | Record<string, never>>) => {
    try {
      const result = await action();
      if ("id" in result) onChanged(result as ServiceDetail);
      setProblem(null);
    } catch (err) {
      setProblem(errorMessage(err));
    }
  };

  const past = [...detail.sessions].reverse();

  return (
    <div className="account-row__more services__body">
      <p className="chart-note">
        Dovuto {formatAmount(detail.due)}, pagato {formatAmount(detail.paid)}{" "}
        <Help topic="coverage" label="saldo e copertura" />
      </p>
      {problem !== null ? <p className="account-form__error" role="alert">{problem}</p> : null}

      <h3 className="section-title">Sessioni</h3>
      {past.length === 0 ? (
        <p className="hint">Nessuna sessione: il calendario non ha eventi con un titolo che contiene «{detail.title_pattern}».</p>
      ) : (
        <div className="plan-scroll">
          <table className="plan-table">
            <thead>
              <tr>
                <th scope="col">Data</th>
                <th scope="col">Durata</th>
                <th scope="col">Importo</th>
                <th scope="col">Stato</th>
                <th scope="col">Azione</th>
              </tr>
            </thead>
            <tbody>
              {past.map((session) => (
                <SessionRow key={session.event_id} session={session}
                  onSave={(amount) => void run(() => api.setSessionAmount(session.event_id, amount))}
                  onClose={(note) => void run(() => api.closeSession(session.event_id, note))}
                  onReopen={() => void run(() => api.reopenSession(session.event_id))} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {detail.cancelled.length === 0 ? null : (
        <details>
          <summary>{detail.cancelled.length} annullate</summary>
          <ul className="trash-list">
            {detail.cancelled.map((session) => (
              <li key={session.event_id}>
                {day(session.start)} · {session.summary || "evento cancellato"}
              </li>
            ))}
          </ul>
        </details>
      )}

      <h3 className="section-title">Pagamenti</h3>
      {detail.payments.length === 0 ? <p className="hint">Nessun pagamento collegato.</p> : (
        <ul className="trash-list">
          {detail.payments.map((payment) => (
            <li key={payment.transaction_id} className="services__payment">
              <span>
                {formatDateWithYear(payment.date)} · {formatAmount(payment.amount)} ·{" "}
                {payment.counterparty ?? payment.description}
                <span className="hint">{payment.by_rule ? " dalla regola" : " a mano"}</span>
              </span>
              <button type="button" className="button button--ghost"
                onClick={() => void run(() => api.linkPayment(payment.transaction_id, null).then(() => api.service(detail.id)))}>
                Scollega
              </button>
            </li>
          ))}
        </ul>
      )}

      {!picking ? (
        <div className="account-row__actions">
          <button type="button" className="button" onClick={() => {
            setPage(null);
            setPicking(true);
          }}>
            Collega un movimento
          </button>
          <button type="button" className="button button--ghost" onClick={onEdit}>
            Modifica il servizio
          </button>
        </div>
      ) : (
        <div className="services__picker">
          <div className="field">
            <label htmlFor={`${pickerId}-query`}>Cerca un movimento</label>
            <input id={`${pickerId}-query`} className="input" value={query} autoFocus
              placeholder="controparte, descrizione o importo"
              onChange={(event) => setQuery(event.target.value)} />
          </div>
          {page === null ? (
            <p className="hint" aria-busy="true">Cerco…</p>
          ) : page.items.length === 0 ? (
            <p className="hint">Nessun movimento non collegato in questo verso con questa ricerca.</p>
          ) : (
            <>
              <ul className="trash-list">
                {page.items.map((candidate) => (
                  <li key={candidate.id} className="services__payment">
                    <span>
                      {formatDateWithYear(candidate.date)} · {formatAmount(candidate.amount)} ·{" "}
                      {candidate.counterparty ?? candidate.description}
                    </span>
                    <button type="button" className="button button--primary" onClick={() => {
                      setPicking(false);
                      setPage(null);
                      setQuery("");
                      void run(() => api.linkPayment(candidate.id, detail.id));
                    }}>
                      Collega
                    </button>
                  </li>
                ))}
              </ul>
              <div className="account-row__actions">
                <span className="hint">
                  {page.items.length} di {page.total}
                  {searching ? " · aggiorno…" : ""}
                </span>
                {page.items.length < page.total ? (
                  <button type="button" className="button button--ghost" onClick={() => void more()}>
                    Mostra altri
                  </button>
                ) : null}
                <button type="button" className="button button--ghost" onClick={() => {
                  setPicking(false);
                  setPage(null);
                }}>
                  Chiudi
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SessionRow({
  session,
  onSave,
  onClose,
  onReopen,
}: {
  session: ServiceSession;
  onSave: (amount: string) => void;
  /** Close it by hand: the note is required, because no movement explains it. */
  onClose: (note: string) => void;
  onReopen: () => void;
}) {
  const [amount, setAmount] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const noteId = useId();
  return (
    <tr>
      <th scope="row">{day(session.start)}</th>
      <td>{session.hours === null ? "—" : `${Number(session.hours)} h`}</td>
      <td>
        {amount === null ? (
          <button type="button" className="services__open services__edit" title="Correggi l'importo"
            onClick={() => setAmount(session.amount)}>
            {formatAmount(session.amount)}
          </button>
        ) : (
          <form onSubmit={(event) => {
            event.preventDefault();
            onSave(amount.replace(",", "."));
            setAmount(null);
          }}>
            <input className="input services__amount" inputMode="decimal" aria-label="Importo della sessione"
              autoFocus value={amount} onChange={(event) => setAmount(event.target.value)}
              onBlur={() => setAmount(null)} />
          </form>
        )}
      </td>
      <td>
        {STATES[session.state]}
        {session.state === "parziale" && session.covered !== undefined
          ? ` (${formatAmount(session.covered)})` : ""}
        {session.state === "chiusa" && session.note !== null ? (
          <span className="hint"> · {session.note}</span>
        ) : null}
      </td>
      <td>
        {note !== null ? (
          <form className="services__note" onSubmit={(event) => {
            event.preventDefault();
            if (note.trim() === "") return;
            onClose(note.trim());
            setNote(null);
          }}>
            <label htmlFor={`${noteId}-note`}>Come e perché</label>
            <input id={`${noteId}-note`} className="input" autoFocus value={note}
              placeholder="es. in contanti / non fatta, concordato"
              onChange={(event) => setNote(event.target.value)} />
            <button type="submit" className="button button--primary" disabled={note.trim() === ""}>
              Chiudi la sessione
            </button>
            <button type="button" className="button button--ghost" onClick={() => setNote(null)}>
              Annulla
            </button>
          </form>
        ) : session.state === "chiusa" ? (
          <button type="button" className="button button--ghost" onClick={onReopen}>
            Riapri
          </button>
        ) : session.state === "annullata" ? null : (
          <button type="button" className="button button--ghost" onClick={() => setNote("")}>
            Chiudi a mano
          </button>
        )}
      </td>
    </tr>
  );
}

/** Create or change a service: name, type, direction, price, calendar, title, text, days. */
function ServiceSheet({
  state,
  defaultWindow,
  onClose,
  onSaved,
}: {
  state: { id: number | null; draft: ServiceDraft } | null;
  /** The days a read covers when the service asks for none of its own. */
  defaultWindow: CalendarWindow;
  onClose: () => void;
  onSaved: (detail: ServiceDetail) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const fieldId = useId();
  const [draft, setDraft] = useState<ServiceDraft>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (state !== null && !dialog.open) {
      setDraft(state.draft);
      setError(null);
      dialog.showModal();
    } else if (state === null && dialog.open) {
      dialog.close();
    }
  }, [state]);

  const set = <K extends keyof ServiceDraft>(key: K, value: ServiceDraft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  const setDays = (key: "lookback_days" | "ahead_days", typed: string) => {
    const trimmed = typed.trim();
    const value = trimmed === "" ? null : Number(trimmed);
    set(key, value !== null && Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : null);
  };

  const save = async () => {
    if (state === null || saving) return;
    setSaving(true);
    const body: ServiceDraft = {
      ...draft,
      rate: draft.rate.trim().replace(",", "."),
      match_text: draft.match_text?.trim() ? draft.match_text.trim() : null,
    };
    try {
      onSaved(state.id === null ? await api.createService(body) : await api.updateService(state.id, body));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleBackdropClick = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === dialogRef.current) onClose();
  };

  return (
    <dialog ref={dialogRef} className="sheet" aria-labelledby={titleId} onClick={handleBackdropClick}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
    >
      <div className="sheet__panel">
        <header className="sheet__header">
          <h2 className="sheet__title" id={titleId}>
            {state?.id == null ? "Nuovo servizio" : "Modifica servizio"}
          </h2>
          <button type="button" className="button button--ghost" onClick={onClose} aria-label="Chiudi">
            ✕
          </button>
        </header>
        <div className="field">
          <label htmlFor={`${fieldId}-name`}>Nome</label>
          <input id={`${fieldId}-name`} className="input" value={draft.name} placeholder="Ripetizioni Andrea"
            onChange={(event) => set("name", event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`${fieldId}-kind`}>Tipo</label>
          <select id={`${fieldId}-kind`} className="input" value={draft.kind}
            onChange={(event) => set("kind", event.target.value as ServiceDraft["kind"])}>
            {Object.entries(KINDS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${fieldId}-direction`}>Verso</label>
          <select id={`${fieldId}-direction`} className="input" value={draft.direction}
            onChange={(event) => set("direction", event.target.value as ServiceDraft["direction"])}>
            <option value="entrata">Lo dai tu: ti pagano</option>
            <option value="uscita">Lo ricevi: paghi tu</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${fieldId}-billing`}>Come si paga</label>
          <select id={`${fieldId}-billing`} className="input" value={draft.billing}
            onChange={(event) => set("billing", event.target.value as ServiceDraft["billing"])}>
            <option value="sessione">A sessione: un prezzo, quanto dura non conta</option>
            <option value="ora">A ora: il prezzo per ogni ora dell&apos;evento</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${fieldId}-rate`}>
            {draft.billing === "ora" ? "Prezzo per ora" : "Prezzo per sessione"}
          </label>
          <input id={`${fieldId}-rate`} className="input" inputMode="decimal" value={draft.rate}
            onChange={(event) => set("rate", event.target.value)} />
        </div>
        {draft.billing === "ora" ? (
          <div className="field">
            <label htmlFor={`${fieldId}-hours`}>Ore di una sessione senza fine</label>
            <input id={`${fieldId}-hours`} className="input" inputMode="decimal"
              value={draft.default_hours}
              onChange={(event) => set("default_hours", event.target.value)} />
            <p className="hint">
              Per gli eventi che non dicono quando finiscono: la durata la legge dal calendario.
            </p>
          </div>
        ) : null}
        <div className="field">
          <label htmlFor={`${fieldId}-calendar`}>Calendario (ID)</label>
          <input id={`${fieldId}-calendar`} className="input" value={draft.calendar_id}
            placeholder="nome@gmail.com, o l'ID di un calendario condiviso"
            onChange={(event) => set("calendar_id", event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`${fieldId}-title`}>Titolo degli eventi (anche solo una parte)</label>
          <input id={`${fieldId}-title`} className="input" value={draft.title_pattern}
            placeholder="Ripetizioni, oppure /^seduta/"
            onChange={(event) => set("title_pattern", event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`${fieldId}-match`}>Testo nella descrizione dei movimenti</label>
          <input id={`${fieldId}-match`} className="input" value={draft.match_text ?? ""}
            placeholder="es. Carla Spallarossa: i movimenti che lo contengono si collegano da soli"
            onChange={(event) => set("match_text", event.target.value)} />
          <p className="hint">
            Contiene, maiuscole a parte. Vuoto: i pagamenti si collegano solo a mano.
          </p>
        </div>
        <div className="field">
          <label htmlFor={`${fieldId}-lookback`}>Giorni di calendario indietro</label>
          <input id={`${fieldId}-lookback`} className="input" inputMode="numeric"
            value={draft.lookback_days ?? ""} placeholder={`${defaultWindow.lookback_days}`}
            onChange={(event) => setDays("lookback_days", event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`${fieldId}-ahead`}>Giorni di calendario avanti</label>
          <input id={`${fieldId}-ahead`} className="input" inputMode="numeric"
            value={draft.ahead_days ?? ""} placeholder={`${defaultWindow.ahead_days}`}
            onChange={(event) => setDays("ahead_days", event.target.value)} />
          <p className="hint">Vuoti valgono {defaultWindow.lookback_days} e {defaultWindow.ahead_days}.</p>
        </div>
        {state?.id == null ? null : (
          <div className="field">
            <Toggle checked={draft.active} label="Attivo: il calendario si legge"
              onChange={(value) => set("active", value)} />
            <Toggle checked={draft.recalculate} label="Ricalcola le sessioni già scritte"
              onChange={(value) => set("recalculate", value)} />
            <p className="hint">
              Rilegge il calendario e rifà durata e importo di ogni sessione, tranne quelle
              corrette a mano.
            </p>
          </div>
        )}
        {error !== null ? <p className="account-form__error" role="alert">{error}</p> : null}
        <button type="button" className="button button--primary" disabled={saving} onClick={() => void save()}>
          {saving ? "Salvataggio…" : "Salva"}
        </button>
      </div>
    </dialog>
  );
}
