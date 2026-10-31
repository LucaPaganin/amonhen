import { useCallback, useEffect, useMemo, useState } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { categoryText } from "../category";
import { FlowsChart, NetWorthChart } from "../components/Charts";
import { Help } from "../components/Help";
import {
  currentMonth,
  formatAmount,
  formatDate,
  formatMonths,
  shiftMonth,
  toAmount,
} from "../format";
import type { GuideTopic } from "./Guide";
import type {
  AccountRef,
  Anomaly,
  Category,
  DashboardFilters,
  Flows,
  Metrics,
  MonthReading,
  NetWorth,
} from "../types";
import { useTags } from "../useTags";
import { useWide } from "../useWide";

/** The period the charts open on. */
const DEFAULT_MONTHS = 12;
/** The periods the quick chips offer, in months. */
const PERIODS = [3, 6, 12, 24];
/** How many anomalies and categories are on screen before anyone asks for more. */
const ANOMALIES_SHOWN = 3;
const CATEGORIES_SHOWN = 6;

interface DashboardScreenProps {
  categories: Category[];
  /** Bumped after a sync: every series is read again, not redrawn as it was. */
  refreshToken: number;
  /** Opens the month's movements of a category. */
  onOpenCategory: (category: string) => void;
}

/** A figure with a sign, for the distance from the usual. */
function signed(value: number): string {
  return `${value > 0 ? "+" : ""}${formatAmount(value)}`;
}

/** The sentence under the month's figure: what it is being compared with. */
function monthComparison(reading: MonthReading): string {
  if (reading.usual === null) return "Nessun mese completo con cui confrontarlo";
  const usual = toAmount(reading.usual);
  const distance = toAmount(reading.spent) - usual;
  const pace = `di solito ${formatAmount(usual)} al giorno ${reading.day}`;
  if (Math.abs(distance) < 1) return `Come al solito: ${pace}`;
  return `${formatAmount(Math.abs(distance))} ${distance > 0 ? "in più" : "in meno"} del solito: ${pace}`;
}

