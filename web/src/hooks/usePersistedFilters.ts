"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchUiState, saveUiState } from "@/lib/api";

/**
 * Hook that persists filter state per-project via the API.
 *
 * - On mount: loads saved state from API, URL params take priority
 * - On change: debounced save to API (300ms)
 * - On project switch: react-query invalidates ["ui-state"], filters reload
 */
export function usePersistedFilters<T extends Record<string, string | number>>(
  /** Page key in ui_state.json, e.g. "papers", "screening" */
  pageKey: string,
  /** Default values when no saved state exists */
  defaults: T,
) {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch saved UI state from API
  const { data: savedState } = useQuery({
    queryKey: ["ui-state"],
    queryFn: fetchUiState,
    staleTime: 60_000,
  });

  // Build initial values: URL params > saved state > defaults
  const [filters, setFiltersRaw] = useState<T>(() => {
    const result = { ...defaults };
    // We can't read savedState synchronously on first render,
    // so we just use URL params > defaults here
    for (const key of Object.keys(defaults)) {
      const urlVal = searchParams.get(key);
      if (urlVal != null) {
        if (typeof defaults[key] === "number") {
          (result as Record<string, any>)[key] = parseInt(urlVal, 10) || defaults[key];
        } else {
          (result as Record<string, any>)[key] = urlVal;
        }
      }
    }
    return result;
  });

  // When saved state loads, apply it (only for keys not already set by URL)
  const appliedSaved = useRef<boolean>(false);
  useEffect(() => {
    if (!savedState || appliedSaved.current) return;
    const saved = savedState[pageKey];
    if (!saved) {
      appliedSaved.current = true;
      return;
    }
    setFiltersRaw((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const key of Object.keys(defaults)) {
        // Only apply saved value if URL didn't override it
        const urlVal = searchParams.get(key);
        if (urlVal == null && saved[key] != null && saved[key] !== prev[key]) {
          (next as Record<string, any>)[key] = saved[key];
          changed = true;
        }
      }
      return changed ? next : prev;
    });
    appliedSaved.current = true;
  }, [savedState, pageKey, defaults, searchParams]);

  // Sync filters to URL
  useEffect(() => {
    const params = new URLSearchParams();
    for (const [key, val] of Object.entries(filters)) {
      if (val !== defaults[key as keyof T]) {
        params.set(key, String(val));
      }
    }
    const qs = params.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, [filters, defaults]);

  // Debounced save to API
  const persistToApi = useCallback(
    (newFilters: T) => {
      if (saveTimer.current != null) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        try {
          const current = queryClient.getQueryData<Record<string, any>>(["ui-state"]) || {};
          const updated = { ...current, [pageKey]: newFilters };
          await saveUiState(updated);
          queryClient.setQueryData(["ui-state"], updated);
        } catch {
          // Silently fail — UI state persistence is best-effort
        }
      }, 300);
    },
    [pageKey, queryClient],
  );

  const setFilters = useCallback(
    (updater: T | ((prev: T) => T)) => {
      setFiltersRaw((prev) => {
        const next = typeof updater === "function" ? (updater as (p: T) => T)(prev) : updater;
        persistToApi(next);
        return next;
      });
    },
    [persistToApi],
  );

  /** Set a single filter key, optionally resetting page to 1 */
  const setFilter = useCallback(
    (key: keyof T, value: string | number, resetPage = false) => {
      setFilters((prev) => {
        const next = { ...prev, [key]: value };
        if (resetPage && "page" in next) {
          (next as Record<string, any>).page = 1;
        }
        return next;
      });
    },
    [setFilters],
  );

  return { filters, setFilters, setFilter };
}
