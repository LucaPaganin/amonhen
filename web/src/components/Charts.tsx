/**
 * The dashboard charts, and the ones of Statistiche.
 *
 * Every series arrives already summed by the API: these components only turn
 * strings into numbers and pick colours, so a chart can never disagree with the
 * numbers printed beside it.
 */
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { categoryText } from "../category";
import { formatAmount, formatDate, formatMonth, toAmount } from "../format";
import type {
  CategorySpend,
  CategoryStatistics,
  MonthlyFlow,
  NetWorthPoint,
  SeriesStatistics,
} from "../types";

/* Nessuna griglia e nessuna linea d'asse: restano le etichette, e i numeri
   esatti li porta il tooltip. */
const AXIS = {
  tick: { fill: "var(--muted)", fontSize: 12 },
  axisLine: false,
  tickLine: false,
} as const;

/** Every slice is a gradient of its own colour, from the light end to the deep
    one: a flat disc of eight saturated hues is the look this app does not have. */
const SLICES: Array<[string, string]> = [
  ["#f6d894", "#d99f36"],
  ["#a8cff7", "#5f8fd0"],
  ["#f6bda4", "#d0744f"],
  ["#96e8c6", "#49b98b"],
  ["#f6b6cd", "#cf6f95"],
  ["#dcea94", "#9aae42"],
  ["#d0c5ff", "#8d76e6"],
  ["#b9c6d6", "#7a8da3"],
];

const TOOLTIP = {
  background: "rgba(30, 32, 54, 0.95)",
  border: "none",
  borderRadius: "20px",
  boxShadow: "0 18px 40px -18px rgba(3, 5, 14, 0.9)",
  color: "var(--text)",
  fontSize: "13px",
} as const;

const CURSOR = { fill: "rgba(255, 255, 255, 0.05)" } as const;

function money(value: unknown): string {
  return formatAmount(Number(value ?? 0));
}

/** Axis numbers stay short on a phone; the tooltip carries the exact amount. */
function compact(value: number): string {
  if (Math.abs(value) >= 1000) {
    const thousands = (value / 1000).toLocaleString("it-IT", { maximumFractionDigits: 1 });
    return `${thousands}k€`;
  }
  return `${value.toLocaleString("it-IT", { maximumFractionDigits: 0 })}€`;
}

function shortMonth(month: string): string {
  const date = new Date(`${month}-01T00:00:00`);
  return Number.isNaN(date.getTime()) ? month : date.toLocaleDateString("it-IT", { month: "short" });
}

function labelFrom(payload: unknown, key: string): string {
  const rows = payload as Array<{ payload?: Record<string, string> }> | undefined;
  const value = rows?.[0]?.payload?.[key];
  return value ? (key === "month" ? formatMonth(value) : formatDate(value)) : "";
}

interface SpendingPieProps {
  categories: CategorySpend[];
  total: string;
}

export function SpendingPie({ categories, total }: SpendingPieProps) {
  // A category whose refunds beat its spending has no slice to draw: it stays in
  // the legend, and sorted last it shifts nobody's colour.
  const data = categories
    .map((item) => ({ name: categoryText(item.category), value: toAmount(item.amount) }))
    .filter((slice) => slice.value > 0);
  // The currency symbol is one character the figure does not need at full size:
  // it is drawn smaller, which is room the digits get to use. Intl separates it
  // with a non-breaking space, and ICU uses the narrow one just as often.
  const written = formatAmount(total);
  const parts = written.match(/^(.*?)[\s\u00a0\u202f]+(\S+)$/);
  const amount = parts ? parts[1] : written;
  const symbol = parts ? parts[2] : "";

  return (
    <div className="chart chart--pie">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <defs>
            {data.map((_slice, index) => {
              const [light, deep] = SLICES[index % SLICES.length];
              return (
                <linearGradient
                  id={`slice-${index}`}
                  key={`slice-${index}`}
                  x1="0"
                  y1="0"
                  x2="1"
                  y2="1"
                >
                  <stop offset="0%" stopColor={light} />
                  <stop offset="100%" stopColor={deep} />
                </linearGradient>
              );
            })}
          </defs>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius="68%"
            outerRadius="88%"
            paddingAngle={3}
            cornerRadius={6}
            stroke="none"
            isAnimationActive={false}
          >
            {data.map((slice, index) => (
              <Cell key={slice.name} fill={`url(#slice-${index % SLICES.length})`} />
            ))}
          </Pie>
          <Tooltip contentStyle={TOOLTIP} itemStyle={{ color: "var(--text)" }} formatter={money} />
        </PieChart>
      </ResponsiveContainer>
      <div className="chart__center" aria-hidden="true">
        <span className="chart__center-label">Speso</span>
        <span className="chart__center-value">
          {amount}
          {symbol !== "" ? <span className="chart__center-symbol"> {symbol}</span> : null}
        </span>
      </div>
    </div>
  );
}

