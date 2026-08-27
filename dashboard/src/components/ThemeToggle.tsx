import React from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "../theme/ThemeProvider";
import { cn } from "./ui/Button";

/**
 * ThemeToggle — the light/dark switch (Apple-style sun/moon pill).
 * Mirrors the OS default on first visit; persists the explicit choice.
 */
export interface ThemeToggleProps {
  className?: string;
  /** Use the translucent surface style (for the floating landing nav). */
  variant?: "pill" | "ghost";
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ className, variant = "ghost" }) => {
  const { theme, toggleTheme } = useTheme();
  const dark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      className={cn(
        "w-9 h-9 rounded-full flex items-center justify-center transition cursor-pointer shrink-0",
        variant === "pill"
          ? "border border-line-subtle bg-app-surface text-content-secondary hover:text-content-primary hover:shadow-float"
          : "text-content-tertiary hover:text-content-primary hover:bg-app-subtle",
        className
      )}
    >
      {dark ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
    </button>
  );
};

export default ThemeToggle;
