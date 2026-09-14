/**
 * The three dashboard charts.
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
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatAmount, formatDate, formatMonth, toAmount } from "../format";
import type { CategorySpend, MonthlyFlow, NetWorthPoint } from "../types";
import { categoryText } from "../category";

const PALETTE = [
  "#d2a13f",
  "#6fa8dc",
  "#c98b6b",
  "#7fc8a9",
  "#d98ca8",
  "#b3c46a",
  "#a99bf0",
  "#8fa3b8",
];

const AXIS = {
  tick: { fill: "var(--muted)", fontSize: 12 },
  axisLine: { stroke: "var(--border)" },
  tickLine: false,
} as const;

const GRID = { stroke: "var(--border)", vertical: false } as const;

const TOOLTIP = {
  background: "var(--surface-raised)",
  border: "1px solid var(--border-strong)",
  borderRadius: "3px",
  color: "var(--text)",
  fontSize: "13px",
} as const;

const CURSOR = { fill: "rgba(236, 235, 230, 0.06)" } as const;

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
  const data = categories.map((item, index) => ({
    name: categoryText(item.category),
    value: toAmount(item.amount),
    color: PALETTE[index % PALETTE.length],
  }));

  return (
    <div className="chart chart--pie">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius="58%"
            outerRadius="86%"
            paddingAngle={2}
            stroke="none"
            isAnimationActive={false}
          >
            {data.map((slice) => (
              <Cell key={slice.name} fill={slice.color} />
            ))}
          </Pie>
          <Tooltip contentStyle={TOOLTIP} itemStyle={{ color: "var(--text)" }} formatter={money} />
        </PieChart>
      </ResponsiveContainer>
      <div className="chart__center" aria-hidden="true">
        <span className="chart__center-label">Speso</span>
        <span className="chart__center-value">{formatAmount(total)}</span>
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
              style={{ background: PALETTE[index % PALETTE.length] }}
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
          <CartesianGrid {...GRID} />
          <XAxis dataKey="label" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={compact} width={52} />
          <Tooltip
            contentStyle={TOOLTIP}
            itemStyle={{ color: "var(--text)" }}
            cursor={CURSOR}
            formatter={money}
            labelFormatter={(_label, payload) => labelFrom(payload, "month")}
          />
          <Bar dataKey="Entrate" fill="var(--in)" radius={[2, 2, 0, 0]} isAnimationActive={false}>
            {data.map((row) => (
              // The month still running is dimmed: it is short, not cheap.
              <Cell key={row.month} fillOpacity={row.partial ? 0.45 : 1} />
            ))}
          </Bar>
          <Bar dataKey="Uscite" fill="var(--out)" radius={[2, 2, 0, 0]} isAnimationActive={false}>
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
    Totale: toAmount(point.total),
  }));

  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="networth-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="label" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={compact} width={52} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={TOOLTIP}
            itemStyle={{ color: "var(--text)" }}
            cursor={{ stroke: "var(--border)" }}
            formatter={money}
            labelFormatter={(_label, payload) => labelFrom(payload, "date")}
          />
          <Area
            type="monotone"
            dataKey="Totale"
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
