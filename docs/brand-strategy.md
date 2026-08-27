# Brand & UI/UX Strategy — NOCTRA

> **⚠ Superseded (Phase 20):** the product now ships as **AXIOM AI** — see the
> current brand specification in [`brand-identity-axiom.md`](brand-identity-axiom.md)
> and `dashboard/src/constants/brand.ts`. This document is retained as the
> historical Phase 1–3 naming decision record.

Condensed deliverable for **Phase 1–3** of the rebrand. Full commit diff carries the implementation; this doc is the decision record.

## 1. Brand Identity & Naming (research-driven)

### Naming trends surveyed (2026)

- **YC 2025 vogue shift:** serious/competent animal names (Kestrel, Bear, Lark) over derpy -y/-ly coinages; harder coinages ending in *A* (Panta, Zarna) or consonant (Tornyol, Lexius); short invented 5–7-char pronounceable (Vercel, Resend) dominates over descriptive *FlowHub* compounds. Plosive K/T/P/B/G drives recall (Stripe, Slack, Figma). `— Heirloom/Elliott Verbal Brand Names Report 2026`
- **Cybersecurity naming crisis:** saturated templates *Flowly/Fluxo/Synthara/Cogniverse* and physics clichés *Quantum/Vector/Fusion* blur; `AI` suffix now dates the brand like `.com` in 2001; concept names beat category names (Stripe ≠ payments). `— Spellbrand B2B Naming Crisis 2026`
- **RSA 2025 best-name filter:** easy to say → easy to remember → easy to type → short → ownable handle. `— Cybersecurity Ventures RSA 2025` + `Adfirm 2026` 5-filter (phonetic, domain, trademark, search, connotation) where ~200 candidates yield only 5–20 viable.
- **Corelight case:** compound illumination story (Core + Light) bridges technical + executive audiences. Portfolio rebrand wants the same: one story that translates to both analyst and board. `— Heirloom Corelight`

### Shortlist (passes 5-filter; invented or recontextualised; no AI suffix; 5–6 letters)

| # | Name | Etymology / story | Syll. | Trade note | Tagline |
|---|------|-------------------|-------|------------|---------|
| **1** | **NOCTRA** ★ | *nocturnal* sentinel — built for the night shift (dark-native SOC) | 2 NOK-tra | Invented, low SaaS collision; `noctra.ai/.io` pattern ownable; ends *A* (2026 coinage trend), plosive K/T | **Silent. Precise. Always watching.** |
| 2 | KESTRA | kestrel (hover-watch → strike) + orchestra (SOAR playbooks) | 2 KES-tra | Distinct from MS Kestrel (infra); ends *A*; hover precision metaphor | Hover. See. Orchestrate. |
| 3 | VIGLA | *vigilance* compressed, 5 letters | 2 VIG-la | Ultra-short, ends *A*; close to *vigil* for intuition | Vigilance, distilled. |
| 4 | OBSKRA | *camera obscura* — dark chamber that reveals the image | 2 OB-skra | Hard SK/B, invented, strong recall | Reveal what hides. |
| 5 | CORVEX | *corvus* (raven intelligence) + *vex* (vex adversaries) | 2 COR-vex | Ends consonant X (assertive, techy), low collision | Intelligence that vexes adversaries. |

Runner-up from prior round **STRIX** (owl genus) kept as reserve alias; **AEGIS/ARGUS** dropped — strong but crowded marks in security class.

**Recommended: NOCTRA.** Highest distinctiveness, owns the dark-mode narrative, shortest learning curve, passes phonetic handle test, leaves headroom for adjacent products (NOCTRA Graph, NOCTRA Playbooks). One-line swap via `dashboard/src/constants/brand.ts` → `BRAND_NAME` to rotate to KESTRA etc.

### Tagline & positioning

