# Session Log

Phase-by-phase record of how this project was built and hardened. Each phase maps to
commits on `main` and, where applicable, to requirement IDs tracked in the
[traceability matrix](traceability-matrix.md).

## Phase 1 — Foundation (auth, API keys, permissions)

- Initial clean commit + training logic.
- API-key authentication, user registration, permission management
  (`43bb648`) — the ABAC permission catalog that everything else gates on.
- Project structure added to README (`62d646c`).

## Phase 2 — v3 restructure: multi-tenant, event-driven SOC

- Reworked the service into a multi-tenant, event-driven SOC platform
  (`f3c1d6a`): `org_id` tenancy, Kafka event chain, engine / cases /
  alert services.

## Phase 3 — SOC dashboard + ML retrain pipeline

- SOC dashboard pages, ML retrain pipeline (`POST /retrain` hot-swap), and
  E2E org-scoping fix (`a3e3ed3`).

## Phase 4 — Landing page, shared UI library

- SOC overview landing page, shared React component library, page-state
  polish (`9a70fdf`).

## Phase 5 — Admin cross-tenant views + ABAC role screens

- Admin cross-tenant views (FR-TENANT-06) and ABAC roles screen
  (FR-UI-06) (`deb9d5b`).
- Fixed `/me` to return permissions so admin routes aren't gated to the
  alerts page (`2945088`).
- Admin detection-rules and IP-reputation screens (FR-UI-05) (`da26042`).

## Phase 6 — Correctness fixes

- MITRE int-port + substring false-match fix, Kafka integration key fix,
  hermetic test engine (`b35ddfe`).

## Phase 7 — Container/rollout hardening

- Containerized dashboard + in-cluster Postgres; live `kind` rollout
  verified (NFR-PORT) (`b9d7110`).
- Removed dead modules, broke the ABAC-auth import cycle, unified the
  user-admin API (`3e4eede`).
- 1 GB-budget Docker Compose for the full app + stack README, tooling
  fixes (`2836db5`); gitignored stray dev db (`663ba29`).
- Fixed Docker login: `COOKIE_AUTH=true` so dashboard login cookies are set
  (`7e913b7`) — closed a stale-Vite/`COOKIE_AUTH=false` login failure.

## Phase 8 — Production hardening

- TLS at gateway: ingress-nginx + cert-manager issuers (NFR-SEC-10)
  (`7a3f010`).
- Load/performance baseline: k6 + Locust suites (NFR-PERF-01..05)
  (`009237b`).
- Managed-Postgres swap guide for production (NFR-PORT) (`d1c627f`);
  `loadtest/` listed in project structure (`503e378`).

## Phase 9 — UI shell polish

- Scrollable sidebar, breadcrumbs + back nav, Inter + JetBrains Mono fonts,
  WCAG contrast fix, density toggle, route motion, tooltips
  (`4621fba`).

## Phase 10 — Documentation sync

- `docs/`/`diagrams/` were briefly untracked then re-tracked so
  requirements, traceability matrix, and ML-pipeline docs live in git
  (`d5fe608`, `8dfd4b8`, `7851fe7`, `432ad50`, `e1755e4`).
- `docs/session-log.md` (this file) written.

## Phase 11 — Enhancement pass (CI + analyst tooling)

- CI enforcement: `.github/workflows/ci.yml` with backend pytest, ml-service
  pytest, dashboard typecheck+build, and k8s manifest validation via
  kubeconform (catches broken charts on every push) (`bc41f47`).
- Dashboard CI badge in README (`2eb0ddd`).
- SOAR playbooks: explicit rule->action overrides with full CRUD API +
  dashboard manager; inactive playbooks fall back to heuristics
  (`71d15bc`).
- ML explainability: dependency-free `/explain/*` endpoints surfacing
  coefficient/keyword/centroid/rule evidence for every model family
  (`6a1f608`).
- Model benchmark harness: `GET /benchmark` evaluating deployed artifacts
  against holdout sets; observed network outlier rate tracked against expected
  contamination (`b13a730`).
- Entity-graph enhancements: `GET /entities/summary` (aggregate metrics + hubs)
  and `GET /entities/path` (BFS shortest path between indicators)
  (`d1374ab`).

## Phase 12 — Model bake-in + deployable artifacts

- ml-service Dockerfile now runs `python train.py` at build time, baking the
  log/email classifiers into the image (`a8c3ab8`); the gitignored `model/`
  `COPY` that broke fresh clones was removed. `train.py` gained a
  `--require-network` flag (default off) so the network model is skipped
  gracefully when CICIDS2017 isn't in the build context.
- k8s manifests + READMEs aligned: `ml-service.yaml`, `training.yaml`,
  `k8s/README.md`, `README.md`, `ml-service/README.md` now document the
  self-contained image and the network-model opt-in (`9daf5e0`).
- Bugfix: playbook manager fetched rules with `limit=200`, but the backend
  caps rules at 100 → 422 → `Promise.all` rejected and the playbook list /
  rule selector stayed empty (`01740a4`).

## Phase 13 — Telemetry + load-test CI

- Dashboard client errors are reported to the backend via
  `POST /api/v1/telemetry/client-error` and land in the append-only audit
  trail as `CLIENT_ERROR` entries (any authenticated subject, no permission
  gate) (`7c7ad80`).
