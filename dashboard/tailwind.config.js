/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "app-bg": {
          DEFAULT: "#0a0f1c",
        },
        "app-surface": {
          DEFAULT: "#111827",
        },
        "app-surface-raised": {
          DEFAULT: "#151e2e",
        },
        "app-subtle": {
          DEFAULT: "#1e293b",
        },
        "content-primary": {
          DEFAULT: "#f1f5f9",
        },
        "content-secondary": {
          DEFAULT: "#94a3b8",
        },
        "content-tertiary": {
          DEFAULT: "#64748b",
        },
        "accent-primary": {
          DEFAULT: "#22d3ee",
        },
        "accent-secondary": {
          DEFAULT: "#0e7490",
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
          DEFAULT: "#34d399",
        },
        "status-warning": {
          DEFAULT: "#fbbf24",
        },
        "status-critical": {
          DEFAULT: "#f87171",
        },
      },
      boxShadow: {
        "accent-glow": "0 0 20px rgba(34, 211, 238, 0.35)",
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
        "scale-in": "scale-in 140ms ease-out",
        "slide-in-right": "slide-in-right 200ms ease-out",
      },
    },
  },
  plugins: [],
}