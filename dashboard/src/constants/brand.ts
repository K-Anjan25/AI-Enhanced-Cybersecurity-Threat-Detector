/**
 * Brand constants — single source of truth for the product identity.
 * Swap BRAND_NAME to re-theme without touching components.
 * Shortlist researched (2026 naming trends: serious, 5-6 letters, plosive, invented):
 *  1. NOCTRA (recommended) — nocturnal sentinel, built for the night shift
 *  2. KESTRA — kestrel hover + orchestration
 *  3. VIGLA — vigilance compressed
 *  4. OBSKRA — obscura, reveals hidden image
 *  5. CORVEX — corvus + vex (raven-intelligent)
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

/* Shortlist for future rotation / A/B — kept here so rename is one-line. */
export const BRAND_SHORTLIST = ["NOCTRA", "KESTRA", "VIGLA", "OBSKRA", "CORVEX"] as const;