- The `loadtest` job in CI boots the compose stack (postgres + backend +
  ml-service), installs k6, and runs the NFR-PERF suite (`threat-ai.js`) with
  `CI=true`: strict p95 latency gates are relaxed (dev-size compose `cpus`
  limits are unreliable on shared runners) and the job instead gates on
  failure rate < 1% per endpoint while recording latencies as a baseline
  (`eb06275`).
- k6 script made CI-runnable: no object spread / `URLSearchParams`, and the
  analysed mix scales down to a smoke level in CI mode so the background-scan
  fan-out doesn't saturate CPU-capped containers (`0d028d5`, `cef765c`).
- ml-service Locust suite extended to cover `/explain/log` and `/benchmark`
  alongside `/predict/log`; spot-check baseline noted in `loadtest/README.md`
  (`229193b`).
- Docker fix: Kafka listens dual-protocol so the backend publishes in-network
  (`kafka:9092`) while host tooling uses `29092`; `ENABLE_KAFKA` is
  overridable in compose (`326e556`).

## Phase 14 — Brand identity NOCTRA

- Research-driven rebrand to **NOCTRA** (`noctra.ai`) — 6-char, 2-syllable, hard invented + nocturnal totem, abstract to grow (Stripe/Notion pattern). Shortlist refined per 2026 naming analysis: KESTRA / ORVEX / STRYX / KORVA on hard K/T/P/V/X register; NOCTRA kept per decision (`2fb879d`). Full strategy in `docs/brand-strategy.md`.
- Premium dark-native design system: Tailwind v3 tokens only (no v4 migration) — `app-void #060a14`, brand `cyan #00e0ff` + `violet #7c3aed`, CVD-safe semantics (`#10b981`/`#f59e0b`/`#ef4444` + dot+label), Inter + JetBrains Mono, void glows, `violet-glow` shadow. `tailwind.config.js:10`.
- Logo: geometric owl-eye / radar sweep diamond (SVG, no assets) + `THREAT OPS` wordmark; favicon `public/favicon.svg`; `index.html` OG/theme meta to `NOCTRA — Threat Ops`.
- Shell polish: `BrandLogo` wordmark in sidebar + navbar (`DashboardLayout/index.tsx:128`, `Navbar/index.tsx:39`), `Button` gradient primary cyan→violet, `Card` hover brand border, `PageHeader` accent bar, auth pages brand header. `tsc --noEmit && vite build` passes.

## Phase 15 — Motion + landing + token alignment

- Token alignment across analytics/entities: `SEVERITY_COLORS` and chart strokes unified to NOCTRA tokens (`#ef4444`/`#f97316`/`#f59e0b`/`#10b981`, `#00e0ff`) in `AIAnalyticsPage.tsx:33`, `EntitiesPage.tsx:278`, `EntityGraphView.tsx`; `DashboardOverviewPage.tsx:199` tooltip/gradient to `#141e32`/`#00e0ff`; `AlertList.tsx:89` search responsive.
- Motion: `framer-motion` `PageTransition` (`components/PageTransition.tsx:1`, 220ms `easeOut`) wrapping `DashboardLayout` outlet; respects `prefers-reduced-motion`.
- Landing: public `/welcome` `LandingPage.tsx:1` (NOCTRA hero, 4-feature grid, CTA → `/register`/`/login`); `App.tsx:29,66` route added; `README.md:1` brand header + design-system note.

## Phase 16 — Docker build fix + live NOCTRA verification

- `dashboard/.dockerignore` added (`369c169`): `node_modules`/`build` ignored → context 157 MB → 6.70 kB, build 138s → 74s; `docker-dashboard` rebuilt and `LandingPage 4.61 kB` verified via `curl :3000` → `NOCTRA — Threat Ops`; `/welcome` landing live. `docker compose ps` shows `backend`/`ml`/`postgres` healthy, `dashboard` up.
- Live smoke after compose up: `POST /api/v1/register` `smoke_3704` → `POST /api/v1/login` (form `username`+`password`) → `POST /api/v1/analyze` `Failed password…` → `severity=LOW fallback=False` (baked `log_model`).

## Phase 17 — Obsidian Ember palette + Sora display font

- Palette pivot from the launch cyan/violet ("void") theme to **Obsidian Ember**:
  warm `amber #f59e0b` + `sage #84a98c` + `clay #c9ada7` on near-black `app-bg
  #0a0a0f` / `app-void #050508`. Every Tailwind token in `tailwind.config.js`
  (`accent-*`, `status-*`, `chart-1..5`, `app-*`, `content-*`, `line-*`) and
  `BRAND_PALETTE` in `constants/brand.ts` remapped; `accent-glow`/`sage-glow`
  shadows, `favicon.svg`, `BrandLogo` (amber mark + sage ring), `index.html`
  `theme-color`, and `globals.css` radial glows + scrollbar recolored.
- Added `Sora Variable` as the `display` font (headings + wordmark) alongside
  Inter (UI) and JetBrains Mono (mono): dep + `index.tsx` import, `fontFamily.display`
  in `tailwind.config.js`, applied via `font-display` on `PageHeader`, `BrandLogo`,
  the `LandingPage` hero, and the SOC Overview title.
