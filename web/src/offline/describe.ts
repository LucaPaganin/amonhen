// What an operation says to the person who made it, in their own words: pure text.
import { formatAmount, formatDate } from "../format";
import type { Bundle, Operation } from "./types";

function movement(bundle: Bundle | null, id: number): string {
  const found = bundle?.transactions.find((item) => item.id === id);
  if (!found) return `movimento ${id}`;
  return `${formatDate(found.date)} · ${found.description} · ${formatAmount(found.amount)}`;
}

/** The movement an operation is about, one line. */
export function subject(bundle: Bundle | null, operation: Operation): string {
  return movement(bundle, operation.transaction_id);
}

export function action(bundle: Bundle | null, operation: Operation): string {
  const { value } = operation;
  switch (operation.kind) {
    case "category":
      return `Categoria: ${String(value.category)}`;
    case "splits": {
      const splits = value.splits as { category: string }[];
      return splits.length === 1 ? `Categoria: ${splits[0].category}` : `Divisione in ${splits.length} categorie`;
    }
    case "tag_add":
      return `Tag aggiunto: ${String(value.tag)}`;
    case "tag_remove":
      return `Tag tolto: ${String(value.tag)}`;
    case "note":
      return String(value.notes ?? "").trim() === "" ? "Nota tolta" : "Nota riscritta";
    case "delete":
      return "Cancellato";
    case "pair":
      return `Giroconto con ${movement(bundle, Number(value.other_id))}`;
    case "review":
      return value.decision === "confirm"
        ? `Giroconto proposto confermato con ${movement(bundle, Number(value.other_id))}`
        : `Giroconto proposto rifiutato con ${movement(bundle, Number(value.other_id))}`;
  }
}

/** A value from a base, from the phone's side or from the server, as text. */
export function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "(vuoto)";
  if (typeof value === "string") return value;
  const record = value as Record<string, unknown>;
  const splits = Array.isArray(value) ? value : record.splits;
  if (Array.isArray(splits)) {
    return splits
      .map((split: { category: string; amount: string }) => `${split.category} ${formatAmount(split.amount)}`)
      .join(", ");
  }
  if (typeof record.notes === "string") return show(record.notes);
  if (typeof record.category === "string") return record.category;
  if (typeof record.state === "number") {
    return { 0: "da decidere", 1: "confermato", [-1]: "rifiutato" }[record.state] ?? String(record.state);
  }
  if (typeof record.description === "string") {
    return `${formatDate(String(record.date))} · ${record.description} · ${formatAmount(String(record.amount))} · ${String(record.status)}`;
  }
  return JSON.stringify(value);
}
