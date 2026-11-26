// The operations waiting to be sent, kept as a list in which each thing a person decided
// appears once. Pure: no storage, no network.
import type { Operation } from "./types";

interface Split {
  category: string;
  amount: string;
}

/** What an operation decides, so that deciding it twice leaves one operation. */
function decides(op: Operation): string {
  switch (op.kind) {
    case "category":
    case "splits":
      return `categoria:${op.transaction_id}`;
    case "note":
      return `nota:${op.transaction_id}`;
    case "tag_add":
    case "tag_remove":
      return `tag:${op.transaction_id}:${String(op.value.tag)}`;
    case "delete":
      return `cancella:${op.transaction_id}`;
    case "pair":
    case "review": {
      const [low, high] = [op.transaction_id, Number(op.value.other_id)].sort((a, b) => a - b);
      return `${op.kind}:${low}-${high}`;
    }
  }
}

/** Does the operation reach this movement, by either of its legs? */
function reaches(op: Operation, transactionId: number): boolean {
  return op.transaction_id === transactionId || Number(op.value.other_id) === transactionId;
}

function canonical(splits: Split[]): string {
  return JSON.stringify(
    splits.map((split) => [split.category, Math.round(Number(split.amount) * 100)]).sort(),
  );
}

/** An operation that asks for what the copy already held changes nothing. */
function changesNothing(op: Operation): boolean {
  if (op.kind === "category") {
    const held = op.base.splits as Split[];
    return held.length === 1 && held[0].category === op.value.category;
  }
  if (op.kind === "splits") {
    return canonical(op.base.splits as Split[]) === canonical(op.value.splits as Split[]);
  }
  if (op.kind === "note") {
    const text = (value: unknown) => String(value ?? "").trim();
    return text(op.base.notes) === text(op.value.notes);
  }
  return false;
}

/**
 * Add an operation. A second decision about the same thing replaces the first one
 * but keeps the first one's base — the copy's value, which is what the server must
 * compare with, not what was typed in between — and a decision that brings a value
 * back to the copy's own leaves nothing to send. A deletion takes with it every
 * other operation on that movement, and a deleted movement takes no more.
 */
export function enqueue(queue: Operation[], next: Operation): Operation[] {
  if (next.kind === "delete") {
    const others = queue.filter((op) => !reaches(op, next.transaction_id));
    return [...others, next];
  }
  if (queue.some((op) => op.kind === "delete" && op.transaction_id === next.transaction_id)) {
    return queue;
  }
  const key = decides(next);
  const index = queue.findIndex((op) => decides(op) === key);
  if (index === -1) return changesNothing(next) ? queue : [...queue, next];

  const merged: Operation = { ...next, id: queue[index].id, base: queue[index].base };
  const without = queue.filter((_, position) => position !== index);
  if (changesNothing(merged)) return without;
  return [...without.slice(0, index), merged, ...without.slice(index)];
}

export function discard(queue: Operation[], ids: string[]): Operation[] {
  const gone = new Set(ids);
  return queue.filter((op) => !gone.has(op.id));
}

export function newOperationId(): string {
  // `randomUUID` exists only in a secure context; the fallback is enough for an id that
  // has to be unique among the few operations of one phone.
  const crypto = globalThis.crypto as Crypto | undefined;
  if (crypto?.randomUUID) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