- **Tagline:** *Silent. Precise. Always watching.*
- **Positioning (value prop):** *The AI analyst that never blinks — detects across logs, email and network, explains every verdict, and orchestrates response.* One job per screen, evidence beside the alert, severity readable in one pass at 3 a.m.
- **Domain hint:** `noctra.ai` (AI-native) or `noctra.sh` (operator tool) — five-letter `.com` extinct in 2026; compound `.ai/.io` is acceptable for B2B/SaaS per Adfirm guidance.

### Logo & visual language

- **Mark:** geometric owl-eye / radar sweep. Diamond shield outer (`#f59e0b` amber @ 8% fill) + inner offset eye (dual arc) + 90° radar sweep negative + pupil. Sage depth ring (`#84a98c` dashed) for AI dimension. Pure SVG, no assets; crisp 16px favicon → 36px login.
- **Wordmark:** `NOCTRA` tracked `0.14em`, all-caps, Sora Variable Bold (display); sub-line `THREAT OPS` `0.18em` / `content-tertiary`. Favicons variant: mark only.
- **Design system (Tailwind v3 — no full v4 migration per scope):**
  - **Palette — "Obsidian Ember" (v3 hex, perceptually tuned; evolved from the launch cyan/violet in Phase 17):** `app-bg #0a0a0f`, `app-void #050508`, `app-surface #14141f`, `app-surface-raised #1e1e2b`, `app-subtle #23232f`; **brand** `amber #f59e0b` (warm ember accent) + `sage #84a98c` (muted secondary) + `clay #c9ada7`; `content-primary #f1f5f9` / `secondary #a1a1aa` / `tertiary #71717a`; **semantic** `success #84a98c` (sage, CVD distinct), `warning #f4a261` (soft orange), `critical #e76f51` (terracotta) — paired always with dot+label+icon (WCAG 1.4.1); `chart-1 #f59e0b` (amber) / `chart-2 #84a98c` (sage) / `chart-3 #e76f51` (terracotta) / `chart-4 #e9c46a` (gold) / `chart-5 #c9ada7` (clay).
  - **Typography:** Inter Variable (sans, UI) + Sora Variable (display, headings/wordmark) + JetBrains Mono Variable (mono, logs/hashes/IPs). Scale `xxs 0.6875rem` → `2xl`, tight tracking on wordmark, relaxed on body.
  - **Spacing/shape/shadow:** 4px base; radii `xxs 4px` → `xl 12px` → `2xl`; shadows `card / raised / overlay`; brand glows `accent-glow rgba(245,158,11,.35)` + `sage-glow`.
  - **Motion:** `fade-in 160ms`, `fade-up 240ms`, `scale-in 140ms`, `slide-in-right 200ms`; respects `prefers-reduced-motion`. No decorative springs.

---

## 2. UI/UX Research & Benchmark Brief

### Benchmarks (same niche)

1. **CrowdStrike Falcon (Charlotte AI)** — persona-aware, unified asset/risk, AI-generated dashboards from natural-language prompts; fragmentation → clarity. Lesson: persona workspaces + progressive disclosure beat dense metric walls.
2. **Splunk SOC guidance** — “design around the question, not the data”; lead with judgment (severity) then supporting detail; drill-downs do the navigating; resist `just one more panel`. Human-centered audit: 46% of analysts spend more time maintaining tools than defending.
3. **Fuselab SOC UX** — triage queue first; severity cannot be color alone (1-in-8 men CVD, dim night-shift); design at peak volume (4k alerts) not empty state; role-based default views are permissions decisions.
4. **Detectify a11y rebuild (Tailwind + Radix/Shadcn)** — WCAG AA contrast, CVD-safe hues (blue-green vs saturated orange vs red), high-contrast borders + distinct iconography + semantic hierarchy per severity. One alert variant per semantic value.
5. **Cherenkov / Infisical dark-native systems** — cyan-core `#00e0ff` + violet-core funnels, deep indigo voids, border-defined depth not shadows, Inter-only. Dashboard 2026 trend: indigo/cyan piercing on void conveys authority.

### Friction points found across category

