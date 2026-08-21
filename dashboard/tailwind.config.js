/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', "Inter", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono Variable"', "JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        "app-bg": {
          DEFAULT: "#0a0f1c",
        },
        "app-void": {
          DEFAULT: "#060a14",
        },
        "app-surface": {
          DEFAULT: "#111827",
        },
        "app-surface-raised": {
          DEFAULT: "#141e32",
        },
        "app-subtle": {
          DEFAULT: "#1e293b",
        },
        brand: {
          DEFAULT: "#00e0ff",
          violet: "#7c3aed",
          indigo: "#1e1b4b",
          muted: "#0f172a",
        },
        "content-primary": {
          DEFAULT: "#f1f5f9",
        },
        "content-secondary": {
          DEFAULT: "#94a3b8",
        },
        "content-tertiary": {
          DEFAULT: "#7c8ca3",
        },
        "accent-primary": {
          DEFAULT: "#00e0ff",
        },
        "accent-secondary": {
          DEFAULT: "#7c3aed",
        },
        "accent-glow": {
          DEFAULT: "#67e8f9",
        },
        "line-subtle": {
          DEFAULT: "#1e293b",
        },
        "line-bright": {
          DEFAULT: "#334155",
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
        "chart-1": {
          DEFAULT: "#00e0ff",
        },
        "chart-2": {
          DEFAULT: "#7c3aed",
        },
        "chart-3": {
          DEFAULT: "#10b981",
        },
        "chart-4": {
          DEFAULT: "#f59e0b",
        },
        "chart-5": {
          DEFAULT: "#ec4899",
        },
      },
      boxShadow: {
        "accent-glow": "0 0 24px rgba(0, 224, 255, 0.35)",
        "violet-glow": "0 0 20px rgba(124, 58, 237, 0.35)",
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