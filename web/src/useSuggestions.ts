import { useCallback, useEffect, useState } from "react";

import { api, errorMessage, isAbortError } from "./api";
import type { Suggestion, SuggestionDecision, SuggestionDecisionOutcome } from "./types";

export interface SuggestionController {
  suggestions: Suggestion[];
  loading: boolean;
  loadError: string | null;
  reload: () => Promise<void>;
  /**
   * Optimistic: the proposal leaves the list, a failed decision puts it back.
   * `category` corrects the proposal before accepting it; `rule` is the text of
   * the rule to write, and without it the decision is about the movements alone.
   */
  decide: (
    suggestion: Suggestion,
    decision: SuggestionDecision,
    options?: { category?: string; rule?: string },
  ) => Promise<SuggestionDecisionResult>;
}

/** The server's message when the decision was refused, and what it did when it was not. */
export interface SuggestionDecisionResult {
  error: string | null;
  outcome: SuggestionDecisionOutcome | null;
}

export function useSuggestions(): SuggestionController {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      setSuggestions(await api.suggestions(signal));
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

  const reload = useCallback(() => load(), [load]);

  const decide = useCallback(
    async (
      suggestion: Suggestion,
      decision: SuggestionDecision,
      options: { category?: string; rule?: string } = {},
    ): Promise<SuggestionDecisionResult> => {
      setSuggestions((current) => current.filter((item) => item.merchant !== suggestion.merchant));
      try {
        const outcome = await api.decideSuggestion(suggestion.merchant, decision, options);
        void load();
        return { error: null, outcome };
      } catch (error) {
        setSuggestions((current) =>
          [...current, suggestion].sort((a, b) => a.merchant.localeCompare(b.merchant)),
        );
        return { error: errorMessage(error), outcome: null };
      }
    },
    [load],
  );

  return { suggestions, loading, loadError, reload, decide };
}
