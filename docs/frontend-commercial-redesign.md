# NOCTRA — Commercial-Grade Frontend Redesign
*Researched from WordPress + WooCommerce's best implementations, applied to a security product.*

Status: **Active** — companion to [`docs/noctra-redesign-spec.md`](noctra-redesign-spec.md).
Stage 1 (this pass): token system, hooks, component library additions, landing page rewrite
(WordPress-grade marketing surface), dashboard shell upgrade (WooCommerce-storefront patterns:
sticky header + primary action, slide-out "pending decisions" drawer, live count pills).

---

## 1. Why WordPress & WooCommerce

WordPress powers ~43% of the web and WooCommerce the majority of online stores. That scale
means the ecosystem has converged on battle-tested answers to the same problems every product
frontend faces:

| Problem | WordPress answer | WooCommerce answer |
| --- | --- | --- |
| Design tokens drifting | `theme.json` — one file, declarative settings + styles, generates CSS variables | Same block-theme pipeline, per-block styles |
| Pages becoming unmanageable | Block patterns / template parts — reusable layout recipes | Product grid, mini-cart, checkout blocks |
| Feature bloat | Hooks (`do_action` / `apply_filters`) — extension points, no core edits | `woocommerce_add_to_cart_fragments` etc. |
| Users losing the thread | Template hierarchy + clear IA | Distraction-free checkout, sticky cart |
| Trust | Provenance everywhere, plugin reviews | Trust badges, testimonials, stock/sales signals |
| Performance | Fluid typography, tokenized CSS, caching | Lazy fragments, server-rendered cart, ≤ few KB JS |

Our conclusion: NOCTRA should adopt the **architecture** (declarative tokens, extension-point
hooks, reusable patterns) and the **storefront conversion discipline** (sticky header with a
primary action, always-visible "cart" = pending decisions, trust signals, distraction-free
decision flow), not the visual style. A security analyst product must stay calm and precise —
we borrow structure, never cyberpunk decoration.

## 2. What we researched (sources)

1. **WordPress block themes & `theme.json`** — a single declarative file defines every design
   token (`settings`) and their defaults (`styles`); the system generates CSS custom properties
   (`--wp--preset--*`), keeps editor and frontend in sync, supports *style variations* (one
   theme, multiple moods) and *fluid typography* (sizes scale by viewport without media
   queries). Devs ship tokens + a pattern library; layout is content-first.
   → NOCTRA equivalent: `constants/brand.ts` + `tailwind.config.js` + CSS variables in
   `styles/globals.css`; our DUALITY day/night scopes behave like style variations; fluid
   `clamp()` type scale added this pass.

2. **WordPress hooks** — *actions* (`do_action`) fire side effects at named points; *filters*
   (`apply_filters`) transform data; any plugin/theme can attach with priority, namespaced
   names; Query Monitor debugs. The point: extension without editing core.
   → NOCTRA equivalent (added this pass): a typed browser-event bus
   `hooks/useNoctraEvent` + `lib/events.ts` with namespaced, priority-ordered listeners
   (`noctra:command-menu`, `noctra:open-pending-drawer`, `noctra:toast`, …), mirroring
   `do_action`/`add_action`; data-transform filters arrive with react-query selectors.

3. **WooCommerce storefront patterns** — the conversion playbook:
   - Sticky header with a *single* prominent CTA and a cart button carrying a live count pill.
   - Mini-cart = slide-out drawer, non-blocking, updates in place (cart fragments), prominent
     "go to checkout" CTA; empty state copy written by hand.
   - Product grid: image-first cards, one clear per-card CTA, filters up top.
   - Product page = distraction-free: gallery, short description, price, one add-to-cart,
     trust badges, reviews, "you may also like".
   - Homepage = hero with product preview (not abstract marketing art), social proof strip,
     feature grid, final CTA.
   - Trust signals (SOC 2, PCI, guarantees) placed where doubt appears.
   → NOCTRA equivalents (this pass): sticky top bar with "Review decision" primary action;
   **Pending Decisions Drawer** (slide-out, live count, approve/decline CTA, honest empty
   state); case feed = product-grid discipline (one clear action per row); homepage hero shows
   the actual product (a real CSS-built case preview), not abstract art.

4. **SaaS typography rules** — mathematical type scale (Major Second 1.125 / Minor Third 1.2),
   ≥ 4.5:1 contrast, humanist sans for UI + monospace for numbers/data, size = importance,
   weight = emphasis, color = state. Inter remains the strongest default; display faces give
   brand moments (our Sora).
   → Added this pass: explicit 8-step `display` + `ui` type scales in tokens, tabular numbers
   for data, mono for identifiers/severity metadata.

