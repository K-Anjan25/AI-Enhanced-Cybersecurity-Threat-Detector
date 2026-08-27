import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

/**
 * ThemeProvider — whole-app light/dark mode.
 *
 * Applies the `dark` class on <html>, which flips every semantic token in
 * globals.css (the DUALITY system). Persists the choice in localStorage
 * (`td_theme`); falls back to the OS preference on first visit; listens for
 * OS changes only while the user hasn't made an explicit choice.
 */

export type Theme = "light" | "dark";

const THEME_KEY = "td_theme";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const systemTheme = (): Theme =>
  typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";

const readStored = (): Theme | null => {
  try {
    const raw = window.localStorage.getItem(THEME_KEY);
    return raw === "dark" || raw === "light" ? raw : null;
  } catch {
    return null;
  }
};

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>(() => readStored() ?? systemTheme());

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.style.colorScheme = theme;
    // Keep the app background in sync so overscroll never flashes light.
    document.body.style.backgroundColor =
      theme === "dark" ? "rgb(12 14 20)" : "rgb(247 247 245)";
  }, [theme]);

  // Follow the OS only until the user makes an explicit choice.
  useEffect(() => {
    if (readStored()) return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => setThemeState(e.matches ? "dark" : "light");
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  const setTheme = useCallback((t: Theme) => {
    try {
      window.localStorage.setItem(THEME_KEY, t);
    } catch {
      /* private mode — in-memory only */
    }
    setThemeState(t);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem(THEME_KEY, next);
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>{children}</ThemeContext.Provider>
  );
};

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within <ThemeProvider>");
  return ctx;
}

export default ThemeProvider;
