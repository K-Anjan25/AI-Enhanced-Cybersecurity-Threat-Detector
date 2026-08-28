/**
 * NOCTRA design tokens — SIGNAL (design source: newfile.html, the Canva export
 * of the NOCTRA landing — ink canvas + signal green, DM Sans + Space Mono).
 *
 * Scope-flipped tokens (CSS variables, defined in globals.css):
 *   :root (and html.dark) = signal dark (the default);
 *   html.light            = "day ops" paper variant;
 *   .night                = the analyst's voice — always ink (console panels).
 *
 * Fixed tokens: the brand ink (text on signal fills) and the categorical
 * dataviz palette. Everything is sharp: the radius scale is compressed to
 * 2–4px (rounded-full stays for tags/avatars).
 */
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"DM Sans Variable"', '"DM Sans"', "system-ui", "sans-serif"],
        display: ['"DM Sans Variable"', '"DM Sans"', "system-ui", "sans-serif"],
        mono: ['"Space Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        // ── Scope-flipped surfaces ────────────────────────────────────────
        "app-bg": "rgb(var(--c-app-bg) / <alpha-value>)",
        "app-surface": {
          DEFAULT: "rgb(var(--c-app-surface) / <alpha-value>)",
          raised: "rgb(var(--c-app-surface-raised) / <alpha-value>)",
        },
        "app-subtle": "rgb(var(--c-app-subtle) / <alpha-value>)",

        // ── Fixed ink canvas (night panels / wells) ──────────────────────
        "app-void": {
          DEFAULT: "#070b0f", // deepest layer: code, wells
        },
        "app-navy": {
          DEFAULT: "#0d151b", // console panel base
          raised: "#131d24",
          subtle: "#1a262e",
        },

        // ── Brand accent (signal green — flat, never a gradient) ─────────
        brand: {
          DEFAULT: "#a6ff3f", // signal
          ink: "#071006", // text on signal fills (from newfile action-button)
        },
        "accent-primary": "rgb(var(--c-accent-primary) / <alpha-value>)",
        "accent-secondary": "rgb(var(--c-accent-secondary) / <alpha-value>)",

        // ── Scope-flipped content ─────────────────────────────────────────
        "content-primary": "rgb(var(--c-content-primary) / <alpha-value>)",
        "content-secondary": "rgb(var(--c-content-secondary) / <alpha-value>)",
        "content-tertiary": "rgb(var(--c-content-tertiary) / <alpha-value>)",

        // ── Scope-flipped lines (vars hold pre-blended dim hues) ─────────
        "line-subtle": "rgb(var(--c-line-subtle) / <alpha-value>)",
        "line-bright": "rgb(var(--c-line-bright) / <alpha-value>)",

        // ── Scope-flipped status / severity (never color alone) ──────────
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
        "chart-1": { DEFAULT: "#a6ff3f" }, // signal green
        "chart-2": { DEFAULT: "#4fb8a8" },
        "chart-3": { DEFAULT: "#e5a54b" },
        "chart-4": { DEFAULT: "#e77a8b" },
        "chart-5": { DEFAULT: "#7e87a3" },
      },
      backgroundImage: {
        // Signal is FLAT — the token stays for compatibility, now solid green.
        "brand-gradient": "linear-gradient(135deg, #a6ff3f 0%, #a6ff3f 100%)",
        "brand-gradient-soft":
          "linear-gradient(135deg, rgba(166,255,63,0.14) 0%, rgba(166,255,63,0.07) 100%)",
      },
      boxShadow: {
        card: "0 1px 2px rgba(0, 0, 0, 0.4), 0 3px 12px rgba(0, 0, 0, 0.22)",
        navy: "0 26px 80px rgba(0, 0, 0, 0.3)", // console-panel shadow
        overlay: "0 16px 48px rgba(0, 0, 0, 0.5)",
        raised: "0 8px 24px rgba(0, 0, 0, 0.35)",
        float: "0 12px 32px rgba(0, 0, 0, 0.45)",
        hero: "0 24px 70px rgba(0, 0, 0, 0.35)",
        signal: "0 12px 28px rgba(166, 255, 63, 0.2)", // action-button hover glow
      },
      borderRadius: {
        xxs: "2px",
        // Sharp system (newfile uses rounded-sm / 2px) — compress the scale.
        sm: "2px",
        md: "2px",
        lg: "3px",
        xl: "3px",
        "2xl": "4px",
        "3xl": "6px",
      },
      fontSize: {
        xxs: ["0.6875rem", "1rem"],
        // ── Fluid type scale — DM Sans, tight display tracking ───────────
        "display-2xl": [
          "clamp(2.75rem, 1.6rem + 3.6vw, 4.25rem)",
          { lineHeight: "0.98", letterSpacing: "-0.045em" },
        ],
        "display-xl": [
          "clamp(2rem, 1.35rem + 2vw, 2.75rem)",
          { lineHeight: "1.0", letterSpacing: "-0.04em" },
        ],
        "display-lg": [
          "clamp(1.5rem, 1.2rem + 0.9vw, 1.875rem)",
          { lineHeight: "1.08", letterSpacing: "-0.03em" },
        ],
        "display-md": [
          "clamp(1.25rem, 1.1rem + 0.45vw, 1.5rem)",
          { lineHeight: "1.15", letterSpacing: "-0.02em" },
        ],
        "display-sm": ["1.125rem", { lineHeight: "1.3", letterSpacing: "-0.015em" }],
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
