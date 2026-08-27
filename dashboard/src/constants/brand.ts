/**
 * NOCTRA Brand Constants — Single Source of Truth.
 * "You employ an analyst, you don't operate a dashboard."
 */
export const BRAND_NAME = "NOCTRA" as const;
export const BRAND_WORDMARK = "NOCTRA" as const;
export const BRAND_TAGLINE = "Your autonomous security analyst." as const;
export const BRAND_TAGLINE_SECONDARY = "See less. Know more." as const;
export const BRAND_POSITIONING =
  "NOCTRA is the security analyst a small company employs: it watches continuously, explains plainly, proposes one reversible action, and records every decision." as const;
export const BRAND_DOMAIN_HINT = "noctra.ai" as const;

export const BRAND_TYPOGRAPHY = {
  display: "Sora",
  sans: "Inter",
  mono: "JetBrains Mono",
} as const;

/** Brand palette — ink foundation + periwinkle accent (see docs/noctra-redesign-spec.md §16). */
export const BRAND_PALETTE = {
  voidInk: "#08090d",
  bgInk: "#0c0e14",
  surface: "#14161d",
  canvas: "#10131c", // editorial canvas panels (NOCTRA's voice)
  accentPrimary: "#9d7cff", // PRIMARY — brand + primary action (lavender, gradient end)
  accentSecondary: "#c9c4ff", // hover / bright accents on dark
  accentDeep: "#6c5ce7", // gradient start — accent text/links on light surfaces
  accentStar: "#b18cff", // insight sparkle
  badgeInk: "#0b0e1a", // app-icon badge background
  success: "#4cc38a",
  warning: "#e5a54b",
  critical: "#f26d6d",
  contentPrimary: "#eceef4",
  contentSecondary: "#a6acbf",
  contentTertiary: "#6e7487",
} as const;

/** Severity ramp — always rendered as dot + label, never color alone. */
export const BRAND_SEVERITY = {
  LOW: "#52b788",
  MEDIUM: "#e5a54b",
  HIGH: "#f0824f",
  CRITICAL: "#f26d6d",
} as const;

/** Categorical data-visualization palette. */
export const BRAND_DATAVIZ = [
  "#8b7cf6",
  "#4fb8a8",
  "#e5a54b",
  "#e77a8b",
  "#7e87a3",
] as const;