export function SpendingLegend({ categories, total }: SpendingPieProps) {
  const whole = toAmount(total);
  return (
    <ul className="chart-legend">
      {categories.map((item, index) => {
        const share = whole > 0 ? Math.round((toAmount(item.amount) / whole) * 100) : 0;
        return (
          <li className="chart-legend__row" key={item.category}>
            <span
              className="chart-legend__swatch"
              style={{
                background: `linear-gradient(135deg, ${SLICES[index % SLICES.length][0]}, ${SLICES[index % SLICES.length][1]})`,
              }}
              aria-hidden="true"
            />
            <span className="chart-legend__name">{categoryText(item.category)}</span>
            <span className="chart-legend__share">{share}%</span>
            <span className="chart-legend__value">{formatAmount(item.amount)}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function FlowsChart({ months }: { months: MonthlyFlow[] }) {
  const data = months.map((flow) => ({
    month: flow.month,
    label: shortMonth(flow.month),
    Entrate: toAmount(flow.income),
    Uscite: toAmount(flow.expenses),
    partial: flow.partial,
  }));

  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} barGap={2} margin={{ top: 8, right: 4, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="bar-in" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--in-light)" />
              <stop offset="100%" stopColor="var(--in-deep)" />
            </linearGradient>
            <linearGradient id="bar-out" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--out-light)" />
              <stop offset="100%" stopColor="var(--out-deep)" />
            </linearGradient>
          </defs>
          <XAxis dataKey="label" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={compact} width={52} />
          <Tooltip
            contentStyle={TOOLTIP}
            itemStyle={{ color: "var(--text)" }}
            cursor={CURSOR}
            formatter={money}
            labelFormatter={(_label, payload) => labelFrom(payload, "month")}
          />
          <Bar dataKey="Entrate" fill="url(#bar-in)" radius={[7, 7, 0, 0]} isAnimationActive={false}>
            {data.map((row) => (
              // The month still running is dimmed: it is short, not cheap.
              <Cell key={row.month} fillOpacity={row.partial ? 0.45 : 1} />
            ))}
          </Bar>
          <Bar dataKey="Uscite" fill="url(#bar-out)" radius={[7, 7, 0, 0]} isAnimationActive={false}>
            {data.map((row) => (
              <Cell key={row.month} fillOpacity={row.partial ? 0.45 : 1} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function NetWorthChart({ points }: { points: NetWorthPoint[] }) {
  const data = points.map((point) => ({
    date: point.date,
    label: formatDate(point.date),
    Liquidità: toAmount(point.total),
  }));

  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="networth-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.45} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="label" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={compact} width={64} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={TOOLTIP}
            itemStyle={{ color: "var(--text)" }}
            cursor={{ stroke: "var(--fill-3)" }}
            formatter={money}
            labelFormatter={(_label, payload) => labelFrom(payload, "date")}
          />
          <Area
            type="monotone"
            dataKey="Liquidità"
            stroke="var(--accent)"
            strokeWidth={2}
            fill="url(#networth-fill)"
            dot={{ r: 3, fill: "var(--accent)", strokeWidth: 0 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** The gradient of one of the eight slice colours, for a chart's `<defs>`. */
function sliceGradient(id: string, index: number, vertical = true) {
  const [light, deep] = SLICES[index % SLICES.length];
  return (
    <linearGradient
      id={id}
      key={id}
      x1="0"
      y1="0"
      x2={vertical ? "0" : "1"}
      y2={vertical ? "1" : "0"}
    >
      <stop offset="0%" stopColor={light} />
      <stop offset="100%" stopColor={deep} />
    </linearGradient>
  );
}

/** The month's total, against the median and the mean of the window. */
export function StatisticsTotalChart({
  months,
  total,
}: {
  months: string[];
  total: SeriesStatistics;
}) {
  const data = months.map((month, index) => ({
    month,
    label: shortMonth(month),
    Speso: toAmount(total.series[index]),
  }));
  const median = toAmount(total.median);
  const mean = toAmount(total.mean);
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 4, left: -10, bottom: 0 }}>
          <defs>{sliceGradient("stat-total", 0)}</defs>
          <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" />
          <YAxis {...AXIS} tickFormatter={compact} width={52} />
          <Tooltip
            contentStyle={TOOLTIP}
            itemStyle={{ color: "var(--text)" }}
            cursor={CURSOR}
            formatter={money}
            labelFormatter={(_label, payload) => labelFrom(payload, "month")}
          />
          <Bar dataKey="Speso" radius={[7, 7, 0, 0]} isAnimationActive={false}>
            {data.map((row) => (
              // Above the median is a month that took more than usual.
              <Cell
                key={row.month}
                fill="url(#stat-total)"
                fillOpacity={row.Speso > median ? 1 : 0.55}
              />
            ))}
          </Bar>
          <ReferenceLine y={median} stroke="var(--text)" strokeDasharray="5 4" strokeWidth={1.5} />
          <ReferenceLine y={mean} stroke="var(--muted)" strokeDasharray="2 4" strokeWidth={1.5} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** How many categories get a colour of their own; the others share one grey. */
const COMPOSITION_COLOURED = 5;
const OTHERS_FILL = "#5b6378";

interface CompositionTooltipProps {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; payload?: { month?: string } }>;
}

function CompositionTooltip({ active, payload }: CompositionTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const rows = payload
    .filter((row) => (row.value ?? 0) !== 0)
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  const month = payload[0]?.payload?.month;
  return (
    <div className="chart-tooltip" style={TOOLTIP}>
      <p className="chart-tooltip__title">{month ? formatMonth(month) : ""}</p>
      {rows.slice(0, 8).map((row) => (
        <p className="chart-tooltip__row" key={row.name}>
          <span>{row.name}</span>
          <span>{money(row.value)}</span>
        </p>
      ))}
      {rows.length > 8 ? (
        <p className="chart-tooltip__more">e altre {rows.length - 8}</p>
      ) : null}
    </div>
  );
}

/** Each month stacked by category: the largest ones in colour, the rest in grey. */
export function CompositionChart({
  months,
  categories,
}: {
  months: string[];
  categories: CategoryStatistics[];
}) {
  const data = months.map((month, index) => {
    const row: Record<string, string | number> = { month, label: shortMonth(month) };
    for (const item of categories) row[categoryText(item.category)] = toAmount(item.series[index]);
    return row;
  });
  const coloured = categories.slice(0, COMPOSITION_COLOURED);
  const others = categories.slice(COMPOSITION_COLOURED);
  return (
    <div className="chart chart--tall">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 4, left: -10, bottom: 0 }}>
          <defs>{coloured.map((_item, index) => sliceGradient(`stat-stack-${index}`, index))}</defs>
          <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" />
          <YAxis {...AXIS} tickFormatter={compact} width={52} />
          <Tooltip cursor={CURSOR} content={<CompositionTooltip />} />
          {/* The grey ones at the foot of the stack, the coloured ones on top,
              where the eye reads them. */}
          {others.map((item) => (
            <Bar
              key={item.category}
              dataKey={categoryText(item.category)}
              stackId="month"
              fill={OTHERS_FILL}
              isAnimationActive={false}
            />
          ))}
          {coloured
            .map((item, index) => ({ item, index }))
            .reverse()
            .map(({ item, index }) => (
              <Bar
                key={item.category}
                dataKey={categoryText(item.category)}
                stackId="month"
                fill={`url(#stat-stack-${index})`}
                isAnimationActive={false}
              />
            ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** The legend of the composition: the coloured categories, then the grey. */
export function CompositionLegend({ categories }: { categories: CategoryStatistics[] }) {
  const coloured = categories.slice(0, COMPOSITION_COLOURED);
  const others = categories.length - coloured.length;
  return (
    <ul className="chart-legend chart-legend--inline">
      {coloured.map((item, index) => (
        <li className="chart-legend__row" key={item.category}>
          <span
            className="chart-legend__swatch"
            style={{ background: `linear-gradient(135deg, ${SLICES[index][0]}, ${SLICES[index][1]})` }}
            aria-hidden="true"
          />
          <span className="chart-legend__name">{categoryText(item.category)}</span>
        </li>
      ))}
      {others > 0 ? (
        <li className="chart-legend__row">
          <span className="chart-legend__swatch" style={{ background: OTHERS_FILL }} aria-hidden="true" />
          <span className="chart-legend__name">
            {others === 1 ? "Un'altra categoria" : `Altre ${others} categorie`}
          </span>
        </li>
      ) : null}
    </ul>
  );
}

/** How many categories the median-and-mean comparison draws. */
const COMPARED_CATEGORIES = 10;

/** A category's median month against its mean: far apart, it spends now and then. */
export function MedianMeanChart({ categories }: { categories: CategoryStatistics[] }) {
  const data = categories.slice(0, COMPARED_CATEGORIES).map((item) => ({
    name: categoryText(item.category),
    Mediana: toAmount(item.median),
    Media: toAmount(item.mean),
  }));
  return (
    <div className="chart" style={{ height: `${Math.max(data.length * 46, 120)}px` }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          barGap={2}
          margin={{ top: 0, right: 8, left: 0, bottom: 0 }}
        >
          <defs>
            {sliceGradient("stat-median", 0, false)}
            {sliceGradient("stat-mean", 6, false)}
          </defs>
          <XAxis type="number" {...AXIS} tickFormatter={compact} />
          <YAxis type="category" dataKey="name" {...AXIS} width={104} />
          <Tooltip
            contentStyle={TOOLTIP}
            itemStyle={{ color: "var(--text)" }}
            cursor={CURSOR}
            formatter={money}
          />
          <Bar
            dataKey="Mediana"
            fill="url(#stat-median)"
            radius={[0, 6, 6, 0]}
            barSize={12}
            isAnimationActive={false}
          />
          <Bar
            dataKey="Media"
            fill="url(#stat-mean)"
            radius={[0, 6, 6, 0]}
            barSize={12}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
