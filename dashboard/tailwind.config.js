/**
 * NOCTRA design tokens — DUALITY (spec docs/noctra-redesign-spec.md §16–18).
 *
 * Scope-flipped tokens (CSS variables, defined in globals.css):
 *   day workspace = :root defaults; night canvas = `.night` scope on the
 *   panels where the analyst speaks (AI briefs, reasoning, evidence, blast
 *   radius, reports). Components use semantic names only.
 *
 * Fixed tokens (same in both scopes): the ink canvas family (`app-void`,
 * `app-navy`) used inside night panels, `brand-ink` (text on accent fills),
 * and the categorical dataviz palette.
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
        // ── Scope-flipped surfaces ────────────────────────────────────────
        "app-bg": "rgb(var(--c-app-bg) / <alpha-value>)",
        "app-surface": {
          DEFAULT: "rgb(var(--c-app-surface) / <alpha-value>)",
          raised: "rgb(var(--c-app-surface-raised) / <alpha-value>)",
        },
        "app-subtle": "rgb(var(--c-app-subtle) / <alpha-value>)",

        // ── Fixed ink canvas (night panels) ───────────────────────────────
        "app-void": {
          DEFAULT: "#08090D", // deepest layer: code, wells
        },
        "app-navy": {
          DEFAULT: "#10131C", // editorial canvas panels
          raised: "#14161D",
          subtle: "#1B1E28",
        },

        // ── Brand accent (periwinkle family — see spec §15 audit) ─────────
        brand: {
          DEFAULT: "#A8A2FF",
          ink: "#191B22", // text on accent fills (7.6:1 on periwinkle)
        },
        "accent-primary": "rgb(var(--c-accent-primary) / <alpha-value>)",
        "accent-secondary": "rgb(var(--c-accent-secondary) / <alpha-value>)",

        // ── Scope-flipped content ─────────────────────────────────────────
        "content-primary": "rgb(var(--c-content-primary) / <alpha-value>)",
        "content-secondary": "rgb(var(--c-content-secondary) / <alpha-value>)",
        "content-tertiary": "rgb(var(--c-content-tertiary) / <alpha-value>)",

        // ── Scope-flipped lines ───────────────────────────────────────────
        "line-subtle": "rgb(var(--c-line-subtle) / <alpha-value>)",
        "line-bright": "rgb(var(--c-line-bright) / <alpha-value>)",

        // ── Scope-flipped status / severity (never color alone) ───────────
        "status-success": "rgb(var(--c-status-success) / <alpha-value>)",
        "status-warning": "rgb(var(--c-status-warning) / <alpha-value>)",
        "status-critical": "rgb(var(--c-status-critical) / <alpha-value>)",
        severity: {
          low: "rgb(var(--c-severity-low) / <alpha-value>)",
          medium: "rgb(var(--c-severity-medium) / <alpha-value>)",
          high: "rgb(var(--c-severity-high) / <alpha-value>)",
          critical: "rgb(var(--c-severity-critical) / <alpha-value>)",
        },

        // Dataviz categorical palette (= BRAND_DATAVIZ in constants/brand.ts).
        "chart-1": { DEFAULT: "#8B7CF6" },
        "chart-2": { DEFAULT: "#4FB8A8" },
        "chart-3": { DEFAULT: "#E5A54B" },
        "chart-4": { DEFAULT: "#E77A8B" },
        "chart-5": { DEFAULT: "#7E87A3" },
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 16, 22, 0.05), 0 3px 10px rgba(15, 16, 22, 0.04)",
        navy: "0 8px 32px rgba(8, 9, 13, 0.35)",
        overlay: "0 16px 48px rgba(15, 16, 22, 0.18)",
        raised: "0 8px 24px rgba(15, 16, 22, 0.12)",
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
