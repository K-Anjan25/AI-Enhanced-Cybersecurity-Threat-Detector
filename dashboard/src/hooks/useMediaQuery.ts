import { useEffect, useState } from "react";
import { BRAND_BREAKPOINTS } from "../constants/brand";

/**
 * useMediaQuery — SSR-safe matchMedia hook. Also ships named breakpoint
 * helpers for the common Tailwind breakpoints.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    setMatches(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

export function useIsDesktop(): boolean {
  return useMediaQuery(`(min-width: ${BRAND_BREAKPOINTS.lg}px)`);
}

export function useIsMobile(): boolean {
  return useMediaQuery(`(max-width: ${BRAND_BREAKPOINTS.md - 1}px)`);
}
