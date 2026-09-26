import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage, isAbortError } from "./api";
import type { SetupCredentials, SetupState } from "./types";

/**
 * The configuration as the app reads and writes it.
 *
 * A successful write answers with the payload as it now stands — the file the
 * screen is describing is the one it just changed — so the answer is kept
 * instead of followed by a read that would say the same thing. Each write
 * returns the message to show, or null.
 */
export interface SetupController {
  /** Null until the first answer: the app cannot tell what to draw before it. */
  state: SetupState | null;
  error: string | null;
  reload: () => void;
  saveCredentials: (body: SetupCredentials) => Promise<string | null>;
  renameAccount: (
    accountUid: string,
    name: string,
    startSyncDate: string,
  ) => Promise<string | null>;
  removeAccount: (accountUid: string) => Promise<string | null>;
}

export function useSetup(): SetupController {
  const [state, setState] = useState<SetupState | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Every answer carries the configuration as it stood when that request was
  // served, so the *order* answers are issued in is not the order they arrive
  // in. A read is only worth keeping when nothing newer was asked for; a write
  // is always worth keeping, because the server served the writes in order and
  // the last one to answer holds the newest document.
  const newestRead = useRef(0);

  const applyRead = useCallback((answer: SetupState, ticket: number) => {
    if (ticket !== newestRead.current) return;
    setState(answer);
    setError(null);
  }, []);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const ticket = ++newestRead.current;
      try {
        applyRead(await api.setup(signal), ticket);
      } catch (caught) {
        if (isAbortError(caught)) return;
        if (ticket === newestRead.current) setError(errorMessage(caught));
      }
    },
    [applyRead],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const reload = useCallback(() => {
    void load();
  }, [load]);

  const write = useCallback(
    async (request: Promise<SetupState>): Promise<string | null> => {
      // A write invalidates any read in flight: its answer is older than the
      // document this write is about to hand back.
      newestRead.current += 1;
      try {
        setState(await request);
        setError(null);
        return null;
      } catch (caught) {
        return errorMessage(caught);
      }
    },
    [],
  );

  const saveCredentials = useCallback(
    (body: SetupCredentials) => write(api.saveCredentials(body)),
    [write],
  );

  const renameAccount = useCallback(
    (accountUid: string, name: string, startSyncDate: string) =>
      write(api.renameConfiguredAccount(accountUid, name, startSyncDate)),
    [write],
  );

  const removeAccount = useCallback(
    (accountUid: string) => write(api.removeConfiguredAccount(accountUid)),
    [write],
  );

  return { state, error, reload, saveCredentials, renameAccount, removeAccount };
}
