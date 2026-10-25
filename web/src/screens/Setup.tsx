import { useCallback, useEffect, useState } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { formatAmount, formatDate } from "../format";
import type {
  Account,
  AccountVerification,
  ConfiguredAccount,
  DeclaredBalanceCheck,
  Declaration,
  SetupBank,
  SetupCredentials,
  SetupState,
  SyncAccountResult,
  SyncOutcome,
} from "../types";
import { useAccounts } from "../useAccounts";
import type { SetupController } from "../useSetup";
import { suppressedLabel } from "./Accounts";

/** The steps, in the order they are walked; the stepper draws them numbered. */
const STEPS = ["Credenziali", "Banca", "Conti", "Primo sync", "Saldi e verifica"];

/** The countries Enable Banking covers, for the bank list to be read from. */
const COUNTRIES: { code: string; name: string }[] = [
  { code: "IT", name: "Italia" },
  { code: "AT", name: "Austria" },
  { code: "BE", name: "Belgio" },
  { code: "BG", name: "Bulgaria" },
  { code: "CY", name: "Cipro" },
  { code: "HR", name: "Croazia" },
  { code: "DK", name: "Danimarca" },
  { code: "EE", name: "Estonia" },
  { code: "FI", name: "Finlandia" },
  { code: "FR", name: "Francia" },
  { code: "DE", name: "Germania" },
  { code: "GR", name: "Grecia" },
  { code: "IE", name: "Irlanda" },
  { code: "IS", name: "Islanda" },
  { code: "LV", name: "Lettonia" },
  { code: "LI", name: "Liechtenstein" },
  { code: "LT", name: "Lituania" },
  { code: "LU", name: "Lussemburgo" },
  { code: "MT", name: "Malta" },
  { code: "NO", name: "Norvegia" },
  { code: "NL", name: "Paesi Bassi" },
  { code: "PL", name: "Polonia" },
  { code: "PT", name: "Portogallo" },
  { code: "GB", name: "Regno Unito" },
  { code: "CZ", name: "Repubblica Ceca" },
  { code: "RO", name: "Romania" },
  { code: "SK", name: "Slovacchia" },
  { code: "SI", name: "Slovenia" },
  { code: "ES", name: "Spagna" },
  { code: "SE", name: "Svezia" },
  { code: "HU", name: "Ungheria" },
];

/**
 * Where the wizard opens.
 *
 * The credentials are the one requirement with no way around them; an
 * authorization that has just written accounts wants to report them; a bank is
 * otherwise the next thing to choose.
 */
export function setupStartStep(state: SetupState): number {
  if (state.missing.includes("application_id") || state.missing.includes("private_key")) return 0;
  return state.accounts.length > 0 || state.last_connect !== null ? 2 : 1;
}

/** Whether the credentials the bank step needs are on the file. */
function credentialsWritten(state: SetupState): boolean {
  return !state.missing.includes("application_id") && !state.missing.includes("private_key");
}

/**
 * Whether the wizard can be at a step: the credentials the bank one needs, and
 * the entries an authorization wrote for the three after it. A step is also the
 * measure of the one before it — the credentials the first writes, the accounts
 * the second collects — so this is what both the stepper and *Continua* read.
 */
function stepReady(index: number, state: SetupState): boolean {
  if (index <= 0) return true;
  if (!credentialsWritten(state)) return false;
  return index === 1 || state.accounts.length > 0;
}

/** A balance can be negative — an overdraft — so the minus belongs to it. */
function isAmount(value: string): boolean {
  return /^-?\d+(\.\d{1,2})?$/.test(value.trim().replace(",", "."));
}

/** A count said out loud, or nothing at all when there is none to say. */
function countPhrase(count: number, singular: string, plural: string): string | null {
  if (count === 0) return null;
  return `${count} ${count === 1 ? singular : plural}`;
}

/** The 5.4 state of one account, as the step that reads it says it. */
function verificationText(verification: AccountVerification): string {
  switch (verification.state) {
    case "verified":
      return `verificato al ${formatDate(verification.date)}`;
    case "suppressed":
      // The same words the Conti panel uses, count and amount included: the
      // difference section 5.4 explains is this one, and it is what the first sync
      // shows here.
      return `al ${formatDate(verification.date)}: ${suppressedLabel(verification.checks)}`;
    case "mismatch":
      return `non torna al ${formatDate(verification.date)}`;
    case "unverified":
      return "saldo non verificato";
  }
}

