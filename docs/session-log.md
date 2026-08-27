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

