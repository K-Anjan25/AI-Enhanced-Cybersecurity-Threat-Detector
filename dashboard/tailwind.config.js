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
        "line-subtle": {
          DEFAULT: "#e2e8f0",
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
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out",
        "fade-up": "fade-up 240ms ease-out",
      },
    },
  },
  plugins: [],
}
