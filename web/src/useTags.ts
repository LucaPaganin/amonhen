import { useCallback, useEffect, useState } from "react";

import { api, errorMessage, isAbortError } from "./api";
import type { Tag } from "./types";
import type { CategoryFlags } from "./useCategories";

export interface TagsController {
  tags: Tag[];
  error: string | null;
  reload: () => void;
  /** Answers the error to show, or null once saved. */
  updateFlags: (id: number, flags: CategoryFlags) => Promise<string | null>;
}

/** The list of tags, read by each screen that offers one. */
export function useTags(): TagsController {
  const [tags, setTags] = useState<Tag[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      setTags(await api.tags(signal));
      setError(null);
    } catch (caught) {
      if (isAbortError(caught)) return;
      setError(errorMessage(caught));
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

  const updateFlags = useCallback(
    async (id: number, flags: CategoryFlags): Promise<string | null> => {
      try {
        await api.setTagFlags(id, flags);
        await load();
        return null;
      } catch (caught) {
        return errorMessage(caught);
      }
    },
    [load],
  );

  return { tags, error, reload, updateFlags };
}
