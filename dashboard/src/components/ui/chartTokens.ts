import React from "react";

/**
 * Chart tooltip style shared by all Recharts surfaces.
 * Resolves through the app's CSS variables so it themes with light/dark —
 * no more hard-coded dark tooltips floating over light dashboards.
 */
export const CHART_TOOLTIP_STYLE = {
  background: "rgb(var(--c-app-surface))",
  border: "1px solid rgb(var(--c-line-bright))",
  borderRadius: 12,
  color: "rgb(var(--c-content-primary))",
  fontSize: 12,
  boxShadow: "0 8px 24px rgba(15,16,22,0.12)",
} as const;

/**
 * Brand severity ramp for data-viz — must match constants/brand.ts
 * BRAND_SEVERITY (never the old orange palette).
 */
export const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "#f26d6d",
  HIGH: "#f0824f",
  MEDIUM: "#e5a54b",
  LOW: "#52b788",
};

export const CHART_TOOLTIP_STYLE_AXIS = {
  tick: { fill: "rgb(var(--c-content-tertiary))", fontSize: 11 },
} as const;