/** The tint a 5.4 state carries: agreement, or the amber of a defect. */
function verificationClass(state: AccountVerification["state"]): string {
  if (state === "verified") return "chip chip--verified";
  if (state === "suppressed") return "chip chip--suppressed";
  if (state === "mismatch") return "chip chip--warning";
  return "chip";
}

/** What the last authorization did with this entry, when it touched it. */
function lastAction(state: SetupState, account: ConfiguredAccount): "added" | "refreshed" | null {
  const written = state.last_connect?.written ?? [];
  return written.find((row) => row.account === account.name)?.action ?? null;
}

/** One account's part of the sync, in the words the step reports it with. */
function syncLine(account: SyncAccountResult): string {
  if (account.error !== null) return account.error;
  const news = [
    countPhrase(account.actions.inserted ?? 0, "nuovo", "nuovi"),
    countPhrase(account.actions.promoted ?? 0, "aggiornato", "aggiornati"),
    countPhrase(account.actions.reimported ?? 0, "riportato dal cestino", "riportati dal cestino"),
    countPhrase(account.balances, "saldo letto", "saldi letti"),
    countPhrase(account.fetched, "movimento riletto", "movimenti riletti"),
  ].filter((part): part is string => part !== null);
  const written = news.length === 0 ? "niente di nuovo" : news.join(", ");
  return account.balance_mismatch === null ? written : `${written} · ${account.balance_mismatch}`;
}

interface SetupScreenProps {
  setup: SetupController;
  /** Where the wizard opens: the ladder, or the accounts it came back to. */
  initialStep: number;
  /** A write landed in the ledger: the screens behind read it again. */
  onWrote: () => void;
  /** Leaves the wizard; the caller drops `setup` from the URL. */
  onClose: () => void;
}

export function SetupScreen({ setup, initialStep, onWrote, onClose }: SetupScreenProps) {
  const { state, error, reload } = setup;

  if (error !== null) {
    return (
      <section className="screen">
        <header className="screen__header">
          <div>
            <h1 className="screen__title">Configurazione</h1>
          </div>
        </header>
        <div className="state state--error" role="alert">
          <p>Impossibile leggere la configurazione: {error}</p>
          <button type="button" className="button" onClick={reload}>
            Riprova
          </button>
        </div>
      </section>
    );
  }

  if (state === null) {
    return (
      <section className="screen">
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      </section>
    );
  }

  return (
    <Wizard
      setup={setup}
      state={state}
      initialStep={initialStep}
      onWrote={onWrote}
      onClose={onClose}
    />
  );
}

interface WizardProps extends SetupScreenProps {
  state: SetupState;
}

function Wizard({ setup, state, initialStep, onWrote, onClose }: WizardProps) {
  const [step, setStep] = useState(initialStep);

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Configurazione</h1>
          <p className="screen__subtitle">
            {state.configured
              ? "Le banche collegate, i conti che il ledger conosce e i saldi da verificare."
              : "I passi per collegare la prima banca e far nascere il ledger."}
          </p>
        </div>
      </header>

      <ol className="stepper" aria-label="Passi della configurazione">
        {STEPS.map((title, index) => (
          <li className="stepper__item" key={title}>
            <button
              type="button"
              className="stepper__step"
              aria-current={index === step ? "step" : undefined}
              // A step that has been walked is one to go back to; one that still
              // needs something is not a place to be.
              disabled={index !== step && !(index < step && stepReady(index, state))}
              onClick={() => setStep(index)}
            >
              <span className="stepper__number" aria-hidden="true">
                {index + 1}
              </span>
              <span className="stepper__title">{title}</span>
            </button>
          </li>
        ))}
      </ol>

      {step === 0 ? <CredentialsStep state={state} onSave={setup.saveCredentials} /> : null}
      {step === 1 ? <BankStep /> : null}
      {step === 2 ? (
        <AccountsStep
          state={state}
          onRename={setup.renameAccount}
          onRemove={setup.removeAccount}
          onGoToBank={() => setStep(1)}
        />
      ) : null}
      {step === 3 ? <SyncStep onWrote={onWrote} /> : null}
      {step === 4 ? <BalancesStep onWrote={onWrote} /> : null}

      <div className="setup__nav">
        {step > 0 ? (
          <button type="button" className="button" onClick={() => setStep(step - 1)}>
            Indietro
          </button>
        ) : null}
        {step < STEPS.length - 1 ? (
          <button
            type="button"
            className="button button--primary"
            disabled={!stepReady(step + 1, state)}
            onClick={() => setStep(step + 1)}
          >
            Continua
          </button>
        ) : (
          <button
            type="button"
            className="button button--primary"
            disabled={!state.configured}
            onClick={onClose}
          >
            Vai alla dashboard
          </button>
        )}
      </div>
      {step === STEPS.length - 1 && !state.configured ? (
        <p className="hint">
          Prima di uscire serve almeno un conto: senza, il ledger non ha niente da leggere.
        </p>
      ) : null}
    </section>
  );
}

