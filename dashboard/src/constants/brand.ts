/**
 * NOCTRA Brand Constants — Single Source of Truth.
 * "You employ an analyst, you don't operate a dashboard."
 *
 * Mirrors the WordPress `theme.json` pattern: this file declares every design
 * token (settings), `tailwind.config.js` + `styles/globals.css` consume them
 * (styles), and components reference semantic token names only. Changing a
 * value here updates the whole product — no magic numbers in pages.
 */

export const BRAND_NAME = "NOCTRA" as const;
export const BRAND_WORDMARK = "NOCTRA" as const;
export const BRAND_TAGLINE = "Threat intelligence, always on." as const;
export const BRAND_HERO_LINE = "See the threat before it sees you." as const;
export const BRAND_POSITIONING =
  "NOCTRA continuously maps your attack surface, detects what matters, and turns fragmented signals into decisive action." as const;
export const BRAND_DOMAIN_HINT = "noctra.ai" as const;

/** Exact logo gradient (user-locked brand spec §12). Used on the mark, hero
 *  accent and primary actions only — never decorative noise. */
export const BRAND_GRADIENT = {
  from: "#a6ff3f", // signal green (flat — the accent is never a gradient)
  to: "#a6ff3f",
  sparkle: "#d6ff8c",
} as const;

export const BRAND_TYPOGRAPHY = {
  display: "DM Sans", // heroes, page titles, case headlines (bold + tight)
  sans: "DM Sans", // UI and body — the working surface
  mono: "Space Mono", // tech labels, identifiers, telemetry, timestamps
} as const;

/**
 * Fluid type scale (Major Second 1.125 — the SaaS typography playbook).
 * `display` faces carry brand moments; `ui` faces carry working surfaces.
 * Values are clamp() so type scales fluidly with the viewport, the same
 * trick WordPress fluid typography uses — no hand-written media queries.
 */
export const BRAND_TYPE_SCALE = {
  display: {
    "2xl": "clamp(2.75rem, 1.6rem + 3.6vw, 4.25rem)", // landing hero
    xl: "clamp(2rem, 1.35rem + 2vw, 2.75rem)", // page-level statements
    lg: "clamp(1.5rem, 1.2rem + 0.9vw, 1.875rem)", // section titles
    md: "clamp(1.25rem, 1.1rem + 0.45vw, 1.5rem)", // card headlines
    sm: "1.125rem", // emphasis leads
  },
  ui: {
    lg: "1rem", // body / table cells (base)
    md: "0.875rem", // secondary rows, inputs
    sm: "0.8125rem", // captions, badges
    xs: "0.75rem", // labels, timestamps
    "2xs": "0.6875rem", // overlines, kbd, metadata
  },
} as const;

/** Brand palette — ink foundation + periwinkle accent (see docs/noctra-redesign-spec.md §16). */
export const BRAND_PALETTE = {
  voidInk: "#070b0f", // ink canvas
  bgInk: "#070b0f",
  surface: "#0d151b", // console panel
  canvas: "#0d151b", // analyst-voice panels (console-panel treatment)
  accentPrimary: "#a6ff3f", // signal green — brand + primary action
  accentSecondary: "#d6ff8c", // hover / bright accents on ink
  accentDeep: "#73bf19", // signal-dark — accent text/links on light surfaces
  accentStar: "#d6ff8c", // insight sparkle
  badgeInk: "#071006", // text on signal fills
  success: "#4cc38a",
  warning: "#e5a54b",
  critical: "#f26d6d",
  contentPrimary: "#e8f0ed",
  contentSecondary: "#aebdc0",
  contentTertiary: "#8fa2a8",
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
  "#a6ff3f",
  "#4fb8a8",
  "#e5a54b",
  "#e77a8b",
  "#7e87a3",
] as const;

/** Radius scale (4px base, rounded-square system — matches the app icon badge). */
export const BRAND_RADII = {
  xs: "4px",
  sm: "6px",
  md: "8px",
  lg: "12px",
  xl: "16px",
  "2xl": "20px",
  pill: "999px",
} as const;

/** Shadow system — layered, calm, never glowy. */
export const BRAND_SHADOWS = {
  card: "0 1px 2px rgba(15, 16, 22, 0.05), 0 3px 10px rgba(15, 16, 22, 0.04)",
  raised: "0 8px 24px rgba(15, 16, 22, 0.12)",
  float: "0 12px 32px rgba(15, 16, 22, 0.16)",
  hero: "0 24px 64px rgba(8, 9, 13, 0.4)",
  navy: "0 8px 32px rgba(8, 9, 13, 0.35)",
  overlay: "0 16px 48px rgba(15, 16, 22, 0.18)",
} as const;

/** Breakpoints (Tailwind defaults — declared once for JS consumers). */
export const BRAND_BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  "2xl": 1536,
} as const;

/** Stacking order — one registry so drawers/overlays never fight. */
export const BRAND_Z_INDEX = {
  sticky: 20,
  drawer: 40,
  modal: 50,
  toast: 60,
  command: 70,
} as const;

/**
 * Real proof points used by the landing page (WordPress-style trust signals).
 * Every entry is true of the product today — nothing fabricated.
 */
export const BRAND_TRUST_POINTS = [
  {
    title: "Record-only by design",
    body: "NOCTRA records actions — it never executes them. Every recommendation is reversible.",
  },
  {
    title: "Full audit trail",
    body: "Every decision, chat question and state change is appended to an append-only audit log.",
  },
  {
    title: "Explained in plain English",
    body: "What happened, why it matters, what's affected — with stated confidence, never alarm.",
  },
  {
    title: "Self-hostable",
    body: "Docker Compose or Kubernetes. Your telemetry stays on your infrastructure.",
  },
] as const;