- Finished the migration the initial pass had skipped: converted ~43 raw Tailwind
  color utilities (`bg-emerald-500`, `bg-blue-500`, `bg-orange-500`, `text-red-400`,
  …) to semantic tokens across 18 files — `SoarPage`, `IncidentsPage`,
  `AlertDetailModal`, admin `Rules`/`Reputation`/`SystemLogs`/`EngineSettings`,
  shared `Badge`/`Select`/`TextInput`/`TableWithAction`/`Navbar`, and the auth
  `ResetPassword`/`Login` + entity error states — so every surface renders through
  the token system. Severity ramp unified to
  `status-critical`/`status-warning`/`chart-4`/`status-success`; the solid
  batch-delete button dropped white-on-terracotta (failed WCAG AA) for the app's
  tinted `danger` convention. Only the deliberate `text-red-300` danger-button text
  is left raw.
- `tsc --noEmit && vite build` passes (built ~23s; CSS 37.6 kB incl. Sora).

## Phase 18 — Autonomous analyst: credential-leak case loop

- **Product reframe** (owner decision 2026-08-21): NOCTRA
  shifts from a generic multi-tenant SOC *cockpit* to **an autonomous AI security
  analyst for small companies** — "you employ an analyst, you don't operate a
  dashboard." Phase 18 builds the product loop as a **thin, non-breaking vertical
  slice** for one scenario (credential leak): **sense → LLM reasons → plain-English
  Case with blast radius → drafts a reversible action → human approves → recorded +
  auto report.** Reuses the existing engine (entity graph, SOAR, append-only audit,
  multi-tenancy) rather than rebuilding; every legacy page stays reachable as the
  optional "deep dive."
- **Additive, non-breaking schema**: reuse the `cases` table — the "feed of
  decisions" *is* cases, reframed. New nullable columns on `models/case.py`
  (`kind`, `analysis`, `blast_radius`, `proposed_action`, `decision`,
  `decided_by_id`, `decided_at`, `soar_action_id`, `report`) + idempotent
  `ALTER TABLE cases ADD COLUMN IF NOT EXISTS …` in `core/migrations.py`;
  `create_all` builds them on fresh DBs. `case_service.serialize_case` extended —
  extra keys are safe for the existing Incidents page, which renders unchanged.
- **Sense** — `services/scenario.py` `run_credential_leak`: inserts a CRITICAL
  `credential_leak` `SecurityAlert` (MITRE **T1078**), builds a deterministic blast
  radius via `entity_graph.upsert_entity`/`link_entities`
  (`email:jdoe@acme.com` —derives_from→ `account:jdoe` —communicates→ `finance-db`
  / attacker `ip`), drafts `REVOKE_CREDENTIALS`, and opens a `kind='analyst'`
  pending case with `ANALYST_CASE_OPENED` audited.
- **Reason (graceful)** — `services/llm_client.py` `analyze_incident`: synchronous
  `requests` to the Anthropic Messages API mirroring `ml_client._post_with_retry`
  (retry/backoff + `x-api-key`/`anthropic-version` headers); returns the analysis
  JSON contract (`headline`, `what_happened`, `why_it_matters`,
  `blast_radius_summary`, `recommended_action{action_type,target,rationale,undo}`,
  `confidence`, `model`, `fallback`). With no `ANTHROPIC_API_KEY` (or
  `LLM_ENABLED=False`) or on any error/parse failure it returns a deterministic
  templated `fallback_analyze` (`fallback:true`) — **never raises**, so the demo is
  meaningful with no key and richer with one. New `config.py` settings
  `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL="claude-sonnet-5"`/`ANTHROPIC_BASE_URL`/
  `LLM_ENABLED`/`LLM_TIMEOUT`/`LLM_MAX_TOKENS`.
- **Decide + reverse + report** — `services/analyst_service.py` drives the reads
  (`brief`, `feed`, `get_case`) and the human transitions: `approve` runs the
  drafted action through the existing **record-only** `soar.execute_action` (records
  a `SoarAction`, stores `soar_action_id`), `revert` records a compensating
  `ALERT_OPERATOR` entry carrying the `undo` text, `decline` closes with no system
  change. Each transition stamps `decided_by/at`, generates a markdown report via
  `services/report.py` `build_case_report` (summary, blast-radius table, decision,
  action + undo, audit refs), and writes
  `ANALYST_CASE_{APPROVED,DECLINED,REVERTED}` to the append-only log.
- **Endpoints** — `api/v1/endpoints/analyst.py` (`prefix=/analyst`, registered in
  `router.py`): `POST /simulate`, `GET /brief`, `GET /feed`, `GET /cases/{id}`,
  `POST /cases/{id}/{approve,decline,revert}`, `GET /cases/{id}/report`. Reads use
  `get_current_user`, writes reuse `require_permission("alerts:write")` (**no new
  perms**), all org-scoped with the standard `{data,total,page,limit}` envelope.
