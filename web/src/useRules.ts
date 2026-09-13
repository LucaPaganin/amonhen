import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage, isAbortError } from "./api";
import type { Rule } from "./types";

export interface RulesController {
  rules: Rule[];
  loading: boolean;
  loadError: string | null;
  /** Last failed write, shown as-is: the API's `detail` is the message. */
  operationError: string | null;
  reload: () => void;
  /** Upsert: the same text with another category is an edit of that rule. */
  add: (pattern: string, category: string) => Promise<boolean>;
  /** How many movements the rule held, or null when the call failed. */
  remove: (pattern: string) => Promise<number | null>;
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
    async (pattern: string, category: string): Promise<boolean> => {
      setOperationError(null);
      try {
        await api.createRule(pattern, category);
      } catch (error) {
        setOperationError(errorMessage(error));
        return false;
      }
      await load();
      changed.current?.();
      return true;
    },
    [load],
  );

  const remove = useCallback(
    async (pattern: string): Promise<number | null> => {
      setOperationError(null);
      try {
        const { held } = await api.removeRule(pattern);
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
