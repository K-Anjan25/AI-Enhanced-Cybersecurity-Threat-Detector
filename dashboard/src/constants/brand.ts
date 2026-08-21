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

/* Palette mirrors tailwind.config.js Obsidian Ember tokens for JS usage (charts, canvas). */
export const BRAND_PALETTE = {
  amber: "#f59e0b",
  sage: "#84a98c",
  void: "#0a0a0f",
  clay: "#c9ada7",
  success: "#84a98c",
  warning: "#f4a261",
  critical: "#e76f51",
} as const;

/* Serious 5-6 char, 2-syllable, abstract shortlist — hard invented + animal totem */
export const BRAND_SHORTLIST = ["NOCTRA", "KESTRA", "ORVEX", "STRYX", "KORVA"] as const;
