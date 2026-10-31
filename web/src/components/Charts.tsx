/**
 * The two dashboard charts.
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
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatAmount, formatDate, formatMonth, toAmount } from "../format";
import type { MonthlyFlow, NetWorthPoint } from "../types";

/* Nessuna griglia e nessuna linea d'asse: restano le etichette, e i numeri
   esatti li porta il tooltip. */
const AXIS = {
  tick: { fill: "var(--muted)", fontSize: 12 },
  axisLine: false,
  tickLine: false,
} as const;

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
