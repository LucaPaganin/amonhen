import { useCallback, useEffect, useMemo, useState } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { FlowsChart, NetWorthChart, SpendingLegend, SpendingPie } from "../components/Charts";
import {
  currentMonth,
  formatAmount,
  formatDate,
  formatMonth,
  formatMonths,
  shiftMonth,
  toAmount,
} from "../format";
import type {
  AccountRef,
  Anomaly,
  AssistantContext,
  Category,
  DashboardFilters,
  Flows,
  Metrics,
  NetWorth,
  Spending,
} from "../types";
import { categoryText } from "../category";

/** The period the dashboard opens on: the year the flows chart has always shown. */
const DEFAULT_MONTHS = 12;
/** The periods the quick chips offer, in months. */
const PERIODS = [3, 6, 12, 24];

interface DashboardScreenProps {
  categories: Category[];
  /** Opens the assistant on this reading: the question is born at the chart. */
  onAskAssistant: (context: AssistantContext) => void;
}

interface MetricCard {
  key: string;
  label: string;
  value: string | null;
  empty: string;
  explanation: string;
  warning: string | null;
}

export function DashboardScreen({ categories, onAskAssistant }: DashboardScreenProps) {
  const [fromMonth, setFromMonth] = useState(() => shiftMonth(currentMonth(), -(DEFAULT_MONTHS - 1)));
  const [toMonth, setToMonth] = useState(currentMonth);
  const [scopedAccounts, setScopedAccounts] = useState<string[]>([]);
  const [scopedCategory, setScopedCategory] = useState("");
  const [accounts, setAccounts] = useState<AccountRef[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [spending, setSpending] = useState<Spending | null>(null);
  const [spendingError, setSpendingError] = useState<string | null>(null);
  const [flows, setFlows] = useState<Flows | null>(null);
  const [flowsError, setFlowsError] = useState<string | null>(null);
  const [netWorth, setNetWorth] = useState<NetWorth | null>(null);
  const [netWorthError, setNetWorthError] = useState<string | null>(null);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [anomaliesLoading, setAnomaliesLoading] = useState(true);
  const [anomaliesError, setAnomaliesError] = useState<string | null>(null);

  const filters = useMemo<DashboardFilters>(
    () => ({
      from: fromMonth,
      to: toMonth,
      accounts: scopedAccounts,
      categories: scopedCategory === "" ? [] : [scopedCategory],
    }),
    [fromMonth, toMonth, scopedAccounts, scopedCategory],
  );

  const loadMetrics = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      try {
        setMetrics(await api.metrics(filters, signal));
        setLoadError(null);
      } catch (caught) {
        if (isAbortError(caught)) return;
        setLoadError(errorMessage(caught));
      } finally {
        setLoading(false);
      }
    },
    [filters],
  );

  const loadSpending = useCallback(
    async (signal?: AbortSignal) => {
      try {
        setSpending(await api.spending(filters, signal));
        setSpendingError(null);
      } catch (caught) {
        if (isAbortError(caught)) return;
        setSpendingError(errorMessage(caught));
      }
    },
    [filters],
  );

  const loadFlows = useCallback(
    async (signal?: AbortSignal) => {
      try {
        setFlows(await api.flows(filters, signal));
        setFlowsError(null);
      } catch (caught) {
        if (isAbortError(caught)) return;
        setFlowsError(errorMessage(caught));
      }
    },
    [filters],
  );

  const loadNetWorth = useCallback(
    async (signal?: AbortSignal) => {
      try {
        setNetWorth(await api.netWorth(filters, signal));
        setNetWorthError(null);
      } catch (caught) {
        if (isAbortError(caught)) return;
        setNetWorthError(errorMessage(caught));
      }
    },
    [filters],
  );

  // One period read four ways: a filter change refetches all of them together,
  // so the pie, the bars and the line can never describe different windows.
  useEffect(() => {
    const controller = new AbortController();
    void loadMetrics(controller.signal);
    void loadSpending(controller.signal);
    void loadFlows(controller.signal);
    void loadNetWorth(controller.signal);
    return () => controller.abort();
  }, [loadMetrics, loadSpending, loadFlows, loadNetWorth]);

  const loadAnomalies = useCallback(async (signal?: AbortSignal) => {
    setAnomaliesLoading(true);
    try {
      setAnomalies(await api.anomalies(31, signal));
      setAnomaliesError(null);
    } catch (caught) {
      if (isAbortError(caught)) return;
      setAnomaliesError(errorMessage(caught));
    } finally {
      setAnomaliesLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadAnomalies(controller.signal);
    return () => controller.abort();
  }, [loadAnomalies]);

  // The chips need the names only, and a filter that cannot list the accounts
  // still works: it just offers none.
  useEffect(() => {
    const controller = new AbortController();
    api
      .accounts(controller.signal)
      .then(setAccounts)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const cards = useMemo<MetricCard[]>(() => {
    if (!metrics) return [];
    const months = metrics.months_of_history;
    const partialBurn = metrics.partial ? `storico parziale: ${months} mesi su 6` : null;
    const partialEpisodic = metrics.episodic_partial ? `storico parziale: ${months} mesi su 24` : null;
    const partialExpected = [partialBurn, partialEpisodic].filter(Boolean).join(" · ") || null;
    const amount = (value: string | null) => (value === null ? null : formatAmount(value));

    return [
      {
        key: "recurring_burn",
        label: "Burn ricorrente",
        value: amount(metrics.recurring_burn),
        empty: "non disponibile",
        explanation:
          "Mediana mobile delle spese non episodiche degli ultimi 6 mesi: quanto spendi di norma ogni mese.",
        warning: partialBurn,
      },
      {
        key: "episodic_accrual",
        label: "Accantonamento episodico",
        value: amount(metrics.episodic_accrual),
        empty: "non disponibile",
        explanation:
          "Somma delle spese una tantum degli ultimi 24 mesi divisa per 24: la quota mensile da mettere da parte per gli imprevisti.",
        warning: partialEpisodic,
      },
      {
        key: "expected_burn",
        label: "Burn atteso",
        value: amount(metrics.expected_burn),
        empty: "non disponibile",
        explanation: "Burn ricorrente più accantonamento episodico: la spesa mensile attesa.",
        warning: partialExpected,
      },
      {
        key: "runway_months",
        label: "Runway stressato",
        value: metrics.runway_months === null ? null : formatMonths(metrics.runway_months),
        empty: "non calcolabile",
        explanation:
          "Liquidità divisa per burn atteso: quanti mesi copri se le entrate si fermano.",
        warning: null,
      },
      {
        key: "liquidity",
        label: "Liquidità",
        value: amount(metrics.liquidity),
        empty: "non disponibile",
        explanation: "Somma dei saldi dei conti reali scelti, alla data della stima.",
        warning: null,
      },
      {
        key: "essential_monthly",
        label: "Quota incomprimibile",
        value: amount(metrics.essential_monthly),
        empty: "non disponibile",
        explanation:
          "Spese non episodiche delle categorie contrassegnate come incomprimibili: quanto non è tagliabile.",
        warning: null,
      },
      {
        key: "discretionary_monthly",
        label: "Quota discrezionale",
        value: amount(metrics.discretionary_monthly),
        empty: "non disponibile",
        explanation:
          "Spese non episodiche delle altre categorie: quanto potresti tagliare se servisse.",
        warning: null,
      },
      {
        key: "savings_flow",
        label: "Flusso di risparmio",
        value: amount(metrics.savings_flow),
        empty: "non disponibile",
        explanation:
          "Trasferimenti verso i conti contrassegnati come investimento: l'unico ponte tra le spese e il patrimonio.",
        warning: null,
      },
    ];
  }, [metrics]);

  const refreshAll = () => {
    void loadMetrics();
    void loadSpending();
    void loadFlows();
    void loadNetWorth();
    void loadAnomalies();
  };

  const applyPeriod = (months: number) => {
    setToMonth(currentMonth());
    setFromMonth(shiftMonth(currentMonth(), -(months - 1)));
  };

  const presetActive = (months: number) =>
    toMonth === currentMonth() && fromMonth === shiftMonth(currentMonth(), -(months - 1));

  const toggleAccount = (name: string) => {
    setScopedAccounts((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
    );
  };

  const periodChip =
    fromMonth === toMonth
      ? formatMonth(fromMonth)
      : `${formatMonth(fromMonth)} – ${formatMonth(toMonth)}`;

  const subtitle = metrics
    ? `${periodChip} · burn su ${metrics.months_of_history} ${
        metrics.months_of_history === 1 ? "mese" : "mesi"
      } di storico`
    : "Caricamento…";

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Dashboard</h1>
          <p className="screen__subtitle">{subtitle}</p>
        </div>
        <div className="screen__actions">
          <button
            type="button"
            className="button"
            onClick={() => onAskAssistant({ kind: "cruscotto" })}
          >
            Cosa è cambiato?
          </button>
          <button type="button" className="button" onClick={refreshAll} disabled={loading}>
            Aggiorna
          </button>
        </div>
      </header>

      <section className="panel">
        <h2 className="section-title">
          Filtri{" "}
          <span className="count">
            {scopedAccounts.length === 0 && scopedCategory === "" ? "tutto il ledger" : periodChip}
          </span>
        </h2>
        <div className="filters">
          <div className="field">
            <label htmlFor="filter-from">Dal mese</label>
            <input
              id="filter-from"
              className="input"
              type="month"
              value={fromMonth}
              onChange={(event) => event.target.value && setFromMonth(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="filter-to">Al mese</label>
            <input
              id="filter-to"
              className="input"
              type="month"
              value={toMonth}
              onChange={(event) => event.target.value && setToMonth(event.target.value)}
            />
          </div>
          <div className="field">
            <span className="filters__caption">Periodo rapido</span>
            <div className="filters__chips" role="group" aria-label="Scegli il periodo">
              {PERIODS.map((months) => (
                <button
                  key={months}
                  type="button"
                  className={presetActive(months) ? "chip chip--toggle chip--on" : "chip chip--toggle"}
                  aria-pressed={presetActive(months)}
                  onClick={() => applyPeriod(months)}
                >
                  {months} mesi
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <span className="filters__caption">Conti</span>
            <div className="filters__chips" role="group" aria-label="Filtra per conto">
              <button
                type="button"
                className={
                  scopedAccounts.length === 0 ? "chip chip--toggle chip--on" : "chip chip--toggle"
                }
                aria-pressed={scopedAccounts.length === 0}
                onClick={() => setScopedAccounts([])}
              >
                Tutti
              </button>
              {accounts.map((account) => {
                const on = scopedAccounts.includes(account.name);
                return (
                  <button
                    key={account.id}
                    type="button"
                    className={on ? "chip chip--toggle chip--on" : "chip chip--toggle"}
                    aria-pressed={on}
                    onClick={() => toggleAccount(account.name)}
                  >
                    {account.name}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="field">
            <label htmlFor="filter-category">Categoria</label>
            <select
              id="filter-category"
              value={scopedCategory}
              onChange={(event) => setScopedCategory(event.target.value)}
            >
              <option value="">Tutte le categorie</option>
              {categories.map((category) => (
                <option key={category.id} value={category.name}>
                  {categoryText(category.name)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <p className="chart-note">
          Il periodo decide i grafici; i conti restringono tutto ciò che è di conto, la categoria
          solo le spese. Le card delle metriche tengono le loro finestre di 6 e 24 mesi.
        </p>
      </section>

      {loadError ? (
        <div className="state state--error" role="alert">
          <p>{loadError}</p>
          <button type="button" className="button" onClick={() => void loadMetrics()}>
            Riprova
          </button>
        </div>
      ) : null}

      {loading && metrics === null ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : null}

      <section className="panel">
        <h2 className="section-title">
          Spese per categoria <span className="count">{periodChip}</span>
        </h2>
        {spendingError ? (
          <div className="state state--error" role="alert">
            <p>Impossibile caricare le spese: {spendingError}</p>
            <button type="button" className="button" onClick={() => void loadSpending()}>
              Riprova
            </button>
          </div>
        ) : spending === null ? (
          <p className="state" aria-busy="true">
            Caricamento…
          </p>
        ) : spending.categories.length === 0 ? (
          <p className="state state--empty">Nessuna spesa registrata nel periodo.</p>
        ) : (
          <>
            <SpendingPie categories={spending.categories} total={spending.total} />
            <SpendingLegend categories={spending.categories} total={spending.total} />
          </>
        )}
      </section>

      <section className="panel">
        <h2 className="section-title">
          Entrate e uscite <span className="count">{periodChip}</span>
        </h2>
        {flowsError ? (
          <div className="state state--error" role="alert">
            <p>Impossibile caricare il bilancio mensile: {flowsError}</p>
            <button type="button" className="button" onClick={() => void loadFlows()}>
              Riprova
            </button>
          </div>
        ) : flows === null ? (
          <p className="state" aria-busy="true">
            Caricamento…
          </p>
        ) : flows.months.every(
            (month) => toAmount(month.income) === 0 && toAmount(month.expenses) === 0,
          ) ? (
          <p className="state state--empty">Nessun movimento nel periodo.</p>
        ) : (
          <>
            <FlowsChart months={flows.months} />
            <p className="chart-note">
              Entrate in verde, uscite in rosso. Il mese in corso è in trasparenza: non è finito.
            </p>
          </>
        )}
      </section>

      <section className="panel">
        <h2 className="section-title">
          Patrimonio <span className="count">{periodChip}</span>
        </h2>
        {netWorthError ? (
          <div className="state state--error" role="alert">
            <p>Impossibile caricare i saldi: {netWorthError}</p>
            <button type="button" className="button" onClick={() => void loadNetWorth()}>
              Riprova
            </button>
          </div>
        ) : netWorth === null ? (
          <p className="state" aria-busy="true">
            Caricamento…
          </p>
        ) : netWorth.points.length === 0 ? (
          <p className="state state--empty">
            Nessun saldo osservato nel periodo: il primo sync registra il saldo di ogni conto.
          </p>
        ) : netWorth.points.length === 1 ? (
          <p className="state">
            Prima rilevazione: {formatAmount(netWorth.points[0].total)} al{" "}
            {formatDate(netWorth.points[0].date)}. La curva compare dalla seconda.
          </p>
        ) : (
          <NetWorthChart points={netWorth.points} />
        )}
        {netWorth && netWorth.accounts.length > 0 ? (
          <>
            <ul className="chart-legend">
              {netWorth.accounts.map((item) => (
                <li className="chart-legend__row" key={item.account}>
                  <span className="chart-legend__name">{item.account}</span>
                  <span className="chart-legend__share">{formatDate(item.date)}</span>
                  <span className="chart-legend__value">{formatAmount(item.balance)}</span>
                </li>
              ))}
            </ul>
            <p className="chart-note">
              Saldi riferiti dalla banca, non ricostruiti: la curva parte dalla prima rilevazione,
              e la legenda è l&apos;ultimo saldo noto di ogni conto.
            </p>
          </>
        ) : null}
      </section>

      {metrics && (metrics.partial || metrics.episodic_partial) ? (
        <p className="banner banner--warning" role="note">
          Storico parziale: {metrics.months_of_history}{" "}
          {metrics.months_of_history === 1 ? "mese" : "mesi"} disponibili.
          {metrics.partial ? " Il burn ricorrente usa 6 mesi." : ""}
          {metrics.episodic_partial ? " L'accantonamento episodico usa 24 mesi." : ""}
        </p>
      ) : null}

      {metrics ? (
        <ul className="metrics">
          {cards.map((card) => (
            <li className="metric" key={card.key}>
              <div className="metric__head">
                <h2 className="metric__label">{card.label}</h2>
                <span className={card.value === null ? "metric__value metric__value--empty" : "metric__value"}>
                  {card.value ?? card.empty}
                </span>
              </div>
              <p className="metric__note">{card.explanation}</p>
              {card.warning ? (
                <p className="metric__warning" role="note">
                  {card.warning}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <section className="panel">
        <h2 className="section-title">
          Anomalie <span className="count">{anomalies.length}</span>
        </h2>
        {anomaliesError ? (
          <div className="state state--error" role="alert">
            <p>Impossibile caricare le anomalie: {anomaliesError}</p>
            <button type="button" className="button" onClick={() => void loadAnomalies()}>
              Riprova
            </button>
          </div>
        ) : anomaliesLoading && anomalies.length === 0 ? (
          <p className="state" aria-busy="true">
            Caricamento…
          </p>
        ) : anomalies.length === 0 ? (
          <p className="state state--empty">Nessuna anomalia negli ultimi 31 giorni.</p>
        ) : (
          <ul className="anomaly-list">
            {anomalies.map((anomaly) => (
              <li className="anomaly" key={anomaly.transaction_id}>
                <div className="anomaly__head">
                  <span className="anomaly__merchant">{anomaly.merchant}</span>
                  <span className="anomaly__amount">{formatAmount(anomaly.amount)}</span>
                </div>
                <p className="anomaly__meta">
                  {formatDate(anomaly.date)} · {categoryText(anomaly.category)}
                </p>
                <p className="anomaly__sentence">{anomaly.sentence}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
