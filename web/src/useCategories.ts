import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage, isAbortError } from "./api";
import type { Category } from "./types";

export interface CategoryFlags {
  episodic?: boolean;
  essential?: boolean;
}

export function useCategories() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const latest = useRef<Category[]>([]);

  useEffect(() => {
    latest.current = categories;
  }, [categories]);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      setCategories(await api.categories(signal));
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

  // Optimistic: the flag flips immediately; a failed save rolls the whole list
  // back to its previous value. Returns the error message, or null on success.
  const updateCategoryFlags = useCallback(
    async (id: number, flags: CategoryFlags): Promise<string | null> => {
      const snapshot = latest.current;
      setCategories((current) =>
        current.map((category) => (category.id === id ? { ...category, ...flags } : category)),
      );
      try {
        await api.setCategoryFlags(id, flags);
        return null;
      } catch (caught) {
        setCategories(snapshot);
        return errorMessage(caught);
      }
    },
    [],
  );

  return { categories, error, loading, reload, updateCategoryFlags };
}