- **Calm surfaces** (semantic tokens only, `space-y-6 animate-fade-in`;
  `api/analystApi.ts` + `types/analyst.ts`): `pages/BriefPage.tsx` — post-login home
  ("Here's where things stand", StatCards Needs-your-decision / Handled-today /
  Assets-watched, a "What needs you" list, and a primary **Simulate incident**);
  `pages/FeedPage.tsx` — decisions table (headline, severity, decision pill, opened)
  cloned from `IncidentsPage`; `pages/CasePage.tsx` — Explanation (what/why),
  Blast radius (entities + relations), Recommended action (reversible `undo` note +
  model/fallback + confidence), and a Decision gate driving `ConfirmDialog`
  approve/decline/revert with a "View report" reveal. `App.tsx` makes **Brief the
  index** and adds `feed` + `case/:id`; Overview kept at `/dashboard` (deep dive);
  `DashboardLayout` gains Brief/Feed/Overview nav. `.claude/launch.json` added for
  the `noctra-dashboard` dev preview.

## Phase 19 — Multi-Scenario Analyst, Interactive Ask-NOCTRA Chat & Security Connectors

- **Client App Fix**: Repaired Next.js client (`client/`) build failures by supplying missing UI components (`Button`, `Input`, `Card`, `Alert`, `Skeleton`), auth store, API client, and layout suspense boundaries. `cd client && npm run build` now builds cleanly alongside `dashboard`.
- **Multi-Scenario Simulation**: Expanded `services/scenario.py` with 4 scenario generators (`credential_leak` T1078, `phishing_outbreak` T1566, `data_exfiltration` T1048, `compromised_api_key` T1098). Supported via `POST /api/v1/analyst/simulate?scenario_type=...` and dropdown selector on `BriefPage.tsx`.
- **Ask-NOCTRA Interactive AI Analyst Chat**: Added `POST /api/v1/analyst/cases/{id}/chat` endpoint and `analyst_service.chat_about_case`, providing context-aware answers regarding blast radius, MITRE techniques, and remediation details. Audits every query as `ANALYST_CHAT_QUESTION`. Surfaced on `CasePage.tsx` via an interactive chat widget.
- **Connected Security Tooling (Connectors)**: Added `GET /api/v1/analyst/connectors` and `POST /api/v1/analyst/connectors/{id}/sync` exposing real-time status for integrated security tools (Okta, Sentinel EDR, AWS GuardDuty, Cloudflare Edge WAF). Surfaced in `BriefPage.tsx` with on-demand sync triggers.
- **Verification**: `113 passed, 2 skipped` in `backend` pytest; `13 passed` in `ml-service` pytest; `dashboard` Vite build (1.2s) and `client` Next.js build pass cleanly with 0 errors.

## Phase 20 — AXIOM AI Brand Identity & Clean Architecture

- **AXIOM AI Brand Identity & Specifications**: Rebranded the entire application across frontend, backend, prompts, reports, and documentation to **AXIOM AI** (*"Self-evident threat reasoning. Instant containment."*). Formulated formal brand specification in [`docs/brand-identity-axiom.md`](docs/brand-identity-axiom.md) and visual brand poster graphic in [`docs/brand-identity-axiom.png`](docs/brand-identity-axiom.png).
- **Codebase Clean-Up**: Removed unused Next.js prototype directory (`client/`), consolidating all frontend development onto single production React + Vite application (`dashboard/`).
- **3-Column Bento Box Layout**: Refactored `BriefPage.tsx` into a 3-column Bento box layout (White Posture Score card `96/100`, Midnight Navy `#0e1320` incident story card with blast-radius chips and `#2563eb` primary action, live operational status feed).
- **Ask-AXIOM AI Copilot Chat**: Refactored `CasePage.tsx` with interactive Ask-AXIOM AI copilot chat widget, blast-radius graph node mapping, and reversible action approval gates.
- **Full Stack Verification**: `113 passed, 2 skipped` in `backend` Pytest, `13 passed` in `ml-service` Pytest, `dashboard` Vite build 100% success (`built in 1.10s`), and live background server processes running on ports `3000` (Dashboard) and `8000` (Backend API).

## Status

- All 67 FRs implemented and verified (backend `pytest`, `tsc` + `vite build`, Docker E2E smoke, live `kind` rollout).
- Rebranding and single-frontend cleanup complete: `dashboard/` is the single source of truth for AXIOM AI.
- Full test suite passing across backend (113 passed), ml-service (13 passed), and dashboard build (1.10s).


## Phase 21 — Commercial-Grade Frontend Redesign (WordPress/WooCommerce research)

- **Research** — web-researched how the best WordPress and WooCommerce implementations
  are built: block-theme `theme.json` design tokens (declarative settings → CSS variables,
  style variations, fluid typography), the hooks system (actions `do_action` / filters
  `apply_filters` with priority + namespacing), and the storefront conversion playbook
  (sticky header + single primary CTA, mini-cart slide-out drawer with live count pill,
  product-grid card discipline, trust signals, distraction-free checkout, honest empty
  states). Also researched enterprise SaaS typography rules (Major Second 1.125 scale,
  sans UI + mono data pairing, ≥4.5:1 contrast) and security-SaaS dashboard patterns.
  Findings + WP→NOCTRA mapping documented in
  [`docs/frontend-commercial-redesign.md`](frontend-commercial-redesign.md).