- Alert fatigue from timestamp-sorted queues hiding the real detection; silent re-sort losing the analyst’s place; color-only severity failing CVD/ tired eyes; `TTID`/`explain` evidence three clicks away; context-switching between consoles (Intel, SOAR, SIEM) per alert.

### UX patterns adopted for NOCTRA

- **Zero-latency feedback:** optimistic skeletons (`SkeletonTable` matching columns), inline toasts, `active:scale-[0.98]` + focus-visible rings.
- **Progressive disclosure:** summary KPIs → prioritized queue (severity-ranked) → evidence drawer/modal with MITRE + threat-intel + explainability panels.
- **Multi-modal severity:** dot + pill + label (never color alone), high-contrast borders, icon per level.
- **IA:** orient → prioritize → investigate (top KPIs → alert table → detail context).
- **Onboarding:** email+password with analyst role defaults, success toast, remember `density` (comfortable/compact) per user.

### Component architecture

Reusable `components/ui` kit: `Button` (CVA, primary gradient amber→sage), `Card`/`CardHeader`, `Badge`/`SeverityBadge`/`StatusBadge`, `Skeleton*`, `EmptyState`, `Modal`, `Select`, `PageHeader` (brand accent bar), `Breadcrumbs`/`BackButton`, `BrandLogo`. All token-driven (`bg-app-surface`, `border-line-subtle`, `text-accent-primary`); no hardcoded hex in pages. Background glow in `globals.css` via fixed radial gradients (amber 7% + sage 6%).

---

## 3. Frontend Implementation Plan & Execution

- **Stack alignment:** React 18 + TS 4.9 + Vite + Tailwind v3.4 + CVA/tailwind-merge + lucide + recharts already in place. Kept v3 (per clarification) — creative palette only. Added `@fontsource-variable/inter` + `jetbrains-mono` already present; `framer-motion` deferred (CSS keyframes cover 90% of motion needs; add later for route transitions if desired).
- **Responsive/layout:** mobile-first shell: collapsible sidebar (`w-64` ↔ `w-[68px]`, icon-only), sticky top `Navbar` with search + LIVE STREAM, density toggle (`Rows3`) persisted to `localStorage`. `main` is `overflow-y-auto` + `animate-fade-up`. Tables wrap in `overflow-x-auto`; cards stack via `grid`/`space-y`.
- **States:** loading skeletons, empty states, error banners (`status-critical/10` + border), disabled opacity + `cursor-not-allowed`, toasts, confirm dialogs. `prefers-reduced-motion` disables animation.
- **Code quality:** `brand.ts` single-source; `BrandLogo` pure SVG; Tailwind `cn()` via `clsx`+`twMerge`; CVA variants; no new deps. `tsc --noEmit && vite build` passes (2635 modules, ~69 kB gzipped UI chunk).

### File map (delta in this pass)

- `dashboard/tailwind.config.js` — brand/void/chart tokens, violet secondary, refined semantic colors, violet-glow.
- `dashboard/src/constants/brand.ts` — name/tagline/palette/shortlist.
- `dashboard/src/components/BrandLogo.tsx` — SVG mark + wordmark.
- `dashboard/public/favicon.svg` + `dashboard/index.html` — title `NOCTRA — Threat Ops`, OG/theme meta.
- `dashboard/src/styles/globals.css` — indigo/cyan void glows, focus ring, reduced-motion.
- `dashboard/src/components/ui/Button.tsx` — gradient primary, refined variants.
- `dashboard/src/components/ui/Card.tsx` — hover `border-accent-primary/20` + `shadow-raised`.
- `dashboard/src/components/ui/PageHeader.tsx` — brand accent bar.
- `dashboard/src/layouts/DashboardLayout/index.tsx` + `components/Navbar/index.tsx` — `BrandLogo` wordmark.
- `dashboard/src/features/auth/pages/Login.tsx` / `Register.tsx` — brand header, gradient CTA.

Rename is one token: change `BRAND_NAME` in `brand.ts` + `index.html` title if rotating to KESTRA.
