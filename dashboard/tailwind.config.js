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
      },
    },
  },
  plugins: [],
}
