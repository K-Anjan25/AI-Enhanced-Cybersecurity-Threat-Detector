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
        "app-bg": {
          DEFAULT: "#0a0a0f",
        },
        "app-void": {
          DEFAULT: "#050508",
        },
        "app-surface": {
          DEFAULT: "#14141f",
        },
        "app-surface-raised": {
          DEFAULT: "#1e1e2b",
        },
        "app-subtle": {
          DEFAULT: "#23232f",
        },
        brand: {
          DEFAULT: "#f59e0b",
          sage: "#84a98c",
          clay: "#c9ada7",
          muted: "#1a1a1f",
        },
        "content-primary": {
          DEFAULT: "#f1f5f9",
        },
        "content-secondary": {
          DEFAULT: "#a1a1aa",
        },
        "content-tertiary": {
          DEFAULT: "#71717a",
        },
        "accent-primary": {
          DEFAULT: "#f59e0b",
        },
        "accent-secondary": {
          DEFAULT: "#84a98c",
        },
        "accent-glow": {
          DEFAULT: "#fde68a",
        },
        "line-subtle": {
          DEFAULT: "#23232f",
        },
        "line-bright": {
          DEFAULT: "#2d2d3a",
        },
        "status-success": {
          DEFAULT: "#84a98c",
        },
        "status-warning": {
          DEFAULT: "#f4a261",
        },
        "status-critical": {
          DEFAULT: "#e76f51",
        },
        "chart-1": {
          DEFAULT: "#f59e0b",
        },
        "chart-2": {
          DEFAULT: "#84a98c",
        },
        "chart-3": {
          DEFAULT: "#e76f51",
        },
        "chart-4": {
          DEFAULT: "#e9c46a",
        },
        "chart-5": {
          DEFAULT: "#c9ada7",
        },
      },
      boxShadow: {
        "accent-glow": "0 0 24px rgba(245, 158, 11, 0.35)",
        "sage-glow": "0 0 20px rgba(132, 169, 140, 0.35)",
        card: "0 1px 2px rgba(0, 0, 0, 0.25), 0 4px 12px rgba(0, 0, 0, 0.18)",
        raised: "0 6px 20px rgba(0, 0, 0, 0.35), 0 2px 4px rgba(0, 0, 0, 0.25)",
        overlay: "0 12px 40px rgba(0, 0, 0, 0.5)",
      },
      borderRadius: {
        xxs: "4px",
      },
      fontSize: {
        xxs: ["0.6875rem", "1rem"],
      },
      // Predefined spacing/radius scale keeps every component consistent.
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
          "0%": { opacity: "0", transform: "scale(0.97)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(16px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out",
        "fade-up": "fade-up 240ms ease-out",
        "scale-in": "scale-in 140ms ease-out",
        "slide-in-right": "slide-in-right 200ms ease-out",
      },
    },
  },
  plugins: [],
}