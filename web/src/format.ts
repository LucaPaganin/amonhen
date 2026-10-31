const currency = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
const shortDate = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short" });
const longDate = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", year: "numeric" });
const monthName = new Intl.DateTimeFormat("it-IT", { month: "long", year: "numeric" });

export function toAmount(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatAmount(value: string | number): string {
  return currency.format(typeof value === "number" ? value : toAmount(value));
}

/** A day of this year is a day and a month; any other says its year too. */
export function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return (date.getFullYear() === new Date().getFullYear() ? shortDate : longDate).format(date);
}

/** A day that may lie in another year, such as where an account's history starts. */
export function formatDateWithYear(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  return Number.isNaN(date.getTime()) ? iso : longDate.format(date);
}

export function formatMonth(month: string): string {
  const date = new Date(`${month}-01T00:00:00`);
  return Number.isNaN(date.getTime()) ? month : monthName.format(date);
}

export function formatMonths(value: string | number): string {
  const parsed = typeof value === "number" ? value : Number.parseFloat(value);
  if (!Number.isFinite(parsed)) return "";
  const formatted = parsed.toLocaleString("it-IT", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  return `${formatted} mesi`;
}

export function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function shiftMonth(month: string, delta: number): string {
  const [year, monthNumber] = month.split("-").map(Number);
  const date = new Date(year, monthNumber - 1 + delta, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

export function monthBounds(month: string): { from: string; to: string } {
  const [year, monthNumber] = month.split("-").map(Number);
  const lastDay = new Date(year, monthNumber, 0).getDate();
  return { from: `${month}-01`, to: `${month}-${String(lastDay).padStart(2, "0")}` };
}