export function DashboardScreen({ categories, refreshToken, onOpenCategory }: DashboardScreenProps) {
  const wide = useWide();
  const [fromMonth, setFromMonth] = useState(() => shiftMonth(currentMonth(), -(DEFAULT_MONTHS - 1)));
  const [scopedAccounts, setScopedAccounts] = useState<string[]>([]);
  const [scopedCategory, setScopedCategory] = useState("");
  const [scopedTag, setScopedTag] = useState("");
  const [accounts, setAccounts] = useState<AccountRef[]>([]);
  const [month, setMonth] = useState<MonthReading | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [flows, setFlows] = useState<Flows | null>(null);
  const [netWorth, setNetWorth] = useState<NetWorth | null>(null);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [allCategories, setAllCategories] = useState(false);
  const [allAnomalies, setAllAnomalies] = useState(false);
  const { tags } = useTags();

  const filters = useMemo<DashboardFilters>(
    () => ({
      from: fromMonth,
      to: currentMonth(),
      accounts: scopedAccounts,
      categories: scopedCategory === "" ? [] : [scopedCategory],
      tags: scopedTag === "" ? [] : [scopedTag],
    }),
    [fromMonth, scopedAccounts, scopedCategory, scopedTag],
  );

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const [reading, figures, found] = await Promise.all([
          api.month(filters, signal),
          api.metrics(filters, signal),
          api.anomalies(31, signal),
        ]);
        setMonth(reading);
        setMetrics(figures);
        setAnomalies(found);
        setLoadError(null);
      } catch (caught) {
        if (isAbortError(caught)) return;
        setLoadError(errorMessage(caught));
      }
    },
    [filters, refreshToken],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  // The charts are the PC's: a phone neither draws nor asks for them.
  useEffect(() => {
    if (!wide) return;
    const controller = new AbortController();
    Promise.all([api.flows(filters, controller.signal), api.netWorth(filters, controller.signal)])
      .then(([monthly, balances]) => {
        setFlows(monthly);
        setNetWorth(balances);
      })
      .catch((caught) => {
        if (!isAbortError(caught)) setLoadError(errorMessage(caught));
      });
    return () => controller.abort();
  }, [wide, filters, refreshToken]);

  useEffect(() => {
    const controller = new AbortController();
    api
      .accounts(controller.signal)
      .then(setAccounts)
      .catch(() => undefined);
    return () => controller.abort();
  }, [refreshToken]);

  const toggleAccount = (name: string) => {
    setScopedAccounts((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
    );
  };

  const activeFilters =
    scopedAccounts.length + (scopedCategory === "" ? 0 : 1) + (scopedTag === "" ? 0 : 1);

  const shownCategories =
    month === null
      ? []
      : allCategories
        ? month.categories
        : month.categories.slice(0, CATEGORIES_SHOWN);

  // The largest first: three lines are what a person reads.
  const biggestAnomalies = [...anomalies].sort(
    (left, right) => Math.abs(toAmount(right.amount)) - Math.abs(toAmount(left.amount)),
  );
  const shownAnomalies = allAnomalies
    ? biggestAnomalies
    : biggestAnomalies.slice(0, ANOMALIES_SHOWN);

  const details: {
    key: string;
    label: string;
    topic: GuideTopic;
    value: string | null;
    partial: boolean;
  }[] =
    metrics === null
      ? []
      : [
          {
            key: "typical",
            label: "Spesa mensile tipica",
            topic: "typical",
            value: metrics.recurring_burn,
            partial: metrics.partial,
          },
          {
            key: "expected",
            label: "Spesa mensile attesa",
            topic: "expected",
            value: metrics.expected_burn,
            partial: metrics.partial || metrics.episodic_partial,
          },
          {
            key: "reserve",
            label: "Riserva per spese rare",
            topic: "reserve",
            value: metrics.episodic_accrual,
            partial: metrics.episodic_partial,
          },
          {
            key: "essential",
            label: "Spesa irrinunciabile",
            topic: "essential",
            value: metrics.essential_monthly,
            partial: false,
          },
          {
            key: "cuttable",
            label: "Spesa tagliabile",
            topic: "essential",
            value: metrics.discretionary_monthly,
            partial: false,
          },
        ];

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Dashboard</h1>
        </div>
        <div className="screen__actions">
          <button
            type="button"
            className="button"
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen(!filtersOpen)}
          >
            {activeFilters === 0 ? "Filtri" : `Filtri · ${activeFilters}`}
          </button>
        </div>
      </header>

      {filtersOpen ? (
        <section className="panel">
          <div className="filters">
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
            {tags.length === 0 ? null : (
              <div className="field">
                <label htmlFor="filter-tag">Tag</label>
                <select
                  id="filter-tag"
                  value={scopedTag}
                  onChange={(event) => setScopedTag(event.target.value)}
                >
                  <option value="">Tutti i tag</option>
                  {tags.map((tag) => (
                    <option key={tag.id} value={tag.name}>
                      {tag.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </section>
      ) : null}

      {loadError ? (
        <div className="state state--error" role="alert">
          <p>{loadError}</p>
          <button type="button" className="button" onClick={() => void load()}>
            Riprova
          </button>
        </div>
      ) : null}

      {month === null && loadError === null ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : null}

      {month === null ? null : (
        <section className="panel">
          <h2 className="section-title">Questo mese</h2>
          <p className="headline">{formatAmount(month.spent)}</p>
          <p className="chart-note">{monthComparison(month)}</p>
          {toAmount(month.rare) === 0 ? null : (
            <p className="chart-note">
              Più {formatAmount(month.rare)} di spese rare <Help topic="rare" label="spesa rara" />
            </p>
          )}
        </section>
      )}

      {month === null || month.categories.length === 0 ? null : (
        <section className="panel">
          <h2 className="section-title">Dove sono finiti</h2>
          <ul className="where">
            {shownCategories.map((item) => {
              const distance = toAmount(item.spent) - toAmount(item.usual);
              return (
                <li key={item.category}>
                  <button
                    type="button"
                    className="where__row"
                    onClick={() => onOpenCategory(item.category)}
                  >
                    <span className="where__name">{categoryText(item.category)}</span>
                    <span
                      className={
                        distance > 0 ? "where__distance where__distance--over" : "where__distance"
                      }
                    >
                      {Math.abs(distance) < 1 ? "come al solito" : signed(distance)}
                    </span>
                    <span className="where__spent">{formatAmount(item.spent)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          {month.categories.length > CATEGORIES_SHOWN ? (
            <button
              type="button"
              className="button button--block"
              onClick={() => setAllCategories(!allCategories)}
            >
              {allCategories ? "Meno" : `Tutte (${month.categories.length})`}
            </button>
          ) : null}
        </section>
      )}

      {metrics === null ? null : (
        <ul className="metrics metrics--pair">
          <li className="metric">
            <h2 className="metric__label">
              Liquidità <Help topic="liquidity" label="liquidità" />
            </h2>
            <span className="metric__value">
              {metrics.liquidity === null ? "non disponibile" : formatAmount(metrics.liquidity)}
            </span>
          </li>
          <li className="metric">
            <h2 className="metric__label">
              Mesi di autonomia <Help topic="runway" label="mesi di autonomia" />
            </h2>
            <span className="metric__value">
              {metrics.runway_months === null ? "non calcolabile" : formatMonths(metrics.runway_months)}
            </span>
          </li>
        </ul>
      )}

      {anomalies.length === 0 ? null : (
        <section className="panel">
          <h2 className="section-title">
            Anomalie <Help topic="anomaly" label="anomalia" />
          </h2>
          <ul className="anomaly-list">
            {shownAnomalies.map((anomaly) => (
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
          {anomalies.length > ANOMALIES_SHOWN ? (
            <button
              type="button"
              className="button button--block"
              onClick={() => setAllAnomalies(!allAnomalies)}
            >
              {allAnomalies ? "Meno" : `Tutte (${anomalies.length})`}
            </button>
          ) : null}
        </section>
      )}

      {wide ? (
        <>
          <div className="filters__chips" role="group" aria-label="Il periodo dei grafici">
            {PERIODS.map((months) => {
              const on = fromMonth === shiftMonth(currentMonth(), -(months - 1));
              return (
                <button
                  key={months}
                  type="button"
                  className={on ? "chip chip--toggle chip--on" : "chip chip--toggle"}
                  aria-pressed={on}
                  onClick={() => setFromMonth(shiftMonth(currentMonth(), -(months - 1)))}
                >
                  {months} mesi
                </button>
              );
            })}
          </div>

          <section className="panel panel--pair">
            <h2 className="section-title">Entrate e uscite</h2>
            {flows === null ? (
              <p className="state" aria-busy="true">
                Caricamento…
              </p>
            ) : (
              <FlowsChart months={flows.months} />
            )}
          </section>

          <section className="panel panel--pair">
            <h2 className="section-title">Liquidità nel tempo</h2>
            {netWorth === null ? (
              <p className="state" aria-busy="true">
                Caricamento…
              </p>
            ) : netWorth.points.length < 2 ? (
              <p className="state">La curva compare dalla seconda rilevazione.</p>
            ) : (
              <NetWorthChart points={netWorth.points} />
            )}
          </section>
        </>
      ) : null}

      {metrics === null ? null : (
        <details className="metric-help">
          <summary>Dettagli</summary>
          <ul className="metrics">
            {details.map((item) => (
              <li className="metric" key={item.key}>
                <h2 className="metric__label">
                  {item.label} <Help topic={item.topic} label={item.label} />
                </h2>
                <span className="metric__value">
                  {item.value === null ? "non disponibile" : formatAmount(item.value)}
                </span>
                {item.partial ? (
                  <p className="metric__warning" role="note">
                    storico parziale: {metrics.months_of_history} mesi
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
