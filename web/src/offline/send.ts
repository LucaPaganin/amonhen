// The send: what goes to the server and what comes back, nothing decided here.
import { ApiError } from "../apiError";
import type { Operation, Outcome, Resolution } from "./types";
import { OPERATION_FORMAT } from "./types";

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (response.ok) return (await response.json()) as T;
  let detail = `errore ${response.status}`;
  try {
    const parsed = (await response.json()) as { detail?: unknown };
    if (typeof parsed.detail === "string") detail = parsed.detail;
  } catch {
    // Not JSON: the status says it.
  }
  throw new ApiError(response.status, detail);
}

const payload = (operations: Operation[], resolutions: Resolution[]) => ({
  format: OPERATION_FORMAT,
  operations: operations.map(({ id, kind, transaction_id, value, base }) => ({
    id,
    kind,
    transaction_id,
    value,
    base,
  })),
  resolutions,
});

export interface Reply {
  outcomes: Outcome[];
}

/** What would happen: the server applies it and takes it back. */
export const previewSend = (operations: Operation[]): Promise<Reply> =>
  post<Reply>("/offline/preview", payload(operations, []));

/** Do it, with the answer given to each conflict. */
export const commitSend = (operations: Operation[], resolutions: Resolution[]): Promise<Reply> =>
  post<Reply>("/offline/commit", payload(operations, resolutions));
