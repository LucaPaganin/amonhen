import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { MouseEvent } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { Toast } from "../components/Toast";
import { Toggle } from "../components/Toggle";
import { currentMonth, formatAmount, formatDate, formatMonth, shiftMonth, toAmount } from "../format";
import type {
  Account,
  AccountVerification,
  AssistantContext,
  Budget,
  DeclaredBalanceCheck,
  Declaration,
  NewAccount,
} from "../types";
import { useAccounts } from "../useAccounts";
import { categoryText } from "../category";

interface AccountsScreenProps {
  /** Opens the assistant on one budget: the question is born at that row. */
  onAskAssistant: (context: AssistantContext) => void;
}

/** The two figures a bank reports, in the words the form offers. */
const KIND_LABELS: Record<Declaration["kind"], string> = {
  available: "Disponibile",
  booked: "Contabilizzata",
};

/** What declaring a figure is for: it says whether the bank and the ledger agree. */
const VERIFICATION_OUTCOMES: Record<AccountVerification["state"], string> = {
  verified: "banca e ledger concordano",
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
function verificationLabel(checks: DeclaredBalanceCheck[]): string {
  const failed = checks.filter((check) => !check.ok);
  if (failed.length === 1 && failed[0].kind === "available") return "non torna sui sospesi";
  if (failed.length === 1 && failed[0].kind === "booked") return "non torna sul contabile";
  return `discrepanza ${formatAmount(failed[0].difference)}`;
}

/** The numbers behind the chip, for whoever can hover. */
function verificationDetail(verification: AccountVerification): string {
  return verification.checks
    .map(
      (check) =>
        `${check.source} del ${formatDate(check.date)}: banca ${formatAmount(check.declared)}, ` +
        `ledger ${formatAmount(check.computed)}`,
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
  return (
    <span
      className={`chip flag-row__check ${
        verification.state === "verified" ? "chip--verified" : "chip--warning"
      }`}
      title={verificationDetail(verification)}
    >
      {verification.state === "verified"
        ? `verificato al ${formatDate(verification.date)}`
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

export function AccountsScreen({ onAskAssistant }: AccountsScreenProps) {
  const {
    accounts,
    error: accountsError,
    loading: accountsLoading,
    reload: reloadAccounts,
    setInvestment,
    createAccount,
    declareBalance,
    setOpening,
  } = useAccounts();

  const [pendingAccounts, setPendingAccounts] = useState<number[]>([]);
  const [declareFor, setDeclareFor] = useState<Account | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const [month, setMonth] = useState(currentMonth);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [budgetsLoading, setBudgetsLoading] = useState(true);
  const [budgetsError, setBudgetsError] = useState<string | null>(null);
  const [editingBudget, setEditingBudget] = useState<number | null>(null);
  const [budgetDraft, setBudgetDraft] = useState("");
  const [pendingBudget, setPendingBudget] = useState<number | null>(null);

  const loadBudgets = useCallback(async (value: string, signal?: AbortSignal) => {
    setBudgetsLoading(true);
    try {
      setBudgets(await api.budgets(value, signal));
      setBudgetsError(null);
    } catch (caught) {
      if (isAbortError(caught)) return;
      setBudgetsError(errorMessage(caught));
    } finally {
      setBudgetsLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadBudgets(month, controller.signal);
    return () => controller.abort();
  }, [loadBudgets, month]);

  const applyBudget = async (budget: Budget, amount: string | null) => {
    if (pendingBudget !== null) return;
    setPendingBudget(budget.id);
    try {
      const updated = await api.setBudget(budget.id, amount, month);
      setBudgets((current) => current.map((row) => (row.id === budget.id ? updated : row)));
      setEditingBudget(null);
      setNotice(
        amount === null
          ? `Budget di ${categoryText(budget.category)} rimosso`
          : `Budget di ${categoryText(budget.category)} salvato`,
      );
    } catch (caught) {
      setNotice(`Budget non salvato: ${errorMessage(caught)}`);
    } finally {
      setPendingBudget(null);
    }
  };

  const saveBudget = async (budget: Budget) => {
    const value = budgetDraft.trim().replace(",", ".");
    if (!/^\d+(\.\d{1,2})?$/.test(value)) {
      setNotice("Importo non valido: usa cifre e al massimo due decimali.");
      return;
    }
    await applyBudget(budget, value);
  };

  const toggleInvestment = async (account: Account, next: boolean) => {
    if (pendingAccounts.includes(account.id)) return;
    setPendingAccounts((current) => [...current, account.id]);
    const message = await setInvestment(account.id, next);
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
          <h1 className="screen__title">Conti e budget</h1>
          <p className="screen__subtitle">
            I conti reali, il loro saldo di partenza e quanto hai deciso di spendere.
          </p>
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
                      onChange={(next) => void toggleInvestment(account, next)}
                    />
                  </div>
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
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="panel">
        <h2 className="section-title">
          Budget <span className="count">{formatMonth(month)}</span>
        </h2>
        <div className="month-picker">
          <button
            type="button"
            className="button"
            onClick={() => setMonth(shiftMonth(month, -1))}
            aria-label="Mese precedente"
          >
            ‹
          </button>
          <label className="visually-hidden" htmlFor="budget-month">
            Mese
          </label>
          <input
            id="budget-month"
            className="month-picker__input"
            type="month"
            value={month}
            onChange={(event) => {
              if (event.target.value !== "") setMonth(event.target.value);
            }}
          />
          <button
            type="button"
            className="button"
            onClick={() => setMonth(shiftMonth(month, 1))}
            aria-label="Mese successivo"
          >
            ›
          </button>
        </div>
        {budgetsError !== null ? (
          <div className="state state--error" role="alert">
            <p>Impossibile caricare i budget: {budgetsError}</p>
            <button type="button" className="button" onClick={() => void loadBudgets(month)}>
              Riprova
            </button>
          </div>
        ) : budgetsLoading && budgets.length === 0 ? (
          <p className="state" aria-busy="true">
            Caricamento…
          </p>
        ) : budgets.length === 0 ? (
          <p className="state">Nessuna categoria su cui impostare un budget.</p>
        ) : (
          <>
            {budgets.every((row) => row.budget === null) ? (
              <p className="state">
                Nessun budget impostato: apri una categoria per fissare quanto vuoi spendere questo
                mese.
              </p>
            ) : null}
            <ul className="budget-list">
              {budgets.map((budget) => {
                const remaining = budget.remaining === null ? null : toAmount(budget.remaining);
                const overspend = remaining !== null && remaining < 0 ? -remaining : null;
                const editing = editingBudget === budget.id;
                const pending = pendingBudget === budget.id;
                return (
                  <li
                    className={overspend !== null ? "budget-row budget-row--over" : "budget-row"}
                    key={budget.id}
                  >
                    <div className="budget-row__head">
                      <span className="budget-row__name">{categoryText(budget.category)}</span>
                      <span className="budget-row__spent">{formatAmount(budget.spent)} spesi</span>
                    </div>
                    <p className="budget-row__status">
                      {budget.budget === null ? (
                        "Nessun budget impostato"
                      ) : overspend !== null ? (
                        <>
                          Budget {formatAmount(budget.budget)} ·{" "}
                          <strong className="budget-row__over">
                            sforato di {formatAmount(overspend)}
                          </strong>
                        </>
                      ) : (
                        <>
                          Budget {formatAmount(budget.budget)} · restano{" "}
                          {formatAmount(remaining ?? 0)}
                        </>
                      )}
                    </p>
                    {editing ? (
                      <form
                        className="budget-editor"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void saveBudget(budget);
                        }}
                      >
                        <label className="visually-hidden" htmlFor={`budget-${budget.id}`}>
                          Budget mensile per {categoryText(budget.category)}
                        </label>
                        <input
                          id={`budget-${budget.id}`}
                          className="input"
                          type="text"
                          inputMode="decimal"
                          placeholder="0,00"
                          value={budgetDraft}
                          onChange={(event) => setBudgetDraft(event.target.value)}
                          autoFocus
                        />
                        <button
                          type="submit"
                          className="button button--primary"
                          disabled={pending || budgetDraft.trim() === ""}
                        >
                          {pending ? "Salvo…" : "Salva"}
                        </button>
                        <button
                          type="button"
                          className="button"
                          onClick={() => setEditingBudget(null)}
                        >
                          Annulla
                        </button>
                        {budget.budget !== null ? (
                          <button
                            type="button"
                            className="button button--danger"
                            disabled={pending}
                            onClick={() => void applyBudget(budget, null)}
                          >
                            Rimuovi
                          </button>
                        ) : null}
                      </form>
                    ) : (
                      <div className="budget-row__actions">
                        {budget.budget === null ? null : (
                          <button
                            type="button"
                            className="button"
                            onClick={() => onAskAssistant({ kind: "budget", id: budget.id })}
                          >
                            Regge?
                          </button>
                        )}
                        <button
                          type="button"
                          className="button"
                          onClick={() => {
                            setEditingBudget(budget.id);
                            setBudgetDraft(budget.budget === null ? "" : budget.budget);
                          }}
                        >
                          {budget.budget === null ? "Imposta budget" : "Modifica"}
                        </button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
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
