# NOCTRA — UI Wireframe Kit v3 · SIGNAL (code-accurate)

Open **`index.html`** in a browser (or `python3 -m http.server` from this folder) for the
clickable hub. Every board is a standalone HTML file — no build step, no dependencies.

## What this is

Wireframes in the **NOCTRA SIGNAL system**, whose design source is `newfile.html`
(the Canva export of noctradesign.my.canva.site) and which is now implemented in the
dashboard itself:

- **Tokens** — ink canvas `#070b0f`, panel `#0d151b`, signal green `#a6ff3f`
  (`--signal-dark: #73bf19`), text ramp `#e8f0ed / #aebdc0 / #8fa2a8 / #71858a`,
  hairlines ≈ `rgba(162,193,198,.16)`, signal grid texture (56px, fading) + two
  radial glows. Sharp corners (2–4px); tags/avatars stay round.
- **Type** — DM Sans (UI + display, bold with tight tracking) and Space Mono
  (`tech-label`: .68rem, uppercase, tracking .13em — eyebrows, metric labels, tags).
- **Component vocabulary** — `signal-dot` (pulsing live mark), HUD corner brackets,
  `console-panel` (ink gradient + green hairline — the analyst's voice),
  `metric-card`, `threat-item` (green left border event row), `scan-ring`/`scan-line`
  radar, action/secondary buttons, feature cards (green top border, hover lift).
- **Boards** map 1:1 to routes in `dashboard/src/App.tsx` with the real IA, real copy
  and real data contracts (spec strip per board: route · source file · endpoints).
- The landing board is a 1:1 port of `newfile.html` (header → hero + HUD frame →
  stats band → interactive console demo with scan radar → features → access → footer).

## Conventions

| Device | Meaning |
| --- | --- |
| Numbered blue dot | Annotation — explained in the Notes list under each board |
| X-box (dashed, crossed) | Dynamic region (chart / graph / report body / avatar) — never fake data |
| Green-hairline panel | Console panel — the analyst's voice (briefs, evidence, blast radius, reports) |
| Signal green | The only accent: mark, active nav, actions, live status, event markers |
| Space Mono / tech-label | Eyebrows, metric labels, tags, telemetry, identifiers |
| Dot + label | Severity — never color alone |

## Maintenance rule

These wireframes are **derived artifacts**. When a route, nav group, or major page
section changes in `dashboard/src`, update the matching board in the same PR. The
screen-inventory table in `index.html` is the map (route → board → source file → APIs).

This kit supersedes the exploratory direction boards in `docs/ui-concepts/`
(concepts 01–36, directions A–L) and wireframe kit v2 (violet DUALITY).

## Boards

| Board | Route | Source |
| --- | --- | --- |
| `analyst-inbox.html` | `/` | `features/inbox/pages/BriefPage.tsx` |
| `cases-feed.html` | `/feed` | `features/cases/pages/FeedPage.tsx` |
| `case-workspace.html` | `/case/:id` | `features/cases/pages/CasePage.tsx` |
| `actions-log.html` | `/actions` | `features/actions/pages/ActionsPage.tsx` |
| `reports.html` | `/reports` | `features/reports/pages/ReportsPage.tsx` |
| `soc-cockpit.html` | `/dashboard` | `features/dashboard/pages/DashboardOverviewPage.tsx` |
| `alerts.html` | `/alerts` | `features/alerts/*` + `AlertList.tsx` |
| `analytics.html` | `/analytics` | `features/analytics/pages/AIAnalyticsPage.tsx` |
| `entities.html` | `/entities` | `EntitiesPage.tsx` + `EntityGraphView.tsx` |
| `soar.html` | `/soar` | `features/soar/pages/SoarPage.tsx` |
| `incidents.html` | `/incidents` | `IncidentsPage.tsx` + `CreateIncidentModal.tsx` |
| `logs.html` | `/logs` | `features/system/pages/LogHistoryPage.tsx` |
| `profile.html` | `/profile`, `/account` | `Profile.tsx`, `Account.tsx` |
| `admin.html` | `/admin` | `admin/pages/AdminDashboard.tsx` |
| `admin-users.html` | `/admin/users·tenants·roles` | `AdminUsers/TenantsPage/AccessRolesPage` |
| `admin-config.html` | `/admin/rules·reputation·engine-settings·system-logs` | corresponding admin pages |
| `app-shell.html` | shell | `DashboardLayout` · `Navbar` · `CommandMenu` · `PendingDecisionsDrawer` |
| `landing.html` | `/welcome` | `newfile.html` → `LandingPage.tsx` → `components/landing/*` |
| `auth.html` | `/login` `/register` `/reset-password` | `auth/*` + `AuthLayout.tsx` |
| `mobile.html` | responsive | all pages |
