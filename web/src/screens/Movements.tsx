import { useEffect, useMemo, useRef, useState } from "react";

import { api, errorMessage } from "../api";
import { deletionNotice } from "../notices";
import { CategoryPicker } from "../components/CategoryPicker";
import { Toast } from "../components/Toast";
import { TransactionRow } from "../components/TransactionRow";
import { TransferPanel } from "../components/TransferPanel";
import { currentMonth, formatAmount, formatMonth, monthBounds, shiftMonth, toAmount } from "../format";
import type { Account, Category, Transaction } from "../types";
import type { ReviewQueueController } from "../useReviewQueue";
import { categoryText } from "../category";

const PAGE_SIZE = 100;

interface MovementsScreenProps {
  categories: Category[];
  categoriesError: string | null;
  onReloadCategories: () => void;
  onCategorize: ReviewQueueController["categorize"];
  /** A transfer changes what the queue has left, so its counts are refetched. */
  onReviewReload: () => void;
  /** Bumped after a sync: the list is what the ledger now holds, not what it held. */
  refreshToken: number;
}

function chronological(a: Transaction, b: Transaction): number {
  if (a.date !== b.date) return a.date < b.date ? -1 : 1;
  return a.id - b.id;
}

export function MovementsScreen({
  categories,
  categoriesError,
  onReloadCategories,
  onCategorize,
  onReviewReload,
  refreshToken,
}: MovementsScreenProps) {
  const [month, setMonth] = useState(currentMonth);
  const [accountId, setAccountId] = useState("");
  const [category, setCategory] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [items, setItems] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pickerFor, setPickerFor] = useState<Transaction | null>(null);
  const [transferFor, setTransferFor] = useState<Transaction | null>(null);
  const [transferFilter, setTransferFilter] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const latestRequest = useRef(0);

  const bounds = useMemo(() => monthBounds(month), [month]);

  const filters = useMemo(
    () => ({
      from: bounds.from,
      to: bounds.to,
      accountId: accountId === "" ? undefined : Number(accountId),
      category: category === "" ? undefined : category,
      search: search === "" ? undefined : search,
      transfer: transferFilter === "" ? undefined : transferFilter === "yes",
    }),
    [bounds, accountId, category, search, transferFilter],
  );

  useEffect(() => {
    const controller = new AbortController();
    const request = ++latestRequest.current;
    setLoading(true);
    api
      .transactions({ ...filters, limit: PAGE_SIZE, offset: 0 }, controller.signal)
      .then((page) => {
        if (request !== latestRequest.current) return;
        setItems(page.items);
        setTotal(page.total);
        setOffset(page.items.length);
        setLoadError(null);
        setLoading(false);
      })
      .catch((error) => {
        if (request !== latestRequest.current) return;
        setLoadError(errorMessage(error));
        setLoading(false);
      });
    return () => controller.abort();
  }, [filters, reloadKey, refreshToken]);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    const controller = new AbortController();
    api
      .accounts(controller.signal)
      .then(setAccounts)
      .catch(() => {
        // The account filter stays empty; the rest of the screen still works.
      });
    return () => controller.abort();
  }, []);

  const loadMore = async () => {
    const request = ++latestRequest.current;
    setLoading(true);
    try {
      const page = await api.transactions({ ...filters, limit: PAGE_SIZE, offset });
      if (request !== latestRequest.current) return;
      setItems((current) => [...current, ...page.items]);
      setTotal(page.total);
      setOffset(offset + page.items.length);
      setLoadError(null);
    } catch (error) {
      if (request !== latestRequest.current) return;
      setLoadError(errorMessage(error));
    } finally {
      if (request === latestRequest.current) setLoading(false);
    }
  };

  const runningTotals = useMemo(() => {
    const totals = new Map<number, number>();
    let sum = 0;
    for (const transaction of [...items].sort(chronological)) {
      sum += toAmount(transaction.amount);
      totals.set(transaction.id, sum);
    }
    return totals;
  }, [items]);

  const displayed = useMemo(
    () =>
      [...items].sort((a, b) => {
        if (a.date !== b.date) return a.date < b.date ? 1 : -1;
        return b.id - a.id;
      }),
    [items],
  );

  const loadedTotal = useMemo(
    () => items.reduce((sum, transaction) => sum + toAmount(transaction.amount), 0),
    [items],
  );

  const openRow = (transaction: Transaction) => {
    // A leg has no category to pick: its panel says what it is attached to.
    if (transaction.transfer !== null) setTransferFor(transaction);
    else setPickerFor(transaction);
  };

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Movimenti</h1>
          <p className="screen__subtitle">
            {formatMonth(month)} · {items.length} movimenti · totale {formatAmount(loadedTotal)}
            {items.length < total ? " (parziale)" : ""}
          </p>
        </div>
      </header>

      <div className="month-picker">
        <button
          type="button"
          className="button"
          onClick={() => setMonth(shiftMonth(month, -1))}
          aria-label="Mese precedente"
        >
          ‹
        </button>
        <label className="visually-hidden" htmlFor="month">
          Mese
        </label>
        <input
          id="month"
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

      <div className="filters">
        <div className="field">
          <label htmlFor="filter-account">Conto</label>
          <select id="filter-account" value={accountId} onChange={(event) => setAccountId(event.target.value)}>
            <option value="">Tutti i conti</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-category">Categoria</label>
          <select id="filter-category" value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="">Tutte le categorie</option>
            {categories.map((item) => (
              <option key={item.id} value={item.name}>
                {categoryText(item.name)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-transfer">Giroconti e rimborsi</label>
          <select
            id="filter-transfer"
            value={transferFilter}
            onChange={(event) => setTransferFilter(event.target.value)}
          >
            <option value="">Tutti i movimenti</option>
            <option value="yes">Solo giroconti e rimborsi</option>
            <option value="no">Esclusi giroconti e rimborsi</option>
          </select>
        </div>
        <div className="field field--wide">
          <label htmlFor="filter-search">Cerca</label>
          <input
            id="filter-search"
            type="search"
            placeholder="Descrizione, controparte o nota"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
        </div>
      </div>

      {loadError ? (
        <div className="state state--error" role="alert">
          <p>{loadError}</p>
        </div>
      ) : null}

      {loading && items.length === 0 ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : null}

      {!loading && !loadError && items.length === 0 ? (
        <p className="state">Nessun movimento per i filtri scelti.</p>
      ) : null}

      <ul className="txn-list">
        {displayed.map((transaction) => (
          <TransactionRow
            key={transaction.id}
            transaction={transaction}
            runningTotal={runningTotals.get(transaction.id)}
            onSelect={openRow}
          />
        ))}
      </ul>

      {items.length < total ? (
        <button
          type="button"
          className="button button--block"
          onClick={() => void loadMore()}
          disabled={loading}
        >
          {loading ? "Carico…" : `Carica altri (${total - items.length})`}
        </button>
      ) : null}

      <CategoryPicker
        open={pickerFor !== null}
        title={pickerFor ? `Categorizza «${pickerFor.merchant ?? pickerFor.description}»` : ""}
        merchant={pickerFor?.merchant ?? null}
        transaction={pickerFor}
        categories={categories}
        categoriesError={categoriesError}
        onReloadCategories={onReloadCategories}
        onCreateCategory={async (name) => {
          await api.createCategory(name);
          await onReloadCategories();
        }}
        onSaveSplits={async (splits) => {
          const transaction = pickerFor;
          if (!transaction) return;
          const updated = await api.setSplits(transaction.id, splits);
          setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
          setPickerFor(null);
        }}
        onSaveNotes={async (notes) => {
          const transaction = pickerFor;
          if (!transaction) return;
          const updated = await api.setNotes(transaction.id, notes);
          setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
          setPickerFor(updated);
        }}
        onDelete={async () => {
          const transaction = pickerFor;
          if (!transaction) return;
          const deleted = await api.deleteTransaction(transaction.id);
          setItems((current) => current.filter((item) => item.id !== deleted.id));
          setTotal((current) => current - 1);
          setPickerFor(null);
          setNotice(deletionNotice(deleted));
          onReviewReload();
        }}
        onSelect={(chosenCategory, options) => {
          const transaction = pickerFor;
          setPickerFor(null);
          if (!transaction) return;
          setItems((current) =>
            current.map((item) => (item.id === transaction.id ? { ...item, category: chosenCategory } : item)),
          );
          void onCategorize(transaction, chosenCategory, options).then((saved) => {
            if (saved) return;
            setItems((current) =>
              current.map((item) => (item.id === transaction.id ? { ...item, category: transaction.category } : item)),
            );
          });
        }}
        onTransfer={() => {
          const transaction = pickerFor;
          setPickerFor(null);
          setTransferFor(transaction);
        }}
        onClose={() => setPickerFor(null)}
      />

      <TransferPanel
        open={transferFor !== null}
        transaction={transferFor}
        onDone={(message) => {
          setNotice(message);
          // The ledger changed under the list, and the queue's counts with it.
          setOffset(0);
          setItems([]);
          setReloadKey((key) => key + 1);
          onReviewReload();
        }}
        onClose={() => setTransferFor(null)}
      />

      {notice ? <Toast message={notice} onDismiss={() => setNotice(null)} /> : null}
    </section>
  );
}
