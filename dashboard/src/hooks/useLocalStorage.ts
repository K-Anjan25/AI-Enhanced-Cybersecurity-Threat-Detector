import { useCallback, useState } from "react";

/**
 * useLocalStorage — typed, JSON-safe localStorage binding. Falls back to the
 * in-memory value when storage is unavailable (private mode).
 */
export function useLocalStorage<T>(key: string, initial: T): [T, (value: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      return raw !== null ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        try {
          window.localStorage.setItem(key, JSON.stringify(resolved));
        } catch {
          /* storage unavailable — memory only */
        }
        return resolved;
      });
    },
    [key]
  );

  return [value, set];
}
