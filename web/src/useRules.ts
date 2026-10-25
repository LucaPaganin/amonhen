import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage, isAbortError } from "./api";
import type { Rule, RuleDraft } from "./types";

export interface RulesController {
  rules: Rule[];
  loading: boolean;
  loadError: string | null;
  /** Last failed write, shown as-is: the API's `detail` is the message. */
  operationError: string | null;
  reload: () => void;
  /**
   * Upsert: with an id it changes that rule, without one the same text and
   * conditions are an edit of the rule that has them. Answers the error to
   * show where the rule was written, or null once it is saved.
   */
  add: (draft: RuleDraft) => Promise<string | null>;
  /** How many movements the rule held, or null when the call failed. */
  remove: (id: number) => Promise<number | null>;
}

/**
 * `onChanged` fires after every successful write: a rule shrinks what the
 * "Da confermare" queue still has to decide, so its counts and badge reload.
 */
export function useRules(onChanged?: () => void): RulesController {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const changed = useRef(onChanged);

  useEffect(() => {
    changed.current = onChanged;
  }, [onChanged]);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      setRules(await api.rules(signal));
      setLoadError(null);
    } catch (error) {
      if (isAbortError(error)) return;
      setLoadError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const reload = useCallback(() => {
    void load();
  }, [load]);

  const add = useCallback(
    async (draft: RuleDraft): Promise<string | null> => {
      setOperationError(null);
      try {
        await api.createRule(draft);
      } catch (error) {
        const message = errorMessage(error);
        setOperationError(message);
        return message;
      }
      await load();
      changed.current?.();
      return null;
    },
    [load],
  );

  const remove = useCallback(
    async (id: number): Promise<number | null> => {
      setOperationError(null);
      try {
        const { held } = await api.removeRule(id);
        await load();
        changed.current?.();
        return held;
      } catch (error) {
        setOperationError(errorMessage(error));
        return null;
      }
    },
    [load],
  );

  return { rules, loading, loadError, operationError, reload, add, remove };
}
