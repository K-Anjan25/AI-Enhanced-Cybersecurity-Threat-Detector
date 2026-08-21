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

## Status

- All 67 FRs implemented and verified (backend `pytest`, `tsc` + `vite
  build`, Docker E2E smoke, live `kind` rollout).
- FR-AUDIT-05 (`X-Request-ID` tracing) verified via integration tests
  (`test_endpoints.py` echo + generate cases) and marked `IT` in the matrix.
- The ml-service image ships with real log/email models baked in; the
  network (IsolationForest) model requires CICIDS2017 data at
  build/retrain time (skipped by default).
- Every push runs the k6 NFR-PERF suite against the compose stack in CI
  (failure-rate gate < 1%; latencies recorded as a dev-runner baseline —
  strict p95 gates still enforced by `CI=false` local runs).
- Remaining for production only: apply ingested ingress-nginx + cert-manager
  manifests and create the managed-DB Secret (see `k8s/README.md`).