# NOCTRA Demo — 5-Minute Walkthrough

> **NOCTRA** — *Threat intelligence, always on.* — http://localhost:3000
> (`/welcome` → `/` → `/case/1`)

The exact script for demonstrating NOCTRA. Design system: **SIGNAL** — ink canvas
`#070b0f` + signal green `#a6ff3f`, DM Sans + Space Mono, sharp corners, HUD
brackets, console panels.

**Accuracy contract.** Every route, endpoint, file path and number below was read
from the code in this repository, not from memory or from an earlier brand. Where
the product cannot do something yet, this script says so out loud — a demo that
overstates the product is worse than no demo.

---

## 0. Before you start

### Bring the stack up

```bash
docker compose -f docker/docker-compose.yml up -d --build
# dashboard :3000 · backend :8000 · ml-service :8001 · postgres :5431
```

Manual dev setup instead (three terminals + a seed):

```bash
cd ml-service && python -m uvicorn app.main:app --port 8001
cd backend   && python -m uvicorn app.main:app --port 8000
cd backend   && python seed_preview.py          # demo user + ~60 alerts over 7 days
cd dashboard && npm run dev                     # Vite proxies /api → :8000
```

### Sign in

| Field | Value |
| --- | --- |
| Username | `demo` |
| Email | `demo@noctra.ai` |
| Password | `DemoPass123!` |
| Role | `ANALYST` |

Created idempotently by `backend/seed_preview.py`. Without seeding, register your
own account at `/register` — the Inbox will be empty until you fire a scenario
(§3), which is a perfectly good cold-start story.

### Say it right — the four language rules

The product's whole claim is that it is honest. Breaking these in a demo breaks
the claim:

1. **"Recorded", never "executed".** SOAR is record-only. NOCTRA writes the
   action and its compensating reversal to the log; it never touches your
   systems. Never say "blocks", "revokes", "contains" or "remediates"
   unqualified — say "records a recommendation to …".
