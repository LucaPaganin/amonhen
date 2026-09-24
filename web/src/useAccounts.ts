import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage, isAbortError } from "./api";
import type { Account, Declaration, NewAccount } from "./types";

/**
 * What a balance write answers: the account as it now stands, or the message to
 * show. A union rather than a nullable account, so a caller cannot read a
 * verification state off a write that failed.
 */
export type AccountWrite =
  | { account: Account; error: null }
  | { account: null; error: string };

export function useAccounts() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const latest = useRef<Account[]>([]);

  useEffect(() => {
    latest.current = accounts;
  }, [accounts]);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      setAccounts(await api.accounts(signal));
      setError(null);
      setLoading(false);
    } catch (caught) {
      if (isAbortError(caught)) return;
      setError(errorMessage(caught));
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

  // Optimistic: the flags flip immediately; a failed save rolls the list back
  // to its previous value. Returns the error message, or null on success.
  const setFlags = useCallback(
    async (
      id: number,
      flags: { investment?: boolean; reimport_deleted?: boolean },
    ): Promise<string | null> => {
      const snapshot = latest.current;
      setAccounts((current) =>
        current.map((account) => (account.id === id ? { ...account, ...flags } : account)),
      );
      try {
        await api.setAccountFlags(id, flags);
        reload();
        return null;
      } catch (caught) {
        setAccounts(snapshot);
        return errorMessage(caught);
      }
    },
    [reload],
  );

  // The writes below change balances and the verification derived from them, so
  // the list is refetched rather than patched with one row.
  const createAccount = useCallback(
    async (body: NewAccount): Promise<string | null> => {
      try {
        await api.createAccount(body);
        reload();
        return null;
      } catch (caught) {
        return errorMessage(caught);
      }
    },
    [reload],
  );

  const declareBalance = useCallback(
    async (id: number, body: Declaration): Promise<AccountWrite> => {
      try {
        // The answer carries the fresh check, so the row is patched with it
        // instead of triggering a second round trip for the same row.
        const updated = await api.declareBalance(id, body);
        setAccounts((current) => current.map((row) => (row.id === id ? updated : row)));
        return { account: updated, error: null };
      } catch (caught) {
        return { account: null, error: errorMessage(caught) };
      }
    },
    [],
  );

  const setOpening = useCallback(
    async (id: number, body: Declaration): Promise<AccountWrite> => {
      try {
        const updated = await api.setOpening(id, body);
        setAccounts((current) => current.map((row) => (row.id === id ? updated : row)));
        return { account: updated, error: null };
      } catch (caught) {
        return { account: null, error: errorMessage(caught) };
      }
    },
    [],
  );

  return {
    accounts,
    error,
    loading,
    reload,
    setFlags,
    createAccount,
    declareBalance,
    setOpening,
  };
}
