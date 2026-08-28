# NOCTRA — UI Wireframe Kit v2 (code-accurate)

Open **`index.html`** in a browser (or `python3 -m http.server` from this folder) for the
clickable hub. Every board is a standalone HTML file — no build step, no dependencies.

## What this is

Wireframes generated **from the code**, not from imagination:

- Every board maps 1:1 to a route in `dashboard/src/App.tsx`.
- Navigation IA is the real one (`DashboardLayout`): **Main** (Home / Cases / Actions /
  Reports = the analyst loop) with **Investigate / Automate / System** as progressive
  disclosure.
- Copy is the real copy from the components (page titles, descriptions, empty states,
  button labels).
- Data contracts match the API clients (`api/*.ts`) — the spec strip on each board lists
  route, source file, and endpoints.
- The DUALITY system is preserved: day workspace surfaces, **night canvas** panels for
  the analyst's voice (briefs, evidence, blast radius, reports).
- Type stack, spacing rhythm (16px gutters / 20px card padding / 16px radius) and
  severity dot+label rules mirror `tailwind.config.js` + `styles/globals.css`.

## Conventions

| Device | Meaning |
| --- | --- |
| Numbered blue dot | Annotation — explained in the Notes list under each board |
| X-box (dashed, crossed) | Dynamic region (chart / graph / report body / avatar) — never fake data |
| Dark panel | Night canvas — stays dark in both themes |
| Violet | The only brand accent: mark, active nav, primary actions |
| Mono text | Identifiers, numbers, timestamps, machine values |
| Dot + label | Severity — never color alone |

## Maintenance rule

These wireframes are **derived artifacts**. When a route, nav group, or major page
section changes in `dashboard/src`, update the matching board in the same PR. The
screen-inventory table in `index.html` is the map (route → board → source file → APIs).

This kit **supersedes** the exploratory direction boards in `docs/ui-concepts/`
(concepts 01–36, directions A–L, and `new3/wireframe-L*.png`). Those were
direction-finding artifacts; this kit documents the product as built (plus the
redesign deltas noted on the SOC Cockpit, Admin, Engine Settings and Profile boards).

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
| `landing.html` | `/welcome` | `LandingPage.tsx` → `components/landing/*` |
| `auth.html` | `/login` `/register` `/reset-password` | `auth/*` + `AuthLayout.tsx` |
| `mobile.html` | responsive | all pages |
