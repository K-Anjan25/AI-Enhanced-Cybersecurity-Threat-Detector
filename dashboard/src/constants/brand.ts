/**
 * Brand constants — single source of truth for the product identity.
 * NOCTRA kept per decision: serious, 6-char, 2-syllable, hard invented + nocturnal totem, abstract to grow.
 */
export const BRAND_NAME = "NOCTRA" as const;
export const BRAND_WORDMARK = "NOCTRA" as const;
export const BRAND_TAGLINE = "Silent. Precise. Always watching." as const;
export const BRAND_POSITIONING =
  "The AI analyst that never blinks — detects across logs, email and network, explains every verdict, and orchestrates response." as const;
export const BRAND_DOMAIN_HINT = "noctra.ai" as const;

/* Palette mirrors tailwind.config.js brand tokens for JS usage (charts, canvas). */
export const BRAND_PALETTE = {
  cyan: "#00e0ff",
  violet: "#7c3aed",
  void: "#0a0f1c",
  indigo: "#0f172a",
  success: "#10b981",
  warning: "#f59e0b",
  critical: "#ef4444",
} as const;

/* Serious 5-6 char, 2-syllable, abstract shortlist — hard invented + animal totem */
export const BRAND_SHORTLIST = ["NOCTRA", "KESTRA", "ORVEX", "STRYX", "KORVA"] as const;