interface CredentialsStepProps {
  state: SetupState;
  onSave: (body: SetupCredentials) => Promise<string | null>;
}

function CredentialsStep({ state, onSave }: CredentialsStepProps) {
  // The address the browser is on is the one that reaches the app, so it is the
  // one the bank has to call back: proposing anything else means the wizard
  // starts its first step by asking the person to retype the address they are
  // already using. A value already in the file that disagrees — the dead
  // `:3000` port older releases wrote — is shown under the field instead of
  // being kept as the answer.
  const proposed = `${window.location.origin}/callback`;
  const [applicationId, setApplicationId] = useState(state.application_id);
  const [privateKey, setPrivateKey] = useState("");
  const [redirectUrl, setRedirectUrl] = useState(proposed);
  const [holder, setHolder] = useState(state.account_holder_name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (saving) return;
    setSaving(true);
    setError(null);
    const body: SetupCredentials = {
      application_id: applicationId.trim(),
      redirect_url: redirectUrl.trim(),
      account_holder_name: holder.trim(),
    };
    // The key travels only when it is being set: the server keeps the one it
    // has, and a step that left the field empty is not a step that erased it.
    if (privateKey.trim() !== "") body.private_key = privateKey;
    const message = await onSave(body);
    if (message !== null) setError(message);
    else setPrivateKey("");
    setSaving(false);
  };

  return (
    <div className="panel">
      <h2 className="section-title">Credenziali</h2>
      <p className="chart-note">
        Sono le credenziali dell&apos;applicazione che hai creato nella dashboard di Enable Banking:
        l&apos;Application ID e la chiave privata che ti ha dato.
      </p>

      <form
        className="account-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="field">
          <label htmlFor="setup-application-id">Application ID</label>
          <input
            id="setup-application-id"
            className="input"
            type="text"
            autoComplete="off"
            value={applicationId}
            onChange={(event) => setApplicationId(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="setup-private-key">Chiave privata</label>
          <textarea
            id="setup-private-key"
            rows={5}
            spellCheck={false}
            placeholder="-----BEGIN PRIVATE KEY-----"
            value={privateKey}
            onChange={(event) => setPrivateKey(event.target.value)}
          />
          <p className="hint">
            {state.key_loads
              ? `Una chiave c'è già e si carica: ${state.pem_path}. Incollane una solo per sostituirla.`
              : `Va scritta in ${state.pem_path}: senza, Enable Banking non risponde.`}
          </p>
        </div>

        <div className="field">
          <label htmlFor="setup-holder">Nome dell&apos;intestatario</label>
          <input
            id="setup-holder"
            className="input"
            type="text"
            autoComplete="off"
            value={holder}
            onChange={(event) => setHolder(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="setup-redirect-url">Redirect URL</label>
          <input
            id="setup-redirect-url"
            className="input"
            type="text"
            autoComplete="off"
            inputMode="url"
            value={redirectUrl}
            onChange={(event) => setRedirectUrl(event.target.value)}
          />
          <p className="hint">
            L&apos;indirizzo da cui stai usando l&apos;app. Enable Banking registra solo indirizzi
            HTTPS — un indirizzo http://… vale per la prova locale con la banca finta, non per la
            banca vera — e deve combaciare carattere per carattere con quello registrato.
          </p>
          {state.redirect_url !== "" && state.redirect_url !== proposed ? (
            <p className="hint">
              Nel file c&apos;era {state.redirect_url}: salvalo di nuovo solo se è quello che vuoi
              registrare.
            </p>
          ) : null}
        </div>

        {error !== null ? (
          <p className="account-form__error" role="alert">
            {error}
          </p>
        ) : null}

        <div className="account-form__actions">
          <button
            type="submit"
            className="button button--primary"
            disabled={saving || applicationId.trim() === "" || redirectUrl.trim() === ""}
          >
            {saving ? "Salvo…" : "Salva"}
          </button>
        </div>
      </form>

      {credentialsWritten(state) ? (
        <div className="field">
          <p className="filters__caption">
            Da registrare nella dashboard di Enable Banking, carattere per carattere:
          </p>
          <p className="state__command setup__command">{state.redirect_url}</p>
          <p className="hint">
            Questa registrazione resta un passaggio a mano, ed è l&apos;unica: se le due stringhe non
            combaciano la banca rifiuta il ritorno nell&apos;app.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function BankStep() {
  const [country, setCountry] = useState("IT");
  const [banks, setBanks] = useState<SetupBank[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  const loadBanks = useCallback(async (wanted: string, signal?: AbortSignal) => {
    setLoading(true);
    try {
      const answer = await api.setupBanks(wanted, signal);
      setBanks(answer.banks);
      setLoadError(null);
    } catch (caught) {
      if (isAbortError(caught)) return;
      setLoadError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    // The chosen bank belongs to the country it was read from.
    setChosen(null);
    void loadBanks(country, controller.signal);
    return () => controller.abort();
  }, [loadBanks, country]);

  const needle = query.trim().toLowerCase();
  const shown =
    needle === "" ? banks : banks.filter((bank) => bank.name.toLowerCase().includes(needle));

  const connect = async () => {
    if (chosen === null || connecting) return;
    setConnecting(true);
    setConnectError(null);
    try {
      const { url } = await api.setupConnect(chosen, country);
      // The login happens at the bank, and the bank brings the browser back
      // here: `/?setup=1` is the return address, so the tab goes with it.
      window.location.assign(url);
    } catch (caught) {
      setConnectError(errorMessage(caught));
      setConnecting(false);
    }
  };

  return (
    <div className="panel">
      <h2 className="section-title">Banca</h2>
      <p className="chart-note">
        Scegli il paese e poi la banca. L&apos;accesso si fa sul sito della banca: questa app non
        vede le tue credenziali, e alla fine la banca riporta il browser qui.
      </p>

      <div className="field">
        <label htmlFor="setup-country">Paese</label>
        <select
          id="setup-country"
          value={country}
          onChange={(event) => setCountry(event.target.value)}
        >
          {COUNTRIES.map((item) => (
            <option key={item.code} value={item.code}>
              {item.name}
            </option>
          ))}
        </select>
      </div>

      {loadError !== null ? (
        <div className="state state--error" role="alert">
          <p>Impossibile leggere l&apos;elenco delle banche: {loadError}</p>
          <button type="button" className="button" onClick={() => void loadBanks(country)}>
            Riprova
          </button>
        </div>
      ) : loading && banks.length === 0 ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : (
        <>
          <div className="field">
            <label htmlFor="setup-bank-filter">Filtra</label>
            <input
              id="setup-bank-filter"
              className="input"
              type="search"
              autoComplete="off"
              placeholder="Nome della banca…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          {shown.length === 0 ? (
            <p className="state">
              {banks.length === 0
                ? "Nessuna banca per questo paese."
                : "Nessuna banca con questo nome."}
            </p>
          ) : (
            <ul className="bank-list">
              {shown.map((bank) => (
                <li key={bank.name}>
                  <button
                    type="button"
                    className={
                      chosen === bank.name ? "chip chip--toggle chip--on" : "chip chip--toggle"
                    }
                    aria-pressed={chosen === bank.name}
                    onClick={() => setChosen(bank.name)}
                  >
                    {bank.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <form
        className="account-form"
        onSubmit={(event) => {
          event.preventDefault();
          void connect();
        }}
      >
        {connectError !== null ? (
          <p className="account-form__error" role="alert">
            {connectError}
          </p>
        ) : null}
        <div className="account-form__actions">
          <button
            type="submit"
            className="button button--primary"
            disabled={chosen === null || connecting}
            aria-busy={connecting}
          >
            {connecting ? "Apro la banca…" : chosen === null ? "Scegli una banca" : `Vai a ${chosen}`}
          </button>
        </div>
      </form>
    </div>
  );
}

interface AccountsStepProps {
  state: SetupState;
  onRename: (accountUid: string, name: string, startSyncDate: string) => Promise<string | null>;
  onRemove: (accountUid: string) => Promise<string | null>;
  onGoToBank: () => void;
}

function AccountsStep({ state, onRename, onRemove, onGoToBank }: AccountsStepProps) {
  return (
    <div className="panel">
      <h2 className="section-title">
        Conti <span className="count">{state.accounts.length}</span>
      </h2>
      <p className="chart-note">
        Il nome è come il ledger conosce il conto: due voci con lo stesso nome diventano un conto
        solo, e i loro movimenti finiscono insieme. La data dice da quando importare i movimenti.
        <em>Togli</em> toglie la voce dalla configurazione: quello che il ledger ha già scritto
        resta.
      </p>

      {state.accounts.length === 0 ? (
        <p className="state">
          Nessun conto configurato: autorizza una banca, e i conti che risponde compaiono qui.
        </p>
      ) : (
        <ul className="flag-list">
          {state.accounts.map((account) => (
            <ConfiguredAccountRow
              key={account.account_uid}
              account={account}
              action={lastAction(state, account)}
              onRename={onRename}
              onRemove={onRemove}
            />
          ))}
        </ul>
      )}

      <div className="account-form__actions">
        <button type="button" className="button" onClick={onGoToBank}>
          Aggiungi o rinnova una banca
        </button>
      </div>
    </div>
  );
}

interface ConfiguredAccountRowProps {
  account: ConfiguredAccount;
  /** What the last authorization did with it, when it touched it. */
  action: "added" | "refreshed" | null;
  onRename: (accountUid: string, name: string, startSyncDate: string) => Promise<string | null>;
  onRemove: (accountUid: string) => Promise<string | null>;
}

function ConfiguredAccountRow({
  account,
  action,
  onRename,
  onRemove,
}: ConfiguredAccountRowProps) {
  const [name, setName] = useState(account.name);
  const [startSyncDate, setStartSyncDate] = useState(account.start_sync_date ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const changed = name.trim() !== account.name || startSyncDate !== (account.start_sync_date ?? "");

  const save = async () => {
    if (saving || name.trim() === "") return;
    setSaving(true);
    setError(null);
    const message = await onRename(account.account_uid, name.trim(), startSyncDate);
    setError(message);
    setSaving(false);
  };

  const remove = async () => {
    if (saving) return;
    setSaving(true);
    setError(null);
    const message = await onRemove(account.account_uid);
    setConfirming(false);
    setError(message);
    setSaving(false);
  };

  return (
    <li className="flag-row">
      <div className="rule-row">
        <div className="rule-row__head">
          <span className="rule-row__pattern">
            {account.institution === "" ? account.name : account.institution}
          </span>
          {action === null ? null : (
            <span className="chip">
              {action === "added" ? "aggiunto dall'ultima autorizzazione" : "rinnovato dall'ultima autorizzazione"}
            </span>
          )}
        </div>
        <p className="hint">
          {account.country === "" ? "Paese non noto" : account.country}
          {account.session_expiry === null
            ? ""
            : ` · consenso fino al ${formatDate(account.session_expiry.slice(0, 10))}`}
        </p>

        <form
          className="account-form"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="field">
            <label htmlFor={`setup-name-${account.account_uid}`}>Nome nel ledger</label>
            <input
              id={`setup-name-${account.account_uid}`}
              className="input"
              type="text"
              autoComplete="off"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`setup-start-${account.account_uid}`}>Movimenti da</label>
            <input
              id={`setup-start-${account.account_uid}`}
              type="date"
              value={startSyncDate}
              onChange={(event) => setStartSyncDate(event.target.value)}
            />
          </div>

          {error !== null ? (
            <p className="account-form__error" role="alert">
              {error}
            </p>
          ) : null}

          <div className="account-form__actions">
            <button
              type="submit"
              className="button button--primary"
              disabled={saving || name.trim() === "" || !changed}
            >
              {saving ? "Salvo…" : "Salva"}
            </button>
            {confirming ? (
              <div className="rule-row__confirm">
                <p>
                  Sicuro? La voce esce dalla configurazione e il sync smette di chiedere questo conto
                  alla banca; nel ledger non cambia niente.
                </p>
                <button
                  type="button"
                  className="button button--danger"
                  disabled={saving}
                  onClick={() => void remove()}
                >
                  Togli
                </button>
                <button type="button" className="button" onClick={() => setConfirming(false)}>
                  Annulla
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="button button--danger"
                disabled={saving}
                onClick={() => setConfirming(true)}
              >
                Togli
              </button>
            )}
          </div>
        </form>
      </div>
    </li>
  );
}

function SyncStep({ onWrote }: { onWrote: () => void }) {
  const [outcome, setOutcome] = useState<SyncOutcome | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (syncing) return;
    setSyncing(true);
    setError(null);
    try {
      setOutcome(await api.sync());
      onWrote();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="panel">
      <h2 className="section-title">Primo sync</h2>
      <p className="chart-note">
        Il sync chiede alla banca i movimenti di ogni conto configurato e li scrive nel ledger. Qui
        è il primo giro, quello che riempie il ledger; da qui in poi lo fa da sé, e il pulsante in
        alto lo ripete quando vuoi.
      </p>

      <form
        className="account-form"
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
      >
        {error !== null ? (
          <p className="account-form__error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="account-form__actions">
          <button
            type="submit"
            className="button button--primary"
            disabled={syncing}
            aria-busy={syncing}
          >
            {syncing ? "Sincronizzo…" : "Sincronizza adesso"}
          </button>
        </div>
      </form>

      {outcome === null ? null : <SyncReport outcome={outcome} />}
    </div>
  );
}

function SyncReport({ outcome }: { outcome: SyncOutcome }) {
  const extras = [
    countPhrase(outcome.transfers_linked, "giroconto collegato", "giroconti collegati"),
    countPhrase(outcome.rules_applied, "movimento categorizzato dalle regole", "movimenti categorizzati dalle regole"),
    countPhrase(outcome.passthrough_legs, "gamba verso un conto dichiarato", "gambe verso un conto dichiarato"),
  ].filter((part): part is string => part !== null);

  if (outcome.accounts.length === 0) {
    return <p className="state">Nessun conto da sincronizzare: la configurazione non ne ha.</p>;
  }

  return (
    <>
      <ul className="flag-list">
        {outcome.accounts.map((account) => (
          <li className="flag-row" key={account.account}>
            <span className="flag-row__name">
              {account.account}
              <span className="flag-row__balance">{syncLine(account)}</span>
              {account.verification === null ? null : (
                <span className={`${verificationClass(account.verification.state)} flag-row__check`}>
                  {verificationText(account.verification)}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
      <p className="hint">
        {extras.length === 0 ? "Nient'altro da segnalare." : extras.join(" · ")}
      </p>
    </>
  );
}

function BalancesStep({ onWrote }: { onWrote: () => void }) {
  const { accounts, error, loading, reload, declareBalance, setOpening } = useAccounts();
  const [pending, setPending] = useState<number[]>([]);

  const declare = async (account: Account, body: Declaration): Promise<string | null> => {
    const { error: message } = await declareBalance(account.id, body);
    if (message === null) onWrote();
    return message;
  };

  const align = async (account: Account, check: DeclaredBalanceCheck): Promise<string | null> => {
    if (pending.includes(account.id)) return null;
    setPending((current) => [...current, account.id]);
    const { error: message } = await setOpening(account.id, {
      date: check.date,
      balance: check.declared,
      kind: check.kind,
    });
    setPending((current) => current.filter((id) => id !== account.id));
    if (message === null) onWrote();
    return message;
  };

  return (
    <div className="panel">
      <h2 className="section-title">
        Saldi e verifica <span className="count">{accounts.length}</span>
      </h2>
      <p className="chart-note">
        Un saldo letto dal sito della banca e scritto qui dice se il ledger torna: è la verifica che
        ogni conto porta con sé. Quando non torna, allineare il saldo iniziale è la via per
        riportarli d&apos;accordo.
      </p>

      {error !== null ? (
        <div className="state state--error" role="alert">
          <p>Impossibile caricare i conti: {error}</p>
          <button type="button" className="button" onClick={reload}>
            Riprova
          </button>
        </div>
      ) : loading && accounts.length === 0 ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : accounts.length === 0 ? (
        <p className="state">
          Nessun conto reale nel ledger: il primo sync lo riempie, e i conti compaiono qui.
        </p>
      ) : (
        <ul className="flag-list">
          {accounts.map((account) => (
            <BalanceRow
              key={account.id}
              account={account}
              pending={pending.includes(account.id)}
              onDeclare={declare}
              onAlign={align}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

interface BalanceRowProps {
  account: Account;
  pending: boolean;
  onDeclare: (account: Account, body: Declaration) => Promise<string | null>;
  onAlign: (account: Account, check: DeclaredBalanceCheck) => Promise<string | null>;
}

function BalanceRow({ account, pending, onDeclare, onAlign }: BalanceRowProps) {
  // `en-CA` formats a date as YYYY-MM-DD, which is what `type="date"` reads.
  const [date, setDate] = useState(() => new Date().toLocaleDateString("en-CA"));
  const [amount, setAmount] = useState("");
  const [kind, setKind] = useState<Declaration["kind"]>("available");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (saving || !isAmount(amount)) return;
    setSaving(true);
    setError(null);
    const message = await onDeclare(account, {
      date,
      balance: amount.trim().replace(",", "."),
      kind,
    });
    // The figure is on the server now: the field starts over for the next one.
    if (message === null) setAmount("");
    setError(message);
    setSaving(false);
  };

  const align = async (check: DeclaredBalanceCheck) => {
    setSaving(true);
    setError(null);
    setError(await onAlign(account, check));
    setSaving(false);
  };

  return (
    <li className="flag-row">
      <div className="rule-row">
        <div className="rule-row__head">
          <span className="rule-row__pattern">{account.name}</span>
          <span className="rule-row__count">{formatAmount(account.balance)}</span>
        </div>
        <span className={`${verificationClass(account.verification.state)} flag-row__check`}>
          {verificationText(account.verification)}
        </span>

        <form
          className="account-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="field">
            <label htmlFor={`setup-balance-date-${account.id}`}>Data del saldo</label>
            <input
              id={`setup-balance-date-${account.id}`}
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`setup-balance-amount-${account.id}`}>Saldo letto dalla banca</label>
            <input
              id={`setup-balance-amount-${account.id}`}
              className="input"
              type="text"
              inputMode="decimal"
              placeholder="0,00"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`setup-balance-kind-${account.id}`}>Tipo</label>
            <select
              id={`setup-balance-kind-${account.id}`}
              value={kind}
              onChange={(event) => setKind(event.target.value as Declaration["kind"])}
            >
              <option value="available">Disponibile</option>
              <option value="booked">Contabilizzata</option>
            </select>
          </div>

          {error !== null ? (
            <p className="account-form__error" role="alert">
              {error}
            </p>
          ) : null}

          <div className="account-form__actions">
            <button
              type="submit"
              className="button button--primary"
              disabled={saving || !isAmount(amount)}
            >
              {saving ? "Dichiaro…" : "Dichiara saldo"}
            </button>
            {account.verification.state === "verified"
              ? null
              : account.verification.checks.map((check) => (
                  <button
                    type="button"
                    className="button"
                    key={`${check.kind}:${check.date}:${check.source}`}
                    disabled={saving || pending}
                    title={`${check.source} del ${formatDate(check.date)}: banca ${formatAmount(
                      check.declared,
                    )}, ledger ${formatAmount(check.computed)}`}
                    onClick={() => void align(check)}
                  >
                    {`Allinea il saldo iniziale (${check.kind === "available" ? "disponibile" : "contabilizzata"})`}
                  </button>
                ))}
          </div>
        </form>
      </div>
    </li>
  );
}
