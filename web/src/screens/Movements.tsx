import { useEffect, useMemo, useRef, useState } from "react";

import { api, errorMessage } from "../api";
import { deletionNotice } from "../notices";
import { CategoryPicker } from "../components/CategoryPicker";
import { RuleSheet, merchantDraft } from "../components/RuleSheet";
import { Toast } from "../components/Toast";
import { TransactionRow } from "../components/TransactionRow";
import { TransferPanel } from "../components/TransferPanel";
import { currentMonth, formatAmount, formatMonth, monthBounds, shiftMonth, toAmount } from "../format";
import type { Account, Category, RuleDraft, Transaction } from "../types";
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
  /** Writes a rule; answers the error to show in its sheet, or null once saved. */
  onSaveRule: (draft: RuleDraft) => Promise<string | null>;
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
  onSaveRule,
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
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  // The rule a movement's sheet asked for: it opens once the category is chosen,
  // with the merchant's text to edit, and writes nothing until it is saved.
  const [ruleFor, setRuleFor] = useState<{ transaction: Transaction; category: string } | null>(null);
  // Choosing rows for one action on all of them: a tap picks instead of opening.
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [batchCategory, setBatchCategory] = useState("");
  const [confirmingBatchDelete, setConfirmingBatchDelete] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const latestRequest = useRef(0);

  const bounds = useMemo(() => monthBounds(month), [month]);
  // What the closed bar does not show: the selects that narrow the list.
  const activeFilters = [accountId, category, transferFilter].filter((value) => value !== "").length;

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
        // A selection is of the rows on screen: a new page is new rows.
        setSelected(new Set());
        setConfirmingBatchDelete(false);
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
    if (selecting) {
      toggleSelected(transaction.id);
      return;
    }
    // A leg has no category to pick: its panel says what it is attached to.
    if (transaction.transfer !== null) setTransferFor(transaction);
    else setPickerFor(transaction);
  };

  const toggleSelected = (id: number) => {
    setConfirmingBatchDelete(false);
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allSelected = displayed.length > 0 && displayed.every((item) => selected.has(item.id));

  const stopSelecting = () => {
    setSelecting(false);
    setSelected(new Set());
    setConfirmingBatchDelete(false);
  };

  // What the ledger holds changed under the list, and the queue's counts with it.
  const reloadAll = () => {
    setOffset(0);
    setItems([]);
    setReloadKey((key) => key + 1);
    onReviewReload();
  };

  const deleteSelected = async () => {
    if (selected.size === 0 || batchBusy) return;
    setBatchBusy(true);
    try {
      const outcome = await api.deleteTransactions([...selected]);
      const what =
        outcome.deleted === 1 ? "Cancellato 1 movimento" : `Cancellati ${outcome.deleted} movimenti`;
      setNotice(
        `${what}: sono nel cestino dei loro conti, in Conti.${
          outcome.unlinked_pairs > 0 ? " I giroconti di cui facevano parte sono stati sciolti." : ""
        }`,
      );
      stopSelecting();
      reloadAll();
    } catch (error) {
      setNotice(`Movimenti non cancellati: ${errorMessage(error)}`);
    } finally {
      setBatchBusy(false);
    }
  };

  const categorizeSelected = async () => {
    if (selected.size === 0 || batchCategory === "" || batchBusy) return;
    setBatchBusy(true);
    try {
      const outcome = await api.categorizeTransactions([...selected], batchCategory);
      const done = `${outcome.categorized} ${outcome.categorized === 1 ? "movimento" : "movimenti"}`;
      const left =
        outcome.skipped > 0
          ? ` · ${outcome.skipped} lasciati com'erano: giroconti o divisi in più categorie, si decidono aprendoli`
          : "";
      setNotice(`${categoryText(batchCategory)}: ${done}${left}`);
      stopSelecting();
      reloadAll();
    } catch (error) {
      setNotice(`Categoria non assegnata: ${errorMessage(error)}`);
    } finally {
      setBatchBusy(false);
    }
  };

  const saveRule = async (draft: RuleDraft): Promise<string | null> => {
    const asked = ruleFor;
    const message = await onSaveRule(draft);
    if (message !== null) return message;
    setRuleFor(null);
    // The movement the rule was asked from takes the category chosen for it even
    // when the text was edited so that the rule no longer reaches it.
    if (asked !== null && draft.action === "category" && draft.target) {
      await onCategorize(asked.transaction, draft.target);
    }
    setNotice(`Regola salvata: «${draft.pattern}»`);
    reloadAll();
    return null;
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
        <div className="screen__actions">
          <button
            type="button"
            className="button"
            onClick={() => (selecting ? stopSelecting() : setSelecting(true))}
            disabled={!selecting && displayed.length === 0}
          >
            {selecting ? "Fine" : "Seleziona"}
          </button>
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

      {/* The search is what a person reaches for, so it stays on the bar; the three
          selects are one tap away below 1024 and beside it above. Four labelled
          fields stacked one under the other pushed the first movement half a
          screen down. Each select says what it holds in its own first option. */}
      <div className="movement-filters">
        <div className="movement-filters__bar">
          <input
            id="filter-search"
            className="input movement-filters__search"
            type="search"
            aria-label="Cerca nei movimenti"
            placeholder="Cerca, anche nelle note"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
          <button
            type="button"
            className="button movement-filters__toggle"
            aria-expanded={filtersOpen}
            aria-controls="movement-filters-more"
            onClick={() => setFiltersOpen(!filtersOpen)}
          >
            {activeFilters === 0 ? "Filtri" : `Filtri · ${activeFilters}`}
          </button>
        </div>
        <div
          id="movement-filters-more"
          className="movement-filters__more"
          data-open={filtersOpen ? "true" : "false"}
        >
          <select
            className="input"
            aria-label="Conto"
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
          >
            <option value="">Tutti i conti</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
          <select
            className="input"
            aria-label="Categoria"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            <option value="">Tutte le categorie</option>
            {categories.map((item) => (
              <option key={item.id} value={item.name}>
                {categoryText(item.name)}
              </option>
            ))}
          </select>
          <select
            className="input"
            aria-label="Giroconti e rimborsi"
            value={transferFilter}
            onChange={(event) => setTransferFilter(event.target.value)}
          >
            <option value="">Con giroconti e rimborsi</option>
            <option value="yes">Solo giroconti e rimborsi</option>
            <option value="no">Senza giroconti e rimborsi</option>
          </select>
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

      {/* L'intestazione della tabella: esiste solo dove la riga ha le colonne da
          nominare (sopra i 1024) e solo quando c'è almeno una riga sotto. Le
          righe dicono già tutto nella loro etichetta, quindi questa non c'è per
          chi ascolta. */}
      {selecting ? (
        <div className="batch-bar" role="region" aria-label="Azioni sui movimenti selezionati">
          <p className="batch-bar__count">
            {selected.size === 0
              ? "Tocca i movimenti da scegliere"
              : `${selected.size} ${selected.size === 1 ? "selezionato" : "selezionati"}`}
          </p>
          <button
            type="button"
            className="button"
            onClick={() => {
              setConfirmingBatchDelete(false);
              setSelected(allSelected ? new Set() : new Set(displayed.map((item) => item.id)));
            }}
            disabled={displayed.length === 0 || batchBusy}
          >
            {allSelected ? "Deseleziona tutti" : `Seleziona tutti (${displayed.length})`}
          </button>
          <select
            className="input"
            aria-label="Categoria da assegnare ai selezionati"
            value={batchCategory}
            onChange={(event) => setBatchCategory(event.target.value)}
            disabled={batchBusy}
          >
            <option value="">Categoria…</option>
            {categories.map((item) => (
              <option key={item.id} value={item.name}>
                {categoryText(item.name)}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="button"
            onClick={() => void categorizeSelected()}
            disabled={selected.size === 0 || batchCategory === "" || batchBusy}
          >
            Assegna
          </button>
          {confirmingBatchDelete ? (
            <>
              <button
                type="button"
                className="button button--danger"
                onClick={() => void deleteSelected()}
                disabled={batchBusy}
              >
                {batchBusy ? "Cancello…" : `Sì, cancella ${selected.size}`}
              </button>
              <button
                type="button"
                className="button"
                onClick={() => setConfirmingBatchDelete(false)}
                disabled={batchBusy}
              >
                No
              </button>
            </>
          ) : (
            <button
              type="button"
              className="button button--danger"
              onClick={() => setConfirmingBatchDelete(true)}
              disabled={selected.size === 0 || batchBusy}
            >
              Cancella
            </button>
          )}
        </div>
      ) : null}

      {displayed.length > 0 ? (
        <div className="txn-head" aria-hidden="true">
          <span>Data</span>
          <span>Descrizione</span>
          <span>Categoria</span>
          <span>Conto</span>
          <span>Importo</span>
        </div>
      ) : null}

      <ul className="txn-list">
        {displayed.map((transaction) => (
          <TransactionRow
            key={transaction.id}
            transaction={transaction}
            runningTotal={runningTotals.get(transaction.id)}
            onSelect={openRow}
            selected={selecting ? selected.has(transaction.id) : undefined}
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
          if (options.rule) {
            // The rule is a statement about movements the bank has not printed
            // yet, so its text is written before anything is saved.
            setRuleFor({ transaction, category: chosenCategory });
            return;
          }
          setItems((current) =>
            current.map((item) => (item.id === transaction.id ? { ...item, category: chosenCategory } : item)),
          );
          void onCategorize(transaction, chosenCategory).then((saved) => {
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

      {ruleFor === null ? null : (
        <RuleSheet
          title={`Una regola da «${ruleFor.transaction.merchant ?? ruleFor.transaction.description}»`}
          initial={merchantDraft(
            ruleFor.transaction.merchant ?? ruleFor.transaction.description,
            ruleFor.category,
          )}
          categories={categories}
          onSave={saveRule}
          onClose={() => setRuleFor(null)}
        />
      )}

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
