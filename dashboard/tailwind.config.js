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
          DEFAULT: "#f4f6fa",
        },
        "app-void": {
          DEFAULT: "#e2e8f0",
        },
        "app-surface": {
          DEFAULT: "#ffffff",
          raised: "#f8fafc",
        },
        "app-subtle": {
          DEFAULT: "#eef2f7",
        },
        "app-navy": {
          DEFAULT: "#0e1320",
          raised: "#141b2d",
          subtle: "#1c253c",
        },
        brand: {
          DEFAULT: "#2563eb",
          cobalt: "#2563eb",
          navy: "#0e1320",
          emerald: "#10b981",
          amber: "#f59e0b",
          critical: "#ef4444",
        },
        "content-primary": {
          DEFAULT: "#0f172a",
        },
        "content-secondary": {
          DEFAULT: "#475569",
        },
        "content-tertiary": {
          DEFAULT: "#94a3b8",
        },
        "accent-primary": {
          DEFAULT: "#2563eb",
        },
        "accent-secondary": {
          DEFAULT: "#3b82f6",
        },
        "accent-glow": {
          DEFAULT: "#60a5fa",
        },
        // Categorical chart palette (matches the hex colors used by the
        // analytics charts in AIAnalyticsPage/DashboardOverviewPage).
        "chart-1": {
          DEFAULT: "#e76f51",
        },
        "chart-2": {
          DEFAULT: "#84a98c",
        },
        "chart-3": {
          DEFAULT: "#f4a261",
        },
        "chart-4": {
          DEFAULT: "#e9c46a",
        },
        "chart-5": {
          DEFAULT: "#7286d3",
        },
        "line-subtle": {
          DEFAULT: "#e2e8f0",
        },
        "line-bright": {
          DEFAULT: "#cbd5e1",
        },
        "line-navy": {
          DEFAULT: "#1e293b",
        },
        "status-success": {
          DEFAULT: "#10b981",
        },
        "status-warning": {
          DEFAULT: "#f59e0b",
        },
        "status-critical": {
          DEFAULT: "#ef4444",
        },
      },
      boxShadow: {
        card: "0 1px 3px rgba(0, 0, 0, 0.05), 0 4px 12px rgba(0, 0, 0, 0.03)",
        navy: "0 4px 20px rgba(14, 19, 32, 0.15), 0 2px 6px rgba(14, 19, 32, 0.1)",
        cobalt: "0 0 20px rgba(37, 99, 235, 0.3)",
        "accent-glow": "0 0 24px rgba(37, 99, 235, 0.35)",
        overlay: "0 12px 32px rgba(15, 23, 42, 0.18)",
        raised: "0 8px 24px rgba(15, 23, 42, 0.14)",
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