2. **Name the reasoning source.** With `ANTHROPIC_API_KEY` set, the case reads
   "Reasoned by `<model>`". Without it, the case reads "NOCTRA built-in
   reasoning engine" (`analysis.fallback = true`, `model =
   "fallback-template"`). Say which one you are showing — the fallback is a
   deterministic template, not a model inference.
3. **Confidence is a number, not a vibe.** The Inbox renders `n/a` instead of a
   percentage when the analysis is a fallback. Do not improvise a number.
4. **Empty is honest.** Empty states are real states. "Nothing is waiting" is a
   better sentence than inventing an incident.

---

## 1. Landing — the brand (0:00–0:35) · `/welcome`

- Open **http://localhost:3000/welcome** — `LandingPage.tsx`.
- Say: *"NOCTRA is the autonomous security analyst for small teams. You employ an
  analyst; you don't operate a dashboard."*
- Walk the page top to bottom (it is a 1:1 port of the SIGNAL design source
  `newfile.html`):
  - **Hero** — eyebrow *Autonomous threat intelligence* → headline *"See the
    threat before it sees you."* → HUD-bracketed SVG threat-topology frame
    (no stock art — the frame is built in SVG, per the repo rule).
  - **Stats band** — `24/7` · `< 5 min` · `360°` · `1 view`. Capability claims
    only, no invented telemetry numbers. (The console demo below *does* show
    numbers — but it is a labelled demo panel, and this script tells you to say
    so.)
  - **Console demo** — click **Start scan** (→ **Reset scan**): the radar sweep
    animates, prioritized threat items populate, and the metric cards read
    `1,284` assets mapped · `48.7k` signals/hour · `03` critical paths · `92%`
    noise reduced. These are **illustrative demo values in a labelled demo
    panel**, not live telemetry — say so if anyone asks. The stats band above
    (24/7, < 5 min, 360°, 1 view) is different: those are capability claims.
  - **Feature grid**, **access panel**, **footer**.
- Note the chrome: ink canvas with the 56px signal grid, `signal-dot` live mark,
  `tech-label` in Space Mono, sharp 2–4px corners.

## 2. Sign in (0:35–1:00) · `/login`

- **Request access** → `/register`, then **Sign in** → `/login`.
- The auth surface is forced to the ink canvas (no theme toggle here — asking
  the analyst happens in the dark).
- Sign in as `demo` → lands on the **Analyst Inbox** (`/`).

## 3. Analyst Inbox — what needs you (1:00–1:45) · `/`

`BriefPage.tsx` → `GET /analyst/brief`. Point at the lead card and the metrics:

| Metric | Meaning | Endpoint field |
| --- | --- | --- |
| Waiting for you | Analyst cases with `decision = pending` | `pending_count` |
| Decisions by you | Decided since local midnight | `handled_today` |
| Assets watched | Entity rows in your org | `watching` |
| Events investigated today | Raw detections created today | `alerts_today` |
| Auto-recorded responses | SOAR actions recorded by rules (excludes analyst decisions and their reversals) | `auto_recorded_today` |

The sub-line reads as a sentence: *"N events investigated today · N auto-recorded
responses · N decisions by you · N waiting."* Every number is a real count —
nothing is estimated.

Then **fire a scenario** — this is the moment the demo becomes real:

- Pick a scenario in the Inbox control, or press **⌘K / Ctrl+K** → **Actions** →
  `Simulate: Credential leak (T1078)`. Both call
  `POST /analyst/simulate?scenario_type=…`.
- Four scenarios exist, all wired: `credential_leak` (T1078),
  `phishing_outbreak` (T1566), `data_exfiltration` (T1048),
  `compromised_api_key` (T1098).
- What happens server-side in one request: a CRITICAL alert is inserted → the
  blast radius is built in the entity graph → one reversible action is drafted →
  a `pending` analyst case is opened → `ANALYST_CASE_OPENED` is appended to the
  audit trail. You land on the new case.

## 4. Case workspace — the reasoning (1:45–3:00) · `/case/:id`

`CasePage.tsx` → `GET /analyst/cases/{id}` + `GET /analyst/cases/{id}/timeline`.
Walk it in this order:

1. **Headline + plain-English narrative** — what happened, why it matters,
   stated confidence. Console-panel treatment (ink + green hairline) because
   this is the analyst's voice.
2. **Evidence (Observed)** — resolved from `case.source_alert_id`: type,
   severity, source IP, MITRE technique, raw message. If the alert row is gone
   the page says so instead of inventing one.
3. **Blast radius** — the connected assets, with risk. Term tooltips
   (hover/focus) give the plain-English gloss; the label stays formal.
4. **The ask** — one recommended action with its `undo` line. Read the
   word **Reversible** out loud; it is the product's promise made visible.
5. **Case record** — server-composed timeline from real rows only (evidence,
   case opened, decision, recorded action, report, audit entries). Absent rows
   produce no entries — never filler.
6. **Ask NOCTRA** — `POST /analyst/cases/{id}/chat`. Ask *"What's affected in
   the blast radius?"* The answer is grounded in the case's own entities.

## 5. The decision — and the record (3:00–3:50)

- **Approve Action** → confirm dialog states plainly that NOCTRA will *record*
  `REVOKE_CREDENTIALS` on the target, that it is reversible and record-only.
- `POST /analyst/cases/{id}/approve` → decision `approved`, status `resolved`,
  `soar_action_id` **recorded**, report generated, audit entry appended.
- **Reports** (`/reports`) → download `noctra-report-case-{id}.md`. Open it:
  the loop in writing, with the reasoning source named.
- **Actions** (`/actions`) → the action log. Every row carries a one-click
  **Revert** (`POST /analyst/cases/{id}/revert`) that records the compensating
  action and flips the case to `reverted`. Revert it live if you want — that is
  the reversibility claim being proven, not described.
- Decline path: `POST /analyst/cases/{id}/decline` closes the case with no
  action; it stays in the decision feed as a decision.

## 6. Investigate — the depth behind the analyst (3:50–4:40)

Optional, and only if the audience wants the engine room. Say the honest framing:
*"NOCTRA leads with the analyst; this is the deep dive it stands on."*

- **Alerts** (`/alerts`) — `AlertList` over `GET /alerts`; search, severity
  filter, MITRE mapping; detail modal links straight to the case opened from
  that alert.
- **Entities & Graph** (`/entities`) — summary KPIs, scroll-zoom/drag-pan graph
  with hover highlighting and a details panel, and a BFS **path finder**
  (`GET /entities/path`). Seeded with 10 entities / 9 links.
- **Analytics** (`/analytics`) — 7-day trend, severity mix, top patterns, and
  the model **benchmark** table (`GET /ml/benchmark`).
- **SOC Cockpit** (`/dashboard`) — the classic operational view, kept.
- **SOAR** (`/soar`) — playbook CRUD, dry-run rule evaluation, action records.
- **Manual Incidents** (`/incidents`) · **Log Uploads** (`/logs`,
  `POST /upload-logs` → `GET /logs/history`).

## 7. Administration (4:40–5:00) — `ADMIN` only

`/admin` hub → **Users**, **Tenants**, **Roles** (ABAC matrix),
**Rules**, **Reputation**, **Engine**, **Audit** (`/admin/system-logs`).
Point at the audit trail specifically: every decision, chat question and state
change lands in an append-only log. That is the compliance story.

## 8. Close

> *"NOCTRA watches the telemetry, explains what happened in plain English, maps
> what is affected, and drafts one reversible action — then it stops and asks.
> You approve; it records and reports. Nothing executes behind your back, and
> every step is auditable."*

---

## Local URLs

| Surface | URL |
| --- | --- |
| Landing | http://localhost:3000/welcome |
| Console (→ Inbox after login) | http://localhost:3000 |
| Backend health | http://localhost:8000/health/live · /health/ready |
| ML service health | http://localhost:8001/health |

---

## Verification matrix

Run this before a demo, or after any change to a page. **Pass** = the page loads,
the listed endpoints return data, and the expected state holds — with no fake,
placeholder or `NaN`/`Invalid Date` values anywhere on screen.

All endpoints are relative to the API base `/api/v1` (`dashboard/src/api/axios.ts`);
in compose, nginx on `:3000` proxies them to the backend on `:8000`.

| # | Route | Source file | Endpoints | Expected state |
| --- | --- | --- | --- | --- |
| 1 | `/welcome` | `features/landing/pages/LandingPage.tsx` | — (static) | Hero + stats band + console demo; Start/Reset scan works; no fabricated metrics |
| 2 | `/login`, `/register`, `/reset-password` | `features/auth/**`, `store/userActions.ts` | `POST /login`, `POST /register`, `GET /me`, `POST /refresh`, `POST /logout`, `POST /forgot-password`, `POST /reset-password` | Ink canvas, no theme toggle; login sets httpOnly cookies (`COOKIE_AUTH=true`); 401 triggers single-flight refresh then clean logout |
| 3 | `/` Inbox | `features/inbox/pages/BriefPage.tsx` | `GET /analyst/brief`, `/analyst/connectors`, `/analyst/feed`; `POST /analyst/simulate`, `/analyst/connectors/{id}/sync` | All five brief counts render as integers; scenario control creates a case and navigates to it; empty state reads as a sentence, not an error |
| 4 | `/feed` | `features/cases/pages/FeedPage.tsx` | `GET /analyst/feed` | Paginated decision feed, newest first; pending/approved/declined/reverted badges correct |
| 5 | `/case/:id` | `features/cases/pages/CasePage.tsx` | `GET /analyst/cases/{id}`, `.../timeline`; `POST .../approve`, `.../decline`, `.../revert`, `.../chat` | Narrative + evidence + blast radius + one reversible action with `undo`; timeline composed from real rows; approve → `soar_action_id` recorded; revert → `reverted` |
| 6 | `/actions` | `features/actions/pages/ActionsPage.tsx` | `GET /analyst/feed`; `POST /analyst/cases/{id}/revert` | Only `approved`/`reverted` cases; filter by action type/target/case; record-only + reversible stated |
| 7 | `/reports` | `features/reports/pages/ReportsPage.tsx` | `GET /analyst/feed`, `/analyst/cases/{id}/report` | Report downloads as `noctra-report-case-{id}.md`; names the reasoning source |
| 8 | `/alerts` | `features/alerts/pages/ThreatAlertsPage.tsx` → `AlertList` | `GET /alerts`, `/save-scanned-alerts` | Search + severity filter + MITRE mapping; detail modal links to any case opened from the alert |
| 9 | `/entities` | `features/entities/pages/EntitiesPage.tsx`, `components/EntityGraphView.tsx` | `GET /entities`, `GET /entities/summary`, `GET /entities/{id}/graph`, `GET /entities/path`, `POST /entities/{id}/reputation` | Graph summary (10 nodes / 9 links when seeded); zoom/pan/select; path finder returns real hops; risk values guarded |
| 10 | `/analytics` | `features/analytics/pages/AIAnalyticsPage.tsx` | `GET /analytics/overview`, `/analytics/trends`, `/analytics/top-threats`, `/ml/benchmark` | Charts render with `role="img"` + labels; no divide-by-zero bar widths |
| 11 | `/dashboard` | `features/dashboard/pages/DashboardOverviewPage.tsx` | `GET /analytics/overview`, `/analytics/trends`, `/analytics/top-threats` | SOC Cockpit header via shared `PageHeader`; top-threats bars bounded by computed max |
| 12 | `/incidents` | `features/incidents/pages/IncidentsPage.tsx`, `components/CreateIncidentModal.tsx` | `GET /cases`, `POST /cases`, `PATCH /cases/{id}` | Manual incident CRUD works |
| 13 | `/logs` | `features/system/pages/LogHistoryPage.tsx` | `POST /upload-logs`, `GET /logs/history`, `GET /uploads/{batchId}` | Upload → scan → save; history lists batches |
| 14 | `/soar` | `features/soar/pages/SoarPage.tsx` | `GET /soar/actions`, `POST /soar/evaluate`, `POST /soar/trigger/{alertId}`, `GET/POST /soar/playbooks`, `PATCH/DELETE /soar/playbooks/{id}` | Playbooks list (rule selector loads — rules capped at 100); dry-run evaluation returns matches; action records present |
| 15 | `/profile`, `/account` | `features/account/pages/Profile.tsx`, `components/Account.tsx` | `GET /user/profile`, `PUT /user/profile`, `POST /user/profile/image`, `PUT /user/updatePassword` | Avatar upload + profile + password update |
| 16 | `/admin` | `features/admin/pages/AdminDashboard.tsx` | `GET /admin/orgs`, `GET /users`, `GET /rules` | Tiles + metrics on shared components |
| 17 | `/admin/users` | `features/admin/pages/AdminUsers.tsx` | `GET /admin/orgs`, `GET/POST /users`, `PATCH/DELETE /users/{id}` | Roster create/edit/delete |
| 18 | `/admin/tenants` | `features/admin/pages/TenantsPage.tsx` | `GET /admin/orgs` | Tenant list |
| 19 | `/admin/roles` | `features/admin/pages/AccessRolesPage.tsx` | `GET /admin/roles` | ABAC role × permission matrix |
| 20 | `/admin/rules` | `features/admin/pages/RulesPage.tsx` | `GET/POST /rules`, `PUT/DELETE /rules/{id}` | Detection-rule CRUD |
| 21 | `/admin/reputation` | `features/admin/pages/ReputationPage.tsx` | `GET/POST /reputation`, `POST /reputation/{ip}/block`, `.../unblock` | IP reputation CRUD + block/unblock |
| 22 | `/admin/engine-settings` | `features/admin/pages/EngineSettingsPage.tsx` | `GET/PUT /engine/settings` | Engine settings persist |
| 23 | `/admin/system-logs` | `features/admin/pages/SystemLogsPage.tsx` | `GET /audit-logs` | Append-only audit trail; decision + chat + error entries visible |
| 24 | Shell (all routes) | `layouts/DashboardLayout`, `components/CommandMenu.tsx`, `Navbar`, `OnboardingChecklist` | `GET /analyst/notifications`, `GET /me` | ⌘K menu (Navigate · Cases · Actions); notification bell shows real pending count; sidebar is a drawer below `lg`; skip-link + `main#main-content` present; onboarding steps derive from real data |

**Automated gates** (run these too — CI runs them on every push):

```bash
cd backend   && pytest tests      # 121 passed, 2 skipped
cd ml-service&& pytest tests      # 13 passed
cd dashboard && npx tsc --noEmit && npm run build
```

**Reset between takes:**

```bash
docker compose -f docker/docker-compose.yml down -v   # wipe volumes
docker compose -f docker/docker-compose.yml up -d --build
```

---

## Known gaps — say these before someone finds them

Honest gaps are better than surprise gaps. As of this writing:

- **Connectors** are a status surface with a sync action
  (`POST /analyst/connectors/{id}/sync`); there is no live third-party sync
  against Okta / CrowdStrike / GuardDuty / Cloudflare yet.
- **The landing console-demo numbers are illustrative.** They live in a labelled
  demo panel on the public marketing page; every number inside the signed-in
  product is a real count.
- **LLM reasoning** requires `ANTHROPIC_API_KEY`; without it every case uses the
  deterministic fallback and the UI labels it "NOCTRA built-in reasoning engine"
  with confidence `n/a`.
- **Scenarios are simulated.** `POST /analyst/simulate` injects a synthetic but
  realistic incident — say "simulate", not "detect", when you fire one live.
