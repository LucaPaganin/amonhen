import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { MouseEvent } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { PeriodSync } from "../components/PeriodSync";
import { Toast } from "../components/Toast";
import { Toggle } from "../components/Toggle";
import { formatAmount, formatDate, toAmount } from "../format";
import type {
  Account,
  AccountFlags,
  AccountVerification,
  DeclaredBalanceCheck,
  Declaration,
  DeletedMovement,
  HeldMovement,
  NewAccount,
} from "../types";
import { useAccounts } from "../useAccounts";

interface AccountsScreenProps {
  /** Bumped after a sync: the balances and the 5.4 verdict are read again. */
  refreshToken: number;
}

/** The two figures a bank reports, in the words the form offers. */
const KIND_LABELS: Record<Declaration["kind"], string> = {
  available: "Disponibile",
  booked: "Contabilizzata",
};

/** What declaring a figure is for: it says whether the bank and the ledger agree. */
const VERIFICATION_OUTCOMES: Record<AccountVerification["state"], string> = {
  verified: "banca e ledger concordano",
  suppressed: "d'accordo salvo i movimenti cancellati a mano",
  mismatch: "banca e ledger non concordano",
  unverified: "nessun confronto possibile",
};

/** A balance can be negative — an overdraft — so the minus belongs to it. */
function isAmount(value: string): boolean {
  return /^-?\d+(\.\d{1,2})?$/.test(value.trim().replace(",", "."));
}

function today(): string {
  return new Date().toLocaleDateString("en-CA");
}

/** Which figure disagrees decides what to go and look at. */
export function suppressedLabel(checks: DeclaredBalanceCheck[]): string {
  // The two declared figures describe one account: the available one counts
  // every deleted movement and the booked one a subset, so the total is the
  // widest of them — never their sum, which counts the same movement twice.
  const widest = checks.reduce((most, check) =>
    check.suppressed_count > most.suppressed_count ? check : most,
  );
  // The amount is said without its sign: the two figures above already say
  // which way the difference runs.
  const amount = Math.abs(toAmount(widest.suppressed));
  const what =
    widest.suppressed_count === 1
      ? "1 movimento cancellato a mano"
      : `${widest.suppressed_count} movimenti cancellati a mano`;
  return `d'accordo salvo ${what} (${formatAmount(String(amount))})`;
}

function verificationLabel(checks: DeclaredBalanceCheck[]): string {
  const failed = checks.filter((check) => !check.ok);
  // Naming the figure that disagrees only points somewhere when the other one
  // was declared and agrees: Revolut declares the available figure alone, and
  // a difference there said "sui sospesi" with no pending movement in sight.
  const agrees = (kind: DeclaredBalanceCheck["kind"]) =>
    checks.some((check) => check.kind === kind && check.ok);
  if (failed.length === 1 && failed[0].kind === "available" && agrees("booked")) {
    return "non torna sui sospesi";
  }
  if (failed.length === 1 && failed[0].kind === "booked" && agrees("available")) {
    return "non torna sul contabile";
  }
  return `discrepanza ${formatAmount(failed[0].difference)}`;
}

/** The numbers behind the chip, for whoever can hover. */
function verificationDetail(verification: AccountVerification): string {
  return verification.checks
    .map(
      (check) =>
        `${check.source} del ${formatDate(check.date)}: banca ${formatAmount(check.declared)}, ` +
        `ledger ${formatAmount(check.computed)}` +
        (check.explained
          ? ` (${formatAmount(String(Math.abs(toAmount(check.suppressed))))} cancellati a mano)`
          : ""),
    )
    .join(" · ");
}

/** The 5.4 assertion, where the balance is. */
function VerificationChip({ verification }: { verification: AccountVerification }) {
  if (verification.state === "unverified") {
    return (
      <span
        className="chip flag-row__check"
        title="La banca non ha mai dichiarato un saldo per questo conto"
      >
        saldo non verificato
      </span>
    );
  }
  // Reconciled except for what was deleted here by hand: that is not a defect,
  // so it is not the amber a defect gets either.
  const tone =
    verification.state === "verified"
      ? "chip--verified"
      : verification.state === "suppressed"
        ? "chip--suppressed"
        : "chip--warning";
  return (
    <span className={`chip flag-row__check ${tone}`} title={verificationDetail(verification)}>
      {verification.state === "verified"
        ? `verificato al ${formatDate(verification.date)}`
        : verification.state === "suppressed"
          ? suppressedLabel(verification.checks)
          : verificationLabel(verification.checks)}
    </span>
  );
}

