import { useCallback, useEffect, useState } from "react";

import { api, errorMessage, isAbortError } from "../api";
import { categoryText } from "../category";
import {
  CompositionChart,
  CompositionLegend,
  MedianMeanChart,
  StatisticsTotalChart,
} from "../components/Charts";
import { Help } from "../components/Help";
import { formatAmount, formatMonth, toAmount } from "../format";
import type { CategoryStatistics, SeriesStatistics, Statistics } from "../types";

/** The windows on offer, in complete months. */
const WINDOWS = [6, 12, 24];
const DEFAULT_WINDOW = 12;

interface StatisticsScreenProps {
  /** Bumped after a sync: the months are read again. */
  refreshToken: number;
  onOpenCategory: (category: string) => void;
}

/** One line per month, with a bar as long as the month against the largest one. */
function MonthBars({ months, statistics }: { months: string[]; statistics: SeriesStatistics }) {
  const largest = Math.max(...statistics.series.map(toAmount));
  return (
    <ul className="stat-months">
      {months.map((month, index) => {
        const value = statistics.series[index];
        const share = largest > 0 ? Math.max(toAmount(value), 0) / largest : 0;
        return (
          <li className="stat-month" key={month}>
            <span className="stat-month__name">{formatMonth(month)}</span>
            <span className="stat-month__amount">{formatAmount(value)}</span>
            <span className="stat-month__track" aria-hidden="true">
              <span className="stat-month__bar" style={{ width: `${share * 100}%` }} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** How many categories the heat map lists, the largest mean first. */
const HEATMAP_CATEGORIES = 12;

/**
 * A row per category and a cell per month, as dark as that month against the
 * category's own largest: a category that spends in a season shows where, and
 * one that never stops shows an even row. The server sent every amount.
 */
function Heatmap({ months, categories }: { months: string[]; categories: CategoryStatistics[] }) {
  const rows = categories.slice(0, HEATMAP_CATEGORIES);
  return (
    <div className="heatmap" style={{ ["--heatmap-months" as string]: months.length }}>
      <span className="heatmap__corner" aria-hidden="true" />
      {months.map((month, index) => (
        <span className="heatmap__month" key={month} aria-hidden="true">
          {index % 3 === 0 ? formatMonth(month).slice(0, 3) : ""}
        </span>
      ))}
      {rows.map((item) => {
        const largest = Math.max(...item.series.map(toAmount), 0);
        return [
          <span className="heatmap__name" key={`${item.category}-name`}>
            {categoryText(item.category)}
          </span>,
          ...months.map((month, index) => {
            const value = item.series[index];
            const share = largest > 0 ? Math.max(toAmount(value), 0) / largest : 0;
            return (
              <span
                key={`${item.category}-${month}`}
                className="heatmap__cell"
                style={{ ["--heat" as string]: share }}
                title={`${categoryText(item.category)}, ${formatMonth(month)}: ${formatAmount(value)}`}
              />
            );
          }),
        ];
      })}
    </div>
  );
}

function CategoryRow({
  item,
  months,
  open,
  onToggle,
  onOpenCategory,
}: {
  item: CategoryStatistics;
  months: string[];
  open: boolean;
  onToggle: () => void;
  onOpenCategory: (category: string) => void;
}) {
  return (
    <li>
      <button type="button" className="where__row" aria-expanded={open} onClick={onToggle}>
        <span className="where__text">
          <span className="where__name">{categoryText(item.category)}</span>
          <span className="where__distance">
            In {item.active_months} {item.active_months === 1 ? "mese" : "mesi"} su {months.length} · da{" "}
            {formatAmount(item.min)} a{" "}
            {formatAmount(item.max)}
          </span>
        </span>
        <span className="stat-figures">
          <span className="where__spent">{formatAmount(item.median)}</span>
          <span className="stat-figures__mean">media {formatAmount(item.mean)}</span>
        </span>
      </button>
      {open ? (
        <div className="stat-detail">
          <MonthBars months={months} statistics={item} />
          <button
            type="button"
            className="button button--block"
            onClick={() => onOpenCategory(item.category)}
          >
            Apri i movimenti
          </button>
        </div>
      ) : null}
    </li>
  );
}

/** Desiderata 5.15: what each category usually takes. The server does every sum. */
export function StatisticsScreen({ refreshToken, onOpenCategory }: StatisticsScreenProps) {
  const [months, setMonths] = useState(DEFAULT_WINDOW);
  const [statistics, setStatistics] = useState<Statistics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opened, setOpened] = useState<string | null>(null);

  const load = useCallback(async (window: number, signal?: AbortSignal) => {
    setError(null);
    try {
      setStatistics(await api.statistics(window, signal));
    } catch (caught) {
      if (!isAbortError(caught)) setError(errorMessage(caught));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(months, controller.signal);
    return () => controller.abort();
  }, [load, months, refreshToken]);

  const shown = statistics?.months ?? [];

  return (
    <section className="screen">
      <header className="screen__header">
        <div>
          <h1 className="screen__title">Statistiche</h1>
          <p className="screen__subtitle">Quanto prende di solito ogni categoria, mese per mese.</p>
        </div>
      </header>

      <div className="filters__chips" role="group" aria-label="I mesi letti">
        {WINDOWS.map((count) => (
          <button
            key={count}
            type="button"
            className={months === count ? "chip chip--toggle chip--on" : "chip chip--toggle"}
            aria-pressed={months === count}
            onClick={() => setMonths(count)}
          >
            {count} mesi
          </button>
        ))}
      </div>

      {error !== null ? (
        <div className="state state--error" role="alert">
          <p>Impossibile caricare le statistiche: {error}</p>
          <button type="button" className="button" onClick={() => void load(months)}>
            Riprova
          </button>
        </div>
      ) : null}

      {statistics === null && error === null ? (
        <p className="state" aria-busy="true">
          Caricamento…
        </p>
      ) : null}

      {statistics !== null && statistics.total === null ? (
        <p className="state">Nessun mese completo da leggere.</p>
      ) : null}

      {statistics === null || statistics.total === null ? null : (
        <>
          <section className="panel">
            <h2 className="section-title">
              Un mese <Help topic="statistics" label="mediana e media" />
            </h2>
            <p className="headline">{formatAmount(statistics.total.median)}</p>
            <p className="chart-note">
              Mediana di {formatMonth(shown[0])} – {formatMonth(shown[shown.length - 1])}, media{" "}
              {formatAmount(statistics.total.mean)}
            </p>
            {statistics.applied.available < statistics.applied.months ? (
              <p className="chart-note">
                Il ledger arriva a {statistics.applied.available} mesi completi su{" "}
                {statistics.applied.months}.
              </p>
            ) : null}
          </section>

          <section className="panel">
            <h2 className="section-title">Mese per mese</h2>
            <StatisticsTotalChart months={shown} total={statistics.total} />
            <p className="chart-note">
              Più chiari i mesi sotto la mediana. La linea tratteggiata è la mediana, quella a
              puntini la media.
            </p>
          </section>

          {statistics.categories.length > 0 ? (
            <>
              <section className="panel">
                <h2 className="section-title">Di cosa è fatto un mese</h2>
                <CompositionChart months={shown} categories={statistics.categories} />
                <CompositionLegend categories={statistics.categories} />
              </section>

              <section className="panel">
                <h2 className="section-title">Mediana e media</h2>
                <MedianMeanChart categories={statistics.categories} />
                <p className="chart-note">
                  Quando la media supera di molto la mediana, la categoria spende a colpi: pochi
                  mesi grandi e molti piccoli.
                </p>
              </section>

              <section className="panel">
                <h2 className="section-title">Quando spende ogni categoria</h2>
                <Heatmap months={shown} categories={statistics.categories} />
                <p className="chart-note">
                  Ogni riga rispetto al suo mese più caro: più accesa la casella, più vicina a
                  quel mese. Il puntatore su una casella ne mostra l'importo.
                </p>
              </section>
            </>
          ) : null}

          <section className="panel">
            <h2 className="section-title">Per categoria</h2>
            <ul className="where">
              {statistics.categories.map((item) => (
                <CategoryRow
                  key={item.category}
                  item={item}
                  months={shown}
                  open={opened === item.category}
                  onToggle={() => setOpened(opened === item.category ? null : item.category)}
                  onOpenCategory={onOpenCategory}
                />
              ))}
            </ul>
          </section>
        </>
      )}
    </section>
  );
}