- **Token system (WP `theme.json` analog)** — extended `constants/brand.ts` (single source
  of truth): `BRAND_GRADIENT` (exact logo violet `#6C5CE7→#9D7CFF`), `BRAND_TYPE_SCALE`
  (fluid clamp() display + ui scales), `BRAND_RADII`, `BRAND_SHADOWS` (added float/hero),
  `BRAND_BREAKPOINTS`, `BRAND_Z_INDEX`, `BRAND_TRUST_POINTS` (real, verifiable claims).
  `tailwind.config.js` gained `backgroundImage.brand-gradient*`, `text-display-2xl…sm`
  fluid scale, `shadow-float/hero`. `styles/globals.css` gained scrollbar-none + smooth
  anchor scrolling.
- **Hooks library (WP hooks analog)** — new `dashboard/src/hooks/`: `useScrollDirection`
  (sticky-header hide-on-scroll), `useMediaQuery`/`useIsDesktop`/`useIsMobile`,
  `useCountUp` (reduced-motion safe), `useInView` (IntersectionObserver reveal),
  `useNoctraEvent`, `useHotkey` (mod+k/escape), `useLocalStorage`; barrel export.
  New `lib/events.ts` — namespaced, priority-ordered action/filter bus mirroring
  `do_action`/`apply_filters` (`EVENTS.COMMAND_MENU`, `OPEN_PENDING_DRAWER`, …).
- **Components (block-pattern analog)** — `components/ui/` added `SectionLabel` (overline
  eyebrow) + `TrustPill` (trust-signal chip). New `components/landing/`: `LandingNav`
  (sticky, hide-on-scroll, gradient CTA), `LandingHero` (product preview built in CSS —
  a real NOCTRA case card, labeled illustrative; no stock art), `TrustBar` (real test
  numbers 114/13 + connectors + run modes with count-up), `FeatureGrid` (6 real features,
  each linked to its live route), `HowItWorks` (8-step analyst loop), `FinalCTA` (gradient
  band + multi-column footer). New `components/storefront/PendingDecisionsDrawer.tsx` —
  the WooCommerce mini-cart pattern: slide-out drawer of pending cases, severity dots,
  time-ago, "Review & decide" CTA, honest empty state, event-bus refresh, body scroll
  lock, Escape close.
- **Shell upgrade** — `Navbar` gained the mini-cart trigger: a "Review decisions"
  gradient button with live pending-count pill (icon-only + count on mobile) that opens
  the drawer via the event bus; count stays in sync through `EVENTS.PENDING_CHANGED`
  (also emitted by the drawer after fetch). `DashboardLayout` mounts the drawer once.
- **Landing rewrite** — `LandingPage.tsx` completely rebuilt as the WordPress-grade
  marketing flow: nav → hero → trust bar → features → how-it-works → final CTA →
  footer. Every number is real (test suites, connectors, run modes); no fabricated
  metrics, no fake testimonials; one gradient (the exact brand violet) used only on
  primary actions and the hero accent.
- **Verification** — `tsc --noEmit && vite build` clean (~1.4s). Live preview: Vite on
  port 3000 (proxies `/api` → FastAPI on 8000, SQLite `noctra_preview.db`); demo user
  `demo` / `DemoPass123!` with one simulated CRITICAL case in the pending drawer.
- **Wireframes** — 4 new concept boards in `docs/ui-concepts/new/` (landing hero,
  inbox + drawer, case workspace, mobile); 8 web references archived in
  `docs/ui-concepts/reference/`.

## Phase 22 — Light/Dark Mode Toggle + L rollout to every remaining file

- **Theme system** — `theme/ThemeProvider.tsx`: whole-app light/dark. Persists
  `td_theme` in localStorage, falls back to OS `prefers-color-scheme`, listens for
  OS changes until an explicit choice. `html.dark` flips every semantic token in
  `globals.css` (same ink family as the night canvas); body background synced so
  overscroll never flashes. `components/ThemeToggle.tsx` (sun/moon pill) mounted in
  the Navbar and the landing nav.
- **Token sweep** — converted every remaining hard-coded light class to semantic
  tokens so dark mode flips the whole app: Card, PageHeader, Button (secondary/ghost),
  Modal, Toast, CommandMenu, Term tooltip, Navbar, DashboardLayout sidebar, Pending
  Decisions Drawer, all landing components (nav/hero/trust/features/how-it-works/
  footer), Login/Register. Grep audit: 0 hard-coded `bg-white`/`text-neutral-*/`
  `border-black/*` left outside intentional night panels.
- **Night canvas framing** — the dark product card on the landing now carries the
  caption "The night canvas — NOCTRA's dark workspace", making the light/dark
  duality explicit (owner direction: the dark card is fine as long as it represents
  light/dark mode). `.night` analyst panels stay dark in both themes by design.
- **Verification** — `tsc --noEmit && vite build` clean (~1.5s); all new modules
  serve 200 in the live preview.

## Phase 23 — Crescent-moon brand mark, L auth pages, skeleton layout repair