interface DeclareSheetProps {
  open: boolean;
  account: Account | null;
  onClose: () => void;
  onDeclare: (account: Account, body: Declaration) => Promise<string | null>;
}

function DeclareSheet({ open, account, onClose, onDeclare }: DeclareSheetProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [date, setDate] = useState("");
  const [amount, setAmount] = useState("");
  const [kind, setKind] = useState<Declaration["kind"]>("available");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setDate(today());
      setAmount("");
      setKind("available");
      setError(null);
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  const handleBackdropClick = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === dialogRef.current) onClose();
  };

  const submit = async () => {
    if (account === null || saving) return;
    setSaving(true);
    setError(null);
    const message = await onDeclare(account, {
      date,
      balance: amount.trim().replace(",", "."),
      kind,
    });
    if (message !== null) {
      setError(message);
    } else {
      onClose();
    }
    setSaving(false);
  };

  return (
    <dialog
      ref={dialogRef}
      className="sheet"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      onClick={handleBackdropClick}
    >
      <div className="sheet__panel">
        <header className="sheet__header">
          <h2 className="sheet__title" id={titleId}>
            {account === null ? "Dichiara saldo" : `Dichiara saldo · ${account.name}`}
          </h2>
          <button type="button" className="button button--ghost" onClick={onClose} aria-label="Chiudi">
            ✕
          </button>
        </header>

        <form
          className="account-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="field">
            <label htmlFor="declaration-date">Data</label>
            <input
              id="declaration-date"
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="declaration-amount">Saldo</label>
            <input
              id="declaration-amount"
              className="input"
              type="text"
              inputMode="decimal"
              placeholder="0,00"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="declaration-kind">Tipo</label>
            <select
              id="declaration-kind"
              value={kind}
              onChange={(event) => setKind(event.target.value as Declaration["kind"])}
            >
              <option value="available">{KIND_LABELS.available}</option>
              <option value="booked">{KIND_LABELS.booked}</option>
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
              {saving ? "Salvo…" : "Dichiara"}
            </button>
            <button type="button" className="button" onClick={onClose}>
              Annulla
            </button>
          </div>
        </form>
      </div>
    </dialog>
  );
}

interface NewAccountSheetProps {
  open: boolean;
  onClose: () => void;
  onCreate: (body: NewAccount) => Promise<string | null>;
}

