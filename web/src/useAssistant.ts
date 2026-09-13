import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "./api";
import type {
  AssistantContext,
  AssistantHistoryEntry,
  AssistantReading,
  AssistantState,
} from "./types";

export interface AssistantController {
  state: AssistantState | null;
  stateError: string | null;
  reading: AssistantReading | null;
  asking: boolean;
  askError: string | null;
  history: AssistantHistoryEntry[];
  notice: string | null;
  ask: (question: string, context: AssistantContext | null) => Promise<void>;
  decide: (category: string, decision: "accept" | "dismiss") => Promise<void>;
  reloadState: () => void;
  dismissNotice: () => void;
}

/**
 * The assistant as the screen sees it.
 *
 * Nothing here decides anything about the numbers: it asks the server, shows
 * what came back, and reloads the state so the count of the day's calls and the
 * proposals still waiting are never guessed.
 */
export function useAssistant(): AssistantController {
  const [state, setState] = useState<AssistantState | null>(null);
  const [stateError, setStateError] = useState<string | null>(null);
  const [reading, setReading] = useState<AssistantReading | null>(null);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [history, setHistory] = useState<AssistantHistoryEntry[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const reloadState = useCallback(() => setReloads((count) => count + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    api
      .assistant(controller.signal)
      .then((next) => {
        setState(next);
        setStateError(null);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException) return;
        setStateError(errorMessage(error));
      });
    api
      .assistantHistory(controller.signal)
      .then(setHistory)
      .catch(() => undefined);
    return () => controller.abort();
  }, [reloads]);

  const ask = useCallback(
    async (question: string, context: AssistantContext | null) => {
      setAsking(true);
      setAskError(null);
      try {
        setReading(await api.askAssistant(question, context));
        reloadState();
      } catch (error) {
        setAskError(errorMessage(error));
      } finally {
        setAsking(false);
      }
    },
    [reloadState],
  );

  const decide = useCallback(
    async (category: string, decision: "accept" | "dismiss") => {
      try {
        await api.decideBudgetProposal(category, decision);
        setNotice(
          decision === "accept"
            ? `Budget di ${category} salvato`
            : `Proposta per ${category} scartata`,
        );
        reloadState();
      } catch (error) {
        setNotice(`Non salvato: ${errorMessage(error)}`);
      }
    },
    [reloadState],
  );

  return {
    state,
    stateError,
    reading,
    asking,
    askError,
    history,
    notice,
    ask,
    decide,
    reloadState,
    dismissNotice: () => setNotice(null),
  };
}
