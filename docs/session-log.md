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

## Status

- All 67 FRs implemented and verified (backend `pytest`, `tsc` + `vite
  build`, Docker E2E smoke, live `kind` rollout).
- FR-AUDIT-05 (`X-Request-ID` tracing) verified via integration tests
  (`test_endpoints.py` echo + generate cases) and marked `IT` in the matrix.
- The ml-service image ships with real log/email models baked in; the
  network (IsolationForest) model requires CICIDS2017 data at
  build/retrain time (skipped by default).
- Remaining for production only: apply ingested ingress-nginx + cert-manager
  manifests and create the managed-DB Secret (see `k8s/README.md`).