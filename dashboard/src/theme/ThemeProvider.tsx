import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

/**
 * ThemeProvider — whole-app theme.
 *
 * NOCTRA is dark-first (the SIGNAL system): the default is the signal-dark
 * ink canvas; `light` selects the "day ops" paper variant. The provider
 * toggles `dark`/`light` classes on <html>` (globals.css maps them), persists
 * the choice in localStorage (`td_theme`) and defaults to dark.
 */

export type Theme = "light" | "dark";

const THEME_KEY = "td_theme";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const readStored = (): Theme | null => {
  try {
    const raw = window.localStorage.getItem(THEME_KEY);
    return raw === "dark" || raw === "light" ? raw : null;
  } catch {
    return null;
  }
};

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Dark-first: the brand is the ink canvas; stored preference wins.
  const [theme, setThemeState] = useState<Theme>(() => readStored() ?? "dark");

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.classList.toggle("light", theme === "light");
    root.style.colorScheme = theme;
    // Keep the app background in sync so overscroll never flashes.
    document.body.style.backgroundColor =
      theme === "dark" ? "rgb(7 11 15)" : "rgb(238 241 236)";
  }, [theme]);

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
