/**
 * NOCTRA design tokens (dark-first).
 * Source of truth for the redesign spec (docs/noctra-redesign-spec.md §16–18).
 * Tokens are semantic (role-named): components must reference these, not raw
 * slate/blue literals. `app-navy` keeps its legacy name for the editorial
 * canvas layer (#10131C).
 */
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', "Inter", "system-ui", "sans-serif"],
        display: ["Sora", "Inter", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono Variable"', "JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        // ── Surfaces (dark-first) ─────────────────────────────
        "app-void": {
          DEFAULT: "#08090D", // deepest layer: scroll wells, code surfaces
        },
        "app-bg": {
          DEFAULT: "#0C0E14", // page background
        },
        "app-surface": {
          DEFAULT: "#14161D", // cards, tables
          raised: "#1A1D26", // hover / raised cards / popovers
        },
        "app-subtle": {
          DEFAULT: "#1B1E28", // table headers, input fills, muted chips
        },
        "app-navy": {
          // Legacy token name kept — the "night canvas" editorial panels.
          DEFAULT: "#10131C",
          raised: "#14161D",
          subtle: "#1B1E28",
        },

        // ── Brand accent (periwinkle family) ────────────────────────────────
        // Evidence-based choice (spec §15): the light end of the violet family
        // is unclaimed in security branding and has the strongest contrast.
        brand: {
          DEFAULT: "#A8A2FF",
          ink: "#0C0E14",
        },
        "accent-primary": {
          DEFAULT: "#A8A2FF", // brand, primary buttons, links
        },
        "accent-secondary": {
          DEFAULT: "#C9C4FF", // hover / bright accents on dark
        },

        // ── Content ───────────────────────────────────────────────────────
        "content-primary": {
          DEFAULT: "#ECEEF4",
        },
        "content-secondary": {
          DEFAULT: "#A6ACBF",
        },
        "content-tertiary": {
          DEFAULT: "#6E7487",
        },

        // ── Lines ─────────────────────────────────────────────────────────
        "line-subtle": {
          DEFAULT: "#232735",
        },
        "line-bright": {
          DEFAULT: "#323850",
        },

        // ── Status ────────────────────────────────────────────────────────
        "status-success": {
          DEFAULT: "#4CC38A", // approved, healthy
        },
        "status-warning": {
          DEFAULT: "#E5A54B", // awaiting decision, high severity
        },
        "status-critical": {
          DEFAULT: "#F26D6D", // critical severity, destructive
        },

        // ── Severity ramp (dot + text label, never color alone) ──────────
        severity: {
          low: "#52B788",
          medium: "#E5A54B",
          high: "#F0824F",
          critical: "#F26D6D",
        },

        // Dataviz categorical palette (= BRAND_DATAVIZ in constants/brand.ts).
        "chart-1": { DEFAULT: "#8B7CF6" },
        "chart-2": { DEFAULT: "#4FB8A8" },
        "chart-3": { DEFAULT: "#E5A54B" },
        "chart-4": { DEFAULT: "#E77A8B" },
        "chart-5": { DEFAULT: "#7E87A3" },
      },
      boxShadow: {
        card: "0 1px 2px rgba(4, 6, 12, 0.4), 0 4px 16px rgba(4, 6, 12, 0.28)",
        navy: "0 8px 32px rgba(4, 6, 12, 0.55)",
        overlay: "0 16px 48px rgba(4, 6, 12, 0.6)",
        raised: "0 8px 24px rgba(4, 6, 12, 0.45)",
      },
      borderRadius: {
        xxs: "4px",
      },
      fontSize: {
        xxs: ["0.6875rem", "1rem"],
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(2px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.96)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(12px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out",
        "fade-up": "fade-up 240ms ease-out",
        "scale-in": "scale-in 140ms ease-out",
        "slide-in-right": "slide-in-right 180ms ease-out",
      },
    },
  },
  plugins: [],
}
