# NOCTRA Demo — 5-Min Portfolio Walkthrough

> **NOCTRA** — *Silent. Precise. Always watching.* (`noctra.ai`) — http://localhost:3000 (`/welcome` → `/alerts`)

This is the exact click-path for a Loom/portfolio recording. Stack is `docker compose -f docker/docker-compose.yml up -d --build` (postgres + backend + ml-service + dashboard).

---

## 0. Opening (0:00-0:20) — Brand

- Show **http://localhost:3000/welcome** — NOCTRA hero, 4-feature grid (Detect/Explain/Respond/Connect), `Silent. Precise. Always watching.` tagline.
- Say: “NOCTRA is the AI analyst that never blinks — 6-char, 2-syllable, hard invented + nocturnal totem, abstract to grow.”

## 1. Auth (0:20-0:50)

- Click **Start free** → `/register` — note `BrandLogo` owl-eye + gradient CTA (`cyan #00e0ff → violet #7c3aed`).
- Register `analyst / analyst@noctra.ai / ChangeMe#2026` (role ANALYST) → **Sign in** → `/login` → same brand header.
- Login — lands on **SOC Overview** (`/`).

## 2. SOC Overview (0:50-1:30)

- Show KPI strip (Total / Critical / High / Open Incidents / SOAR) — `StatCard` with NOCTRA tokens; trend `AreaChart` (`#00e0ff` total, `#ef4444` critical on `#141e32` tooltip); Top Threats bars (`bg-accent-primary`).
- Point to **Critical Alerts** rail — 5 most recent, `SeverityBadge` (dot+label, CVD-safe).

## 3. Triage Queue (1:30-2:30) — Core SOC

- Click **Threat Alerts** (`/alerts`) — `AlertList` with search + severity filter (`All / Critical / High / Medium / Low`), `SkeletonTable` on load, `EmptyState` when clear.
- Search `Failed password` → filter `Critical` → click row → `AlertDetailModal` shows **MITRE** (`T1059`) + **threat-intel** + **Explain** evidence beside alert (not 3 clicks away).

## 4. Upload & Scan (2:30-3:10)

- Go **Log History** (`/logs`) — choose `sample.log` (`.log/.csv`) → **Upload and Scan** → shows `Scanned: 100 / Threats: 3` → **Upload History** table appears; click **Refresh**.

## 5. Entity Graph (3:10-3:50)

- Open **Entity Graph** (`/entities`) — summary KPIs (nodes/edges/hub degree), **Path Finder** (From ID → To ID → Trace path → `→` pills), table with `Risk score` bar (`#ef4444`/`#f97316`/`#f59e0b`/`#10b981`) + `Graph` pivot → `EntityGraphView` SVG (NOCTRA violet ring).

## 6. SOAR & AI Analytics (3:50-4:40)

- **SOAR Automation** (`/soar`) — Dry-run evaluator (`system_log` + message → Test rules → `2 action(s) would fire: BLOCK_SOURCE_IP`), Playbooks table (active/paused), Executed actions audit.
- **AI Analytics** (`/analytics`) — KPIs, 7-day `LineChart` (`#00e0ff`/`#ef4444`), **Severity Distribution** pie (`SEVERITY_COLORS` NOCTRA), **Model Explainability** (select `log` → paste `SQL injection exploit` → **Explain** → contributions with `attack`/`attention`/`benign` dots), **Model Benchmark** cards (`ok`/`warn`).

## 7. Admin (4:40-5:00) — Close

- Quickly show **Admin Console** (`/admin`) → `SystemLogsPage` (append-only audit, `CLIENT_ERROR` telemetry), `Detection Rules` / `IP Reputation` (admin:read / users:manage gated). Note `X-Request-ID` in network tab.
- Close: “Every push runs k6 NFR-PERF (`CI=true` failure-rate <1%) + `pytest` + `vite build` + `kubeconform` — full traceability in `docs/traceability-matrix.md`.”

---

## Local URLs

- Landing: http://localhost:3000/welcome
- Console: http://localhost:3000 (→ /alerts after login)
- API: http://localhost:8000/health/ready, http://localhost:8001/health, POST /api/v1/analyze (see smoke in `docs/session-log.md: Phase 16`)

## Stack

```
docker compose -f docker/docker-compose.yml up -d --build postgres backend ml-service dashboard
# dashboard at :3000 (NOCTRA), backend :8000, ml :8001, postgres :5431
# .dockerignore keeps dashboard context 6.70 kB (was 157 MB)
```

Stop: `docker compose -f docker/docker-compose.yml down`
