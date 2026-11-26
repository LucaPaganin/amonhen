import { describe, expect, it } from "vitest";
import { discard, enqueue } from "./queue";
import type { Operation } from "./types";

const held = (category: string) => ({ splits: [{ category, amount: "10.00" }] });

function op(kind: Operation["kind"], id: number, value: Operation["value"], base: Operation["base"] = {}): Operation {
  return { id: `${kind}-${id}-${JSON.stringify(value)}`, kind, transaction_id: id, value, base, at: "" };
}

describe("enqueue", () => {
  it("keeps one operation per decision, with the first base and the last value", () => {
    let queue = enqueue([], op("category", 1, { category: "Cibo" }, held("Uncategorized")));
    queue = enqueue(queue, op("category", 1, { category: "Casa" }, held("Cibo")));
    expect(queue).toHaveLength(1);
    expect(queue[0].value).toEqual({ category: "Casa" });
    expect(queue[0].base).toEqual(held("Uncategorized"));
  });

  it("drops a decision that brings the value back to the copy's", () => {
    let queue = enqueue([], op("category", 1, { category: "Cibo" }, held("Uncategorized")));
    queue = enqueue(queue, op("category", 1, { category: "Uncategorized" }, held("Cibo")));
    expect(queue).toEqual([]);
  });

  it("ignores a note equal to the copy's", () => {
    expect(enqueue([], op("note", 1, { notes: " ciao " }, { notes: "ciao" }))).toEqual([]);
  });

  it("lets the last tag decision win", () => {
    let queue = enqueue([], op("tag_add", 1, { tag: "x" }));
    queue = enqueue(queue, op("tag_remove", 1, { tag: "x" }));
    expect(queue).toHaveLength(1);
    expect(queue[0].kind).toBe("tag_remove");
  });

  it("lets a deletion absorb the other operations on the movement, and refuse later ones", () => {
    let queue = enqueue([], op("note", 1, { notes: "a" }, { notes: "" }));
    queue = enqueue(queue, op("pair", 2, { other_id: 1 }));
    queue = enqueue(queue, op("delete", 1, {}));
    expect(queue.map((item) => item.kind)).toEqual(["delete"]);
    expect(enqueue(queue, op("category", 1, { category: "Cibo" }, held("Uncategorized")))).toBe(queue);
  });

  it("discards by id", () => {
    const queue = enqueue([], op("tag_add", 1, { tag: "x" }));
    expect(discard(queue, [queue[0].id])).toEqual([]);
  });
});