- **Brand mark → crescent moon** — owner confirmed the mark in the direction-L
  design is a **crescented moon**, not the interim folded-ribbon N. Rewrote
  `components/BrandLogo.tsx`: full disc r=12 @ (16,16) with a bite disc r=9 @
  (21,11) removed via mask (exact crescent, no hand-drawn arcs), diagonal
  `#6C5CE7→#9D7CFF` gradient, `#B18CFF` sparkle at the upper tip; wordmark +
  sparkle-A + tagline unchanged; `useId` so multiple instances never collide.
  Favicon `public/favicon.svg` and the brand spec (`docs/noctra-redesign-spec.md`
  §12–13) updated to the crescent.
- **Auth pages completed in the new design** — new `features/auth/components/
  AuthLayout.tsx`: split screen (brand panel with crescent mark, mono overline,
  display headline with gradient phrase, three product truths; form card on the
  light canvas) + ThemeToggle top-right. Login and Register rebuilt on it;
  ResetPassword rebuilt as a matching card (crescent mark, gradient pill,
  invalid-token state with back-to-sign-in); ForgotPassword modal aligned
  (rounded-3xl, crescent mark, "Night desk access" overline, accessible close).
  Login card carries the demo workspace hint.
- **Skeleton layout repair** — skeletons were replacing whole pages (spinner
  where a header+cards should be) or double-carding. Added `SkeletonStatCard`,
  `SkeletonChart`, `SkeletonList`; `SkeletonTable` now echoes real column
  widths, supports a checkbox column, and a `bare` mode for use inside a Card
  (no nested chrome). Wired layout-matched skeletons into DashboardOverview,
  AIAnalytics, Brief, Actions, Reports, Case pages (headers stay visible during
  load); applied `bare` in Feed, AlertList, Incidents, AdminUsers.
- **Verification** — `tsc --noEmit && vite build` clean (1.56s); dev server
  serves `/`, `/login`, `/register` 200.

## Phase 24 — /analytics errors fixed + full preview stack running

- **Frontend hardening (AIAnalyticsPage)** — eliminated every runtime crash
  point: top-threats bar width no longer divides by zero (max-count scale,
  `|| 0` guards), Recent Detections tolerates missing arrays + invalid dates
  (`formatDate` helper), Explainability never calls `.map` on an undefined
  `contributions` (ML proxy can return unexpected shapes), Benchmark tolerates
  a missing `models` array, `model_type`/`method` render conditionally.