function NewAccountSheet({ open, onClose, onCreate }: NewAccountSheetProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [name, setName] = useState("");
  const [institution, setInstitution] = useState("");
  const [currency, setCurrency] = useState("");
  const [openingBalance, setOpeningBalance] = useState("");
  const [openingDate, setOpeningDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setName("");
      setInstitution("");
      setCurrency("");
      setOpeningBalance("");
      setOpeningDate("");
      setError(null);
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  const handleBackdropClick = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === dialogRef.current) onClose();
  };

  const submit = async () => {
    if (saving) return;
    setSaving(true);
    setError(null);
    const body: NewAccount = { name: name.trim() };
    if (institution.trim() !== "") body.institution = institution.trim();
    if (currency.trim() !== "") body.currency = currency.trim();
    // The opening date means nothing without the figure it anchors, so the two
    // travel together; the server refuses a figure without its date.
    if (openingBalance.trim() !== "") {
      body.opening_balance = openingBalance.trim().replace(",", ".");
      if (openingDate !== "") body.opening_date = openingDate;
    }
    const message = await onCreate(body);
    if (message !== null) {
      setError(message);
    } else {
      onClose();
    }
    setSaving(false);
  };

  return (
    <dialog
      ref={dialogRef}
      className="sheet"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      onClick={handleBackdropClick}
    >
      <div className="sheet__panel">
        <header className="sheet__header">
          <h2 className="sheet__title" id={titleId}>
            Nuovo conto
          </h2>
          <button type="button" className="button button--ghost" onClick={onClose} aria-label="Chiudi">
            ✕
          </button>
        </header>

        <form
          className="account-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="field">
            <label htmlFor="account-name">Nome</label>
            <input
              id="account-name"
              className="input"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="account-institution">Istituto</label>
            <input
              id="account-institution"
              className="input"
              type="text"
              value={institution}
              onChange={(event) => setInstitution(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="account-currency">Valuta</label>
            <input
              id="account-currency"
              className="input"
              type="text"
              placeholder="EUR"
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="account-opening-balance">Saldo iniziale</label>
            <input
              id="account-opening-balance"
              className="input"
              type="text"
              inputMode="decimal"
              placeholder="0,00"
              value={openingBalance}
              onChange={(event) => setOpeningBalance(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="account-opening-date">Data del saldo iniziale</label>
            <input
              id="account-opening-date"
              type="date"
              value={openingDate}
              onChange={(event) => setOpeningDate(event.target.value)}
            />
          </div>

          {error !== null ? (
            <p className="account-form__error" role="alert">
              {error}
            </p>
          ) : null}

          {openingBalance.trim() !== "" && openingDate === "" ? (
            <p className="chart-note">Indica la data a cui si riferisce il saldo iniziale.</p>
          ) : null}

          <div className="account-form__actions">
            <button
              type="submit"
              className="button button--primary"
              disabled={
                saving ||
                name.trim() === "" ||
                (openingBalance.trim() !== "" &&
                  (!isAmount(openingBalance) || openingDate === ""))
              }
            >
              {saving ? "Creo…" : "Crea conto"}
            </button>
            <button type="button" className="button" onClick={onClose}>
              Annulla
            </button>
          </div>
        </form>
      </div>
    </dialog>
  );
}

export function AccountsScreen({ refreshToken }: AccountsScreenProps) {
  const {
    accounts,
    error: accountsError,
    loading: accountsLoading,
    reload: reloadAccounts,
    setFlags,
    createAccount,
    declareBalance,
    setOpening,
  } = useAccounts();

  const [pendingAccounts, setPendingAccounts] = useState<number[]>([]);
  const [trash, setTrash] = useState<DeletedMovement[]>([]);
  const [trashError, setTrashError] = useState<string | null>(null);
  const [held, setHeld] = useState<HeldMovement[]>([]);
  const [declareFor, setDeclareFor] = useState<Account | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  // Deleting an account cannot be undone from here, so it asks for the name:
  // a tap on the wrong row must not take a bank's whole history with it.
  const [deletingFor, setDeletingFor] = useState<number | null>(null);
  const [typedName, setTypedName] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // A sync declares balances under this screen, so the token says to read them
  // again: the first render is not a refresh, the mount effect above is.
  useEffect(() => {
    if (refreshToken > 0) reloadAccounts();
  }, [refreshToken, reloadAccounts]);

  // The trash is read once and grouped under each account: what a delete left
  // behind belongs to the account whose flag decides whether it may come back.
  const loadTrash = useCallback(async (signal?: AbortSignal) => {
    try {
      setTrash(await api.deleted(signal));
      setTrashError(null);
    } catch (caught) {
      if (isAbortError(caught)) return;
      setTrashError(errorMessage(caught));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadTrash(controller.signal);
    return () => controller.abort();
  }, [loadTrash, refreshToken]);

  // The probable duplicates a period sync held, read once and grouped under
  // their account like the trash: the decision belongs to the account's panel.
  const loadHeld = useCallback(async (signal?: AbortSignal) => {
    try {
      setHeld(await api.held(signal));
    } catch (caught) {
      if (isAbortError(caught)) return;
      setNotice(`Movimenti in attesa non leggibili: ${errorMessage(caught)}`);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadHeld(controller.signal);
    return () => controller.abort();
  }, [loadHeld, refreshToken]);

  const periodChanged = () => {
    reloadAccounts();
    void loadHeld();
    void loadTrash();
  };

  const restore = async (item: DeletedMovement) => {
    if (pendingAccounts.includes(item.account.id)) return;
    setPendingAccounts((current) => [...current, item.account.id]);
    try {
      await api.restoreDeleted(item.id);
      setNotice(`Movimento ripristinato: ${item.merchant ?? item.description}`);
      // Both sides change: the account gains the movement back and the trash
      // loses it, and the verification is what says whether they agree again.
      reloadAccounts();
      await loadTrash();
    } catch (caught) {
      setNotice(`Movimento non ripristinato: ${errorMessage(caught)}`);
    } finally {
      setPendingAccounts((current) => current.filter((id) => id !== item.account.id));
    }
  };

  const toggleFlag = async (
    account: Account,
    flags: AccountFlags,
  ) => {
    if (pendingAccounts.includes(account.id)) return;
    setPendingAccounts((current) => [...current, account.id]);
    const message = await setFlags(account.id, flags);
    setPendingAccounts((current) => current.filter((id) => id !== account.id));
    if (message !== null) setNotice(`Conto non aggiornato: ${message}`);
  };

  const handleDeclare = async (account: Account, body: Declaration): Promise<string | null> => {
    const { account: updated, error } = await declareBalance(account.id, body);
    if (error !== null) return error;
    setNotice(`Saldo dichiarato: ${VERIFICATION_OUTCOMES[updated.verification.state]}`);
    return null;
  };

  const handleSetOpening = async (account: Account, check: DeclaredBalanceCheck) => {
    if (pendingAccounts.includes(account.id)) return;
    setPendingAccounts((current) => [...current, account.id]);
    const { account: updated, error } = await setOpening(account.id, {
      date: check.date,
      balance: check.declared,
      kind: check.kind,
    });
    setPendingAccounts((current) => current.filter((id) => id !== account.id));
    setNotice(
      error === null
        ? `Saldo iniziale allineato: ${VERIFICATION_OUTCOMES[updated.verification.state]}`
        : `Saldo iniziale non allineato: ${error}`,
    );
  };

  const askDelete = (account: Account) => {
    setDeletingFor(account.id);
    setTypedName("");
    setDeleteError(null);
  };

  const deleteAccount = async (account: Account) => {
    if (typedName.trim() !== account.name || pendingAccounts.includes(account.id)) return;
    setPendingAccounts((current) => [...current, account.id]);
    setDeleteError(null);
    try {
      const outcome = await api.deleteAccount(account.id);
      setDeletingFor(null);
      setNotice(
        `Conto ${outcome.name} eliminato con ${outcome.movements} ${
          outcome.movements === 1 ? "movimento" : "movimenti"
        }${outcome.disconnected ? ": il sync non lo chiede più alla banca" : ""}`,
      );
      reloadAccounts();
      void loadTrash();
    } catch (caught) {
      setDeleteError(errorMessage(caught));
    } finally {
      setPendingAccounts((current) => current.filter((id) => id !== account.id));
    }
  };

  const handleCreate = async (body: NewAccount): Promise<string | null> => {
    const message = await createAccount(body);
    if (message !== null) return message;
    setNotice("Conto creato");
    return null;
  };

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Conti</h1>
          <p className="screen__subtitle">I conti reali, il loro saldo e il saldo di partenza.</p>
        </div>
      </header>

      <section className="panel">
        <h2 className="section-title">
          Conti <span className="count">{accounts.length}</span>
        </h2>
        <div className="account-actions">
          <button type="button" className="button button--primary" onClick={() => setNewOpen(true)}>
            Nuovo conto
          </button>
        </div>
        {accountsError !== null ? (
          <div className="state state--error" role="alert">
            <p>Impossibile caricare i conti: {accountsError}</p>
            <button type="button" className="button" onClick={reloadAccounts}>
              Riprova
            </button>
          </div>
        ) : accountsLoading && accounts.length === 0 ? (
          <p className="state" aria-busy="true">
            Caricamento…
          </p>
        ) : accounts.length === 0 ? (
          <p className="state">Nessun conto reale.</p>
        ) : (
          <ul className="flag-list">
            {accounts.map((account) => {
              const pending = pendingAccounts.includes(account.id);
              return (
                <li className="flag-row" key={account.id}>
                  <span className="flag-row__name">
                    {account.name}
                    <span className="flag-row__balance">
                      {formatAmount(account.balance)}
                      {account.opening_balance !== null && account.opening_date !== null
                        ? ` · iniziale ${formatAmount(account.opening_balance)} al ${formatDate(
                            account.opening_date,
                          )}`
                        : ""}
                    </span>
                    <VerificationChip verification={account.verification} />
                  </span>
                  <div className="flag-row__toggles">
                    <Toggle
                      label="Investimento"
                      ariaLabel={`Investimento ${account.name}`}
                      checked={account.investment}
                      disabled={pending}
                      onChange={(next) => void toggleFlag(account, { investment: next })}
                    />
                    <Toggle
                      label="Ripristina i cancellati"
                      ariaLabel={`Ripristina i movimenti cancellati di ${account.name}`}
                      checked={account.reimport_deleted}
                      disabled={pending}
                      onChange={(next) => void toggleFlag(account, { reimport_deleted: next })}
                    />
                    {account.connected ? null : (
                      <Toggle
                        label="Saldo dai movimenti"
                        ariaLabel={`Saldo dai movimenti di ${account.name}`}
                        checked={account.computed_balance}
                        disabled={pending}
                        onChange={(next) => void toggleFlag(account, { computed_balance: next })}
                      />
                    )}
                  </div>
                  {account.computed_balance ? (
                    <p className="hint">
                      Il patrimonio conta questo conto per quello che dicono i suoi movimenti; un
                      saldo dichiarato serve solo a verificarlo.
                    </p>
                  ) : null}
                  {account.reimport_deleted ? (
                    <p className="hint">
                      I movimenti cancellati di questo conto tornano al prossimo sync, con la loro
                      nota.
                    </p>
                  ) : null}
                  {trash.filter((item) => item.account.id === account.id).length === 0 ? null : (
                    <ul className="trash-list">
                      {trash
                        .filter((item) => item.account.id === account.id)
                        .map((item) => (
                          <li className="trash-row" key={item.id}>
                            <span className="trash-row__text">
                              <span className="txn__title">{item.merchant ?? item.description}</span>
                              {item.notes === null ? null : (
                                <span className="txn__note">{item.notes}</span>
                              )}
                              <span className="txn__meta">
                                <span>{formatDate(item.date)}</span>
                                <span>{formatAmount(item.amount)}</span>
                                <span>cancellato il {formatDate(item.deleted_at.slice(0, 10))}</span>
                              </span>
                            </span>
                            <button
                              type="button"
                              className="button"
                              disabled={pending}
                              onClick={() => void restore(item)}
                            >
                              Ripristina
                            </button>
                          </li>
                        ))}
                    </ul>
                  )}
                  {account.connected ? (
                    <PeriodSync
                      account={account}
                      held={held.filter((item) => item.account_id === account.id)}
                      onChanged={periodChanged}
                      onNotice={setNotice}
                    />
                  ) : null}
                  <div className="account-row__actions">
                    <button
                      type="button"
                      className="button"
                      disabled={pending}
                      onClick={() => setDeclareFor(account)}
                    >
                      Dichiara saldo
                    </button>
                    {account.verification.checks.map((check) => (
                      <button
                        type="button"
                        className="button"
                        key={`${check.kind}:${check.date}:${check.source}`}
                        disabled={pending}
                        title={`${check.source} del ${formatDate(check.date)}: banca ${formatAmount(
                          check.declared,
                        )}, ledger ${formatAmount(check.computed)}`}
                        onClick={() => void handleSetOpening(account, check)}
                      >
                        {`Allinea il saldo iniziale (${KIND_LABELS[check.kind].toLowerCase()})`}
                      </button>
                    ))}
                    {deletingFor === account.id ? null : (
                      <button
                        type="button"
                        className="button button--danger"
                        disabled={pending}
                        onClick={() => askDelete(account)}
                      >
                        Elimina conto
                      </button>
                    )}
                  </div>
                  {deletingFor === account.id ? (
                    <form
                      className="account-delete"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void deleteAccount(account);
                      }}
                    >
                      <p className="hint">
                        Elimina il conto con tutti i suoi movimenti, il cestino, i saldi dichiarati e
                        le regole ristrette a lui; se è collegato a una banca, il sync smette di
                        chiederlo. I giroconti con gli altri conti tornano da confermare. Non si
                        annulla: per tornare indietro serve uno snapshot.
                      </p>
                      <label className="field__label" htmlFor={`delete-${account.id}`}>
                        Scrivi «{account.name}» per confermare
                      </label>
                      <input
                        id={`delete-${account.id}`}
                        className="input"
                        type="text"
                        autoComplete="off"
                        value={typedName}
                        onChange={(event) => setTypedName(event.target.value)}
                      />
                      {deleteError === null ? null : (
                        <p className="state state--error" role="alert">
                          Conto non eliminato: {deleteError}
                        </p>
                      )}
                      <div className="account-row__actions">
                        <button
                          type="submit"
                          className="button button--danger"
                          disabled={pending || typedName.trim() !== account.name}
                        >
                          {pending ? "Elimino…" : "Elimina conto e movimenti"}
                        </button>
                        <button
                          type="button"
                          className="button"
                          disabled={pending}
                          onClick={() => setDeletingFor(null)}
                        >
                          Annulla
                        </button>
                      </div>
                    </form>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
        {trashError === null ? null : (
          <p className="state state--error" role="alert">
            Cestino non leggibile: {trashError}
          </p>
        )}
      </section>

      <DeclareSheet
        open={declareFor !== null}
        account={declareFor}
        onClose={() => setDeclareFor(null)}
        onDeclare={handleDeclare}
      />
      <NewAccountSheet open={newOpen} onClose={() => setNewOpen(false)} onCreate={handleCreate} />

      {notice !== null ? <Toast message={notice} onDismiss={() => setNotice(null)} /> : null}
    </section>
  );
}
