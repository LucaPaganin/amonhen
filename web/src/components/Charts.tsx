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

const AXIS = {
  tick: { fill: "var(--muted)", fontSize: 12 },
  axisLine: { stroke: "var(--hairline)" },
  tickLine: false,
} as const;

const GRID = { stroke: "rgba(255, 255, 255, 0.06)", vertical: false } as const;

const TOOLTIP = {
  background: "rgba(28, 30, 50, 0.94)",
  border: "1px solid var(--hairline)",
  borderRadius: "18px",
  boxShadow: "0 18px 40px -18px rgba(3, 5, 14, 0.9)",
  color: "var(--text)",
  fontSize: "13px",
} as const;

const CURSOR = { fill: "rgba(244, 245, 249, 0.06)" } as const;

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
  const data = categories.map((item) => ({
    name: categoryText(item.category),
    value: toAmount(item.amount),
  }));

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
            innerRadius="58%"
            outerRadius="86%"
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
    Totale: toAmount(point.total),
  }));

  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="networth-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.45} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="label" {...AXIS} />
          <YAxis {...AXIS} tickFormatter={compact} width={52} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={TOOLTIP}
            itemStyle={{ color: "var(--text)" }}
            cursor={{ stroke: "var(--hairline)" }}
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