- **Preview stack brought up** so /analytics shows real data, not errors:
  - backend on SQLite `noctra_preview.db` (:8000, venv in backend/.venv)
  - ml-service on :8001 (venv in ml-service/.venv) — /ml/benchmark and
    /ml/explain/* now respond through the API
  - new `backend/seed_preview.py` (idempotent): demo user `demo` /
    `DemoPass123!` (ANALYST) + 41 alerts across 8 days (mixed severity/type/
    MITRE) so KPIs, trend, severity donut, top threats, recent all render.
  - verified end-to-end through the Vite proxy (:3000 → :8000): login →
    overview (41 total / 4 critical / 10 high / 10 recent) → trends (7
    points) → benchmark (models report "skipped — artifact missing", no
    error) → explain/log (contributions + summary + method).
- **Verification** — `tsc --noEmit && vite build` clean.

## Phase 25 — Profile image upload + interactive/detailed/responsive analytics charts

**Profile image upload** (`backend` + `dashboard`):
- New `POST /api/v1/user/profile/image` (multipart) in `backend/app/api/v1/endpoints/users.py`:
  validates content-type (PNG/JPEG/WEBP/GIF) + size (≤5 MB), stores under
  `backend/uploads/avatars/` with uuid names, deletes the previous avatar file,
  persists `user.profile_image`, returns `{message, profileImageURL}`.
- `backend/app/main.py` mounts `StaticFiles` at `/uploads` (dir created eagerly
  so the mount binds at import; lifespan re-ensures it). Vite dev proxy and
  `dashboard/nginx.conf` both forward `/uploads/` → backend so avatars load in
  the preview and in prod. `backend/uploads/` added to `.gitignore`.
- Profile page: avatar preview with camera badge → hidden file input
  (client-side type/size validation), upload progress overlay (Spinner light),
  "Change photo" / "Remove" controls, keep existing "paste URL" field as an
  alternative; `userApi.uploadProfileImage()` posts FormData with
  `Content-Type: multipart/form-data` (avoids axios's JSON default).
- Verified end-to-end via curl: upload 200 → static served on :8000 AND
  through the :3000 proxy (200 image/png) → profile persisted → re-upload
  removes the old file (404 on previous URL) → text/plain rejected 400.

**Analytics charts — interactive, detailed, responsive** (`AIAnalyticsPage.tsx`):
- Alert Trend: 7/14/30/90-day range segmented control (backend `?days=` 1..90
  already supported), clickable series legend toggling Total/Critical/High/
  Medium/Low lines, rich themed tooltip with per-series dots + values, cursor
  line + active dots, summary strip (total / avg per day / peak day), dots
  shown for ≤14-day ranges, loading overlay while switching ranges.
- Severity donut: hover-active slices (Sector outerRadius pop via activeShape),
  center total count, themed tooltip with % of total, legend shows count + %,
  radius is percentage-based so it scales with container (mobile via useIsMobile).
- Detections-by-type bars: themed tooltip, hover cursor fill, value labels on
  top of bars, maxBarSize so bars don't over-bloat on mobile.
- All chart cards now carry an explanatory subtitle; `CHART_TOOLTIP_STYLE`
  import dropped (custom tooltips theme through CSS vars instead).
- Verified: trends?days=7 and days=90 both 200 through the :3000 proxy;
  `tsc --noEmit && vite build` clean.

## Phase 26 — Login loop root cause (cookie context) + Entities graph upgrade + admin edit users

**Login "shows logged in, returns to login" — root cause + fix:**
- Sandbox reset wiped the gitignored `.env` (and venvs/node_modules/DB); the
  backend default `COOKIE_AUTH=false` meant login returned 200 + tokens in the
  body but NO Set-Cookie → every protected call 401 → /refresh 401 →
  axios interceptor clears the session → bounce to /login.
- Recreated `backend/.env` (COOKIE_AUTH=true, real JWT secrets) and re-added
  `backend/.env.example` (tracked) documenting the requirement (pushed f198622).
- Browser still failed after that because the Arena live preview embeds the
  app in a cross-site iframe: `SameSite=strict` cookies are not sent by the
  browser in that context → same loop. Fix: cookie flags now configurable
  (`COOKIE_SAMESITE`, `COOKIE_PARTITIONED` in config.py); preview .env uses
  `SameSite=None; Secure; Partitioned` (CHIPS) via a manual Set-Cookie header
  (Starlette rejects `partitioned=True` on Python < 3.14 — raw header emitted
  in `_set_auth_cookie`, Chrome 114+/Edge/Firefox parse `Partitioned`).
- Verified via :3000 proxy: login → Set-Cookie `HttpOnly; Secure; SameSite=None;
  Partitioned` ×2 → /user/me 200 → /refresh 200 → /analytics/overview 200.

**Admin can now edit users:**
- `AdminUsers.tsx` had `onEdit={() => undefined}` (TableWithAction edit button
  did nothing). Wired to a real edit modal: role (USER/ANALYST/ADMIN) +
  account-active toggle, read-only username/email context, `PATCH /users/:id`
  via `AdminApi.updateRosterUser` (backend supports role + is_active; audits
  USER_UPDATED). Verified: admin PATCH → 200 + persisted; non-admin → 403.
- Seeder now also creates an ADMIN demo user `admin` / `AdminPass123!`
  (idempotent; fixed a bug where the early-return on existing alerts skipped
  the final db.commit so new users never persisted).

**Entities & Graph upgraded (same treatment as /analytics):**
- `EntityGraphView.tsx` rewritten: scroll-to-zoom (zoom-to-cursor), drag-to-pan
  (pointer capture + move-suppressed clicks), zoom +/-/reset buttons with %
  readout, hover highlighting (non-connected nodes/edges dim), floating rich
  tooltip (type, value, risk, occurrences, degree), click-to-select + details
  panel (risk bar, last seen, connections list with relation + risk, Pivot
  button), double-click to pivot, header stats (nodes/edges/depth), full 7-type
  legend + relation legend (solid vs dashed), responsive layout (details panel
  stacks below graph on mobile), Escape to close, risk_score occurrences
  guarded with Number()/?? fallbacks.
- `EntitiesPage.tsx`: guarded risk_score rendering in the table (NaN-safe).
- Seeder now seeds 10 entities (ip/domain/hash/email/file/account/host) + 9
  directed links (resolves_to / communicates / derives_from / attaches /
  authenticates) so the page has real data; verified summary (10/9, by_type
  across all 7), graph fetch at depth 3, and path finder (4→10 reachable, 3 hops).

## Phase 27 — Full page-audit sweep (NaN/stale/unguarded-data) — remaining pages

Line-by-line audit of the pages that hadn't been swept yet; same standard as
the /analytics pass. Findings + fixes:

- DashboardOverviewPage: top-threats bars divided by threats[0].count (NaN
  width when the top threat count is 0) — now computed maxThreatCount, same
  fix as AIAnalyticsPage.
- ReportsPage: feed consumers elsewhere tolerate a bare array but this page
  did res.data.filter(...) — a bare array response would crash it. Now uses
  Array.isArray(res) ? res : res?.data ?? [] and guards c.title / String(c.id)
  in the search filter.
- AlertDetailModal: Number(alert.score).toFixed(3) rendered "NaN" when score
  is a non-numeric value — guarded with Number.isFinite.
- Navbar: notification time could render "Invalid Date" — nTime() helper
  returns "—" for missing/invalid timestamps.
- CasePage: chat confidence Math.round(msg.confidence * 100) when confidence
  is null (now != null + Number()) and timeline time could render
  "Invalid Date" (fmtTime helper).

Clean passes (no changes): ThreatAlertsPage (thin wrapper), AlertList
(severity/message guards + valid-page clamping), CreateIncidentModal,
IncidentsPage, FeedPage (asRows), BriefPage (timeOf + blast chips guarded),
LogHistoryPage, LandingPage + all landing components (static data), the
earlier-audited admin/soar/analytics/entities pages.

Verified: tsc --noEmit && vite build clean.

## Phase 28 — Code-accurate wireframe kit + system-conformance redesign pass

**Wireframe kit (`docs/wireframes/`)** — replaces direction-finding with documentation:
- 20 mid-fi HTML boards + clickable hub (`index.html`) + shared CSS/JS, no build step.
- Every board maps 1:1 to a route in `dashboard/src/App.tsx`: real nav IA (Main /
  Investigate / Automate / System), real copy, spec strip per board (route · source
  file · API endpoints), numbered annotations, X-box placeholders for dynamic regions
  (charts/graphs/reports — never fake data), night-canvas panels shown dark, severity
  as dot + label. Boards: inbox, feed, case workspace (+post-decision + confirm
  dialogs), actions, reports, SOC cockpit, alerts (+detail modal), analytics,
  entities (+graph explorer), SOAR, incidents, logs, profile/account, admin hub,
  admin people, admin config, app shell (⌘K menu + pending drawer + notifications),
  landing, auth, mobile patterns.
- Supersedes the exploratory boards in `docs/ui-concepts/` (kept for history).
- Maintenance rule: wireframes are derived artifacts — update the matching board in
  the same PR that changes a route/nav/page section.

**Frontend conformance pass (make the app match its own system):**
- DashboardOverviewPage: hand-rolled header → shared `PageHeader` (title "SOC
  Cockpit" to match nav + doc title, "Operational" badge, real `Button` secondary/
  primary actions instead of bespoke buttons).
- AdminDashboard: full restructure — `PageHeader`, metrics on `StatCard` (tone
  system, icons), link tiles via the shared `Card` component with arrow-hover
  affordance; removed the bespoke `text-3xl tracking-wide` header and tile classes.
- EngineSettingsPage: hand-rolled BackButton + h1 → `PageHeader` with crumbs
  (Administration / Engine Settings).
- Profile + Account(/account): hand-rolled h1/h2 → `PageHeader`; Account now reads
  as a proper page (header + card) instead of a floating form.
- Verified: `tsc --noEmit && vite build` clean.

## Phase 29 — NOCTRA SIGNAL retheme (design source: newfile.html)

The Canva export `newfile.html` (pushed to main, mirrored at
`docs/design/noctra-signal-reference/part-1-landing.html` + noctradesign.my.canva.site)
defines the new brand: ink canvas + signal green, DM Sans + Space Mono, sharp corners,
HUD corner brackets, console panels, tech labels, scan radar. The violet DUALITY
identity is retired.

**Token system (`styles/globals.css` + `tailwind.config.js`):**
- `:root` (and `html.dark`) = signal dark (ink #070b0f, panel #0d151b, signal #a6ff3f);
  `html.light` = new "day ops" paper variant; `.night` = console panels (always ink).
  ThemeProvider is now dark-first (stored preference still wins).
- Fonts swapped to DM Sans (+ display) and Space Mono (@fontsource packages; old
  Inter/Sora/JetBrains Mono fontsource deps removed).
- Radius scale compressed to 2–4px (sharp); shadows retuned for ink; brand-gradient
  token is now flat signal green; chart-1 = signal; severity ramp unchanged
  (dot + label rule intact).
- New utilities: `.noctra-canvas` (ink shell + 56px signal grid fading down + two
  radial glows), `.tech-label`, `.signal-dot` (pulsing), `.hud-corners`,
  `.threat-item`, `.console-panel`, `.scan-ring/.scan-line/.scan-core` with
  `is-scanning`, `wf-pulse/spin/sweep/reveal` keyframes.

**Components:** Button primary/secondary now match action-button/secondary-button
(solid green + lift/glow hover; hairline secondary with green hover); StatCard is the
metric-card (tech-label + bold value); BrandLogo is the signal-dot + "NOCTRA"
wordmark (tracking .22em) + favicon refreshed; sidebar active item = green left
border; analyst-voice panels (inbox lead card with HUD corners, case evidence/blast
radius/chat, report previews) use the console-panel treatment; ~27 hand-rolled
gradient buttons across pages converted to sharp signal actions; entity-graph node
colors + cockpit chart strokes de-violetted.

**Landing fully rewritten from newfile.html** (`LandingNav/Hero/TrustBar/
ConsoleDemo/FeatureGrid/FinalCTA`): blur header, hero with HUD-bracketed SVG topology
("Threat topology / live"), stats band (24/7 · <5 min · 360° · 1 view), interactive
console demo (metrics 1,284/48.7k/03/92%, prioritized-event threat items, scan radar
with working Start/Reset scan state), 3 feature cards, access panel, footer. Auth
surface forced to the ink canvas (no theme toggle). index.html meta/favicon text
updated to "Threat intelligence, always on".

**Wireframe kit v3 · SIGNAL** (`docs/wireframes/`): shared CSS retokened to the
signal system (all 20 boards restyle through the wf-* classes), shell chrome updated
(signal-dot brand, green active nav), landing board is a 1:1 port of newfile.html,
auth board is ink, hub/README rewritten for the Signal system.

**Preview verified end-to-end:** backend venv + .env (cookie auth, CHIPS partitioned)
restored and seeded; login 200 → Set-Cookie → /user/me 200 (7 perms) → /analyst/brief
200 through the :3000 proxy; `tsc --noEmit && vite build` clean.