5. **Security-SaaS dashboard patterns** — dark-first calm surfaces, KPI cards + incident feed,
   sidebar nav, high-impact visuals. NOCTRA already complies; we keep the analyst-first
   framing ("you employ an analyst, not a dashboard").

## 3. WordPress → NOCTRA mapping

| WordPress / WooCommerce concept | NOCTRA implementation |
| --- | --- |
| `theme.json` settings/styles | `constants/brand.ts` (JS source of truth) → `tailwind.config.js` tokens → CSS vars in `globals.css`; DUALITY day/night = style variations |
| Block patterns / template parts | `components/landing/*` (Hero, TrustBar, FeatureGrid, HowItWorks, FinalCTA, Footer) and `components/storefront/*` (PendingDecisionsDrawer); pages compose patterns |
| Hooks: actions / filters | `lib/events.ts` + `hooks/useNoctraEvent` (action bus); react-query `select` for data filters |
| Sticky header + CTA | Landing nav hides on scroll-down, shows on scroll-up (`useScrollDirection`); dashboard top bar keeps primary action always visible |
| Mini-cart drawer + count pill | PendingDecisionsDrawer with live pending count pill; fragment-style refresh after approve/decline |
| Product grid / card CTA discipline | Case feed & alerts: one explicit action per row, severity dot + label, no color-only states |
| Trust badges | Real proof points only: record-only design, full audit trail, reversible actions, self-hostable, open loop demo |
| Distraction-free checkout | Case workspace decision rail (existing) — one decision, one undo, report after |
| Fluid typography | `clamp()` scale in tokens (`text-display-*`) |
| Empty states written by hand | "Nothing needs you right now." etc. (existing voice, retained) |

## 4. What changed in this pass

**System**
- `constants/brand.ts` — extended: `BRAND_GRADIENT`, `TYPE_SCALE`, `RADII`, `SHADOWS`,
  `BREAKPOINTS`, `Z_INDEX`, `TRUST_POINTS` (real proof points used by the landing).
- `tailwind.config.js` — fluid display/UI type scales (`clamp()`), `text-2xs`, gradient
  utilities, new shadows (`hero`, `float`), radius tokens, `transition` tokens.
- `styles/globals.css` — `brand-gradient` utilities, focus-ring token, selection color,
  scroll-behavior, tabular-nums for data, `text-balance` helpers.
- `hooks/` (new) — `useScrollDirection`, `useMediaQuery`, `useCountUp`, `useInView`,
  `useNoctraEvent`, `useHotkey`, `useLocalStorage`; barrel `hooks/index.ts`.
- `lib/events.ts` (new) — namespaced action/filter event bus (WP-hook analog).

**Components**
- `components/ui/SectionLabel.tsx` — overline eyebrow (WP/SaaS hero pattern).
- `components/ui/TrustPill.tsx` — trust/proof chip (trust-signal pattern).
- `components/landing/*` — LandingNav, LandingHero (product preview built in CSS, not
  stock art), TrustBar, FeatureGrid, HowItWorks, CasePreviewCard (night canvas), FinalCTA,
  LandingFooter.
- `components/storefront/PendingDecisionsDrawer.tsx` — slide-out drawer, live pending list,
  approve/decline shortcut, honest empty state.
- `Navbar` — added primary "Review decision" action + drawer trigger with count pill
  (mini-cart pattern); open-state via the event bus (`noctra:open-pending-drawer`).
- `DashboardLayout` — mounts the drawer; keeps density + mobile nav.

**Pages**
- `features/landing/pages/LandingPage.tsx` — full rewrite: WordPress-grade marketing flow
  (hero → trust bar → product preview → features bento → how-it-works → proof → final CTA →
  multi-column footer). Every claim remains real; no fabricated metrics.

**Wireframes**
- `docs/ui-concepts/new/` — 4 new concept boards (landing hero, inbox with drawer, case
  workspace, mobile) generated from the research synthesis.
- `docs/ui-concepts/reference/` — saved web references (award-winning WordPress sites,
  WooCommerce storefronts) used for direction.

## 5. Anti-patterns we deliberately did NOT copy

- No carousels/sliders of fabricated content; no fake logos/testimonials.
- No "cyber" styling: NOCTRA stays editorial/calm per brand spec §9 avoid-list.
- No neon/glow/gradient noise; the one gradient is the exact brand violet
  `#6C5CE7 → #9D7CFF` used on the logo, hero accent and primary actions only.
- No color-only severity: dot + label retained everywhere.
- No invented metrics anywhere (WordPress proof is real or absent).
