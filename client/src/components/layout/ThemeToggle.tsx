"use client";

import { useState, useEffect, ReactNode } from "react";

export function ThemeToggle({ initial = "light" }: { initial?: "light" | "dark" }) {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof window !== "undefined") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    return initial;
  });

  useEffect(() => {
    const root = window.document.documentElement;
    root.setAttribute("data-theme", theme);
  }, [theme]);

  return null; // Rendered only for the side effect (setting data-theme on html)
}