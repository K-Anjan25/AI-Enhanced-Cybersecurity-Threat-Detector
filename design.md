# UI/UX Design — AI-Enhanced Cybersecurity Threat Detector (AEGIS)

|                  |                                                                                                         |
|---|---|
| **Document**     | Interface and experience design specification                                                           |
| **Version**      | 0.1                                                                                                     |
| **Last updated** | 2026-10-02                                                                                              |
| **Status**       | Approved for build                                                                                      |
| **Implements**   | [prd.md](prd.md) FR-50…FR-54, NFR-09                                                                    |
| **Related**      | [architecture.md](architecture.md) · [rules.md](rules.md) · [task.md](task.md) · [memory.md](memory.md) |

---

## 1. Design principles

1. **Triage in sixty seconds.** The primary job is: land on an alert, understand it, decide. Every screen is judged against the 60-second triage target in [prd.md](prd.md#8-success-metrics).
2. **Evidence over assertion.** A score is an opinion. A timeline, the raw flows, and the top contributing features are evidence. Evidence is always one click away, never buried.
3. **Calm by default, loud when it matters.** A SOC dashboard is stared at for eight hours. Reserve saturated colour and motion for severity — a screen that shouts constantly trains the analyst to ignore it.
4. **Density is a feature.** Analysts are expert users. Prefer information density with clear hierarchy over generous whitespace that pushes evidence below the fold. Offer a comfortable mode; do not force one.
5. **Honest states.** Loading, empty, partial, degraded, and error are distinct, labelled states. The UI never renders a blank panel where data failed to arrive, and never invents a number.
6. **Colour is never the only channel.** Severity is encoded by colour **and** label, so the product is usable by colour-blind analysts and in greyscale printing (NFR-09).

## 2. Personas and key flows

### 2.1 Ana (Tier 1 analyst) — the triage loop

```
notification ──► Alerts (filtered to open, high+) ──► select alert
                                                          │
                    ┌─────────────────────────────────────┘
                    ▼
             Alert detail: verdict banner → explanation → timeline → raw evidence
                    │
       ┌────────────┼────────────┬─────────────────┐
       ▼            ▼            ▼                 ▼
   mark TP      mark FP     escalate to case    suppress family 15m
       │            │            │                 │
       └────────────┴────────────┴─────────────────┘
                    ▼
            back to the list, next alert pre-focused
```

Design consequences: `j`/`k` to move through the list, `Enter` to open, `1`/`2`/`3` to set a verdict, `Esc` to return with the previous selection intact. The next alert is pre-focused so the loop never requires a mouse.

### 2.2 Raj (Security lead) — the hunt and tune loop

Hunt console query → inspect results → spot a pattern → adjust that family's threshold → verify the change on the last 24 h of scores in the Model Ops view → confirm. The loop must be completable without leaving the browser or asking engineering.

### 2.3 Priya (CISO) — the reporting loop

Opens Overview, reads the 30-day trend, exports a PDF. Needs a defensible sentence: what we detected, what we missed, how the numbers moved.

## 3. Information architecture

```
AEGIS
├── Overview                 /                      dashboard, posture, live status
├── Threats
│   ├── Alerts               /alerts                primary triage queue
│   ├── Alert detail         /alerts/:id            evidence + verdict
│   └── Cases                /cases                 grouped, correlated incidents
├── Explore
│   ├── Traffic              /traffic               flow time-series + entity graph
│   ├── Logs                 /logs                  log stream + anomaly windows
│   └── Hunt                 /hunt                  structured search over raw data
├── Models
│   ├── Model ops            /models                versions, metrics, promotion
│   └── Drift                /models/drift          PSI per feature, retrain triggers
└── Admin                    /admin
    ├── Users & roles        /admin/users
    ├── API keys             /admin/keys
    ├── Connectors           /admin/connectors
    ├── Thresholds           /admin/thresholds
    ├── Retention & GDPR     /admin/retention
    └── Audit log            /admin/audit
```

**Navigation:** persistent 240 px left rail (collapsible to a 56 px icon rail) + a 56 px top bar carrying global search (`⌘K`), the live connection indicator, the theme toggle, and the user menu. Role gating per [rules.md](rules.md#6-security-and-privacy-rules): `viewer` sees Overview/Threats/Explore/Models read-only; `admin` additionally sees Admin.

**Route guard rule:** the frontend hides what a role cannot use, but the server enforces it (R-52). A deep link to a forbidden route renders a 403 state, not a redirect loop.

## 4. Page specifications

### 4.1 Overview — `/`

Purpose: "is anything happening, and is AEGIS itself healthy?"

```
┌──────────────────────────────────────────────────────────────────────────┐
│  [status pill: LIVE · 1,204 flows/s]      Last 24 h ▾      ⤓ Export      │
├────────────┬────────────┬────────────┬────────────┬──────────────────────┤
│ CRITICAL   │ HIGH       │ MEDIUM     │ OPEN ALERTS│ MEAN TIME TO VERDICT │
│    3       │   17       │   142      │    86      │      41 s            │
│  ▲ vs 24h  │  ▼ vs 24h  │  –         │            │  target ≤ 60 s       │
├────────────┴────────────┴────────────┴────────────┴──────────────────────┤
│  Alert volume by severity — stacked area, 24 h, brushable                │
├───────────────────────────────────────────┬──────────────────────────────┤
│  Top attacked entities (host / user)      │  Threat family mix — bars    │
│  1. web-07.prod      14 alerts  CRITICAL  │  DDoS        ████████ 41     │
│  2. j.rivera@corp     9 alerts  HIGH      │  Brute force ██████ 31       │
│  3. db-02.prod        6 alerts  MEDIUM    │  Recon       ████ 22         │
├───────────────────────────────────────────┴──────────────────────────────┤
│  Detection pipeline health: ingest ▸ score ▸ correlate ▸ notify          │
│  each stage: throughput, p95 latency, lag · red if budget exceeded       │
└──────────────────────────────────────────────────────────────────────────┘
```

- KPI tiles: value at 32 px semibold, delta vs. previous period at 12 px with ▲/▼, sparkline optional.
- The pipeline health strip is a first-class element, not a footer. When AEGIS itself is degraded the analyst must know that the quiet screen means "broken", not "safe".
- Auto-refresh 5 s for KPI tiles; charts refresh 15 s. Both pause when the tab is hidden.

### 4.2 Alerts — `/alerts`

```
┌ Filters ───────────────────────────────────────────────────────────────┐
│ severity: [critical][high][medium][low]   family: ▾   status: open ▾   │
│ entity: ______   time: last 24 h ▾   sort: score ▾    ⌘K quick filter  │
├────────────────────────────────────────────────────────────────────────┤
│ ● CRITICAL  Port sweep from 10.4.11.9 → 1,204 dst ports   score 0.96   │
│             Reconnaissance · web-07.prod · 2 min ago · 41 occurrences   │
│ ● HIGH      Repeated auth failure then success · j.rivera  score 0.88   │
│             Credential abuse · 14 min ago · 6 occurrences               │
│ ○ MEDIUM    Periodic outbound beaconing · api-03 → 45.83.2.11  0.61     │
│             Exfiltration · 22 min ago · 12 occurrences                  │
└────────────────────────────────────────────────────────────────────────┘
```

- Left severity rail: 3 px colour bar **plus** the severity word.
- Row content hierarchy: severity label → one-line summary in plain language → family · entity · age · occurrences.
- Bulk selection with checkbox column; bulk actions limited to what the role may do (R-53).
- Virtualised list; the queue is expected to hold thousands of rows.
- Real-time insertion prepends new rows with a 200 ms highlight; if the user has scrolled, a pinned "3 new alerts ↑" pill appears instead of shifting content under the cursor.

### 4.3 Alert detail — `/alerts/:id`

The most important screen in the product. Four stacked zones, verdict always visible:

```
┌ Verdict bar (sticky) ──────────────────────────────────────────────────┐
│ CRITICAL · score 0.96 · Reconnaissance · web-07.prod · 14:02:11Z       │
│            [1 True positive] [2 False positive] [3 Benign]  Escalate ▸ │
├ 1. Why we flagged this ────────────────────────────────────────────────┤
│ Top contributing signals (SHAP / attention)                            │
│  ▸ dst_port_count 1,204   baseline 12    ████████████████████  0.41    │
│  ▸ syn_flag_ratio  0.94   baseline 0.31  ██████████████        0.28    │
│  ▸ flow_duration   0.02s  baseline 1.8s  █████████             0.17    │
│ Model: flownet@1.4.2 · evidence window: 14:01:02Z – 14:02:11Z          │
├ 2. Timeline ───────────────────────────────────────────────────────────┤
│  13:58 ──────┬───────────┬──────────┬──── 14:04                        │
│              ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮  flow rate, anomaly score overlaid        │
│              ↑ first anomalous window                                  │
├ 3. Raw evidence ───────────────────────────────────────────────────────┤
│  [Flows 50] [Log lines 200] [Related alerts 3]                        │
│  timestamp        src        dst         dport  proto  bytes  flags    │
│  14:02:11.204     10.4.11.9  10.4.20.1   22     TCP    0      SYN      │
│  … (virtualised, sortable, copyable, CSV export)                       │
├ 4. Context ────────────────────────────────────────────────────────────┤
│  Entity: web-07.prod · first seen 41 d ago · 3 prior alerts (2 FP)     │
│  History on this family: analyst marked this FP twice in 30 d ⚠        │
└────────────────────────────────────────────────────────────────────────┘
```

Non-negotiables:

- The verdict bar is sticky and reachable without scrolling. Keyboard verdicts `1`/`2`/`3`.
- If explanation generation failed, zone 1 renders an explicit `explanation_unavailable` state with the reason — never a blank panel or a fabricated reason (R-70).
- If the evidence window has expired past retention, the panel says `evidence expired at <date>` and the alert is not deletable from history.
- The "history on this family" hint is how the product earns trust: it tells the analyst the model has been wrong here before.

### 4.4 Traffic explorer — `/traffic`

- Top: brushable time-series of flow volume with the composite anomaly score overlaid on a second axis; brushing filters everything below.
- Left: entity table (host / user / service) with alert counts, sortable.
- Right: D3 force-directed entity graph — nodes are entities sized by flow volume, edges weighted by flow count, node fill by peak severity. Hover shows a tooltip; click pins an entity and filters the whole page.
- Graph controls: severity filter, min-flow threshold, "show only alerted entities" toggle, and a static-layout fallback for >2,000 nodes (a force simulation at that size is unusable — we switch to a ranked adjacency matrix and say so).

### 4.5 Logs — `/logs`

- Streaming tail with template clustering: identical Drain3 templates collapse into one row with a count, so 10,000 identical lines become "×10,000".
- Anomalous templates are highlighted with the severity colour **and** a left border.
- Clicking a cluster expands the raw lines and jumps to the alert that referenced them, if any.
- A live tail must be pausable. An analyst reading a stack trace should not have it scroll away.

### 4.6 Hunt — `/hunt`

- Query input with autocomplete over field names (`src_ip`, `dst_port`, `template_id`, `family`) and operator hints.
- Saved queries per user; recent queries in a dropdown.
- Results table with column picker, CSV export (audited, `responder` and above), and a "create alert from this filter" action.
- Empty results render the executed query and the time range so the analyst can see what was actually searched.

### 4.7 Model ops — `/models` and `/models/drift`

- Version table: model ID, kind, status (`staging`/`active`/`retired`), promoted by/at. Metrics are a separate per-version read so registry history stays lightweight.
- Metric cards per active model: ROC-AUC, PR-AUC, precision, recall at the deployed threshold — each with the value from the recorded eval run and the run date (R-74).
- Version comparison: two models side by side, delta per metric, each run's confusion matrix, and two overlaid score-distribution histograms on a shared 0–1 probability axis, with a legend and each recorded operating threshold marked.
- Evaluation visuals come only from a recorded `eval@2` report: ten equal-width bins cover `[0, 1]` (lower-inclusive, with the final bin including `1.0`); each visual shows its exact run artifact and field. An older report or absent run renders as unavailable. Never derive histogram counts from scalar metrics or fill a missing matrix with zeros.
- Promotion flow is a modal with an explicit confirm typing the model ID; shadow-mode is the default promotion target, direct-to-active requires `admin` plus a written justification field.
- Drift page: PSI per feature as horizontal bars with the 0.25 threshold marked; features over threshold get a red bar and a "retrain recommended" badge.

### 4.8 Admin

Standard CRUD screens built from the shared `DataTable` + `Modal` primitives. Notable specifics:

- **Users & roles:** role changes require confirmation and are audited; a user cannot demote their own last `admin`.
- **API keys:** secret shown exactly once, in a copy-to-clipboard field that is not re-renderable; only a prefix is stored.
- **Thresholds:** current value, source (`default` | `calibrated` | `manual`), last changed by/at, and a preview of how many alerts the new value would have produced over the last 7 days **before** saving.
- **Audit log:** append-only, filterable, exportable; visibly non-editable (no edit affordance anywhere).

### 4.9 Authentication — session gate

- With no valid session, show a focused sign-in surface instead of mounting data screens; after sign-in, preserve the requested route. Sign-out clears the tab-scoped session.
- The form uses operator-provisioned credentials. Production bootstrap credentials come from a secret manager; there is no built-in demo user or default password.
- A first-administrator setup form is offered only when `AEGIS_DEV_AUTH_SETUP_ENABLED=true` in a private development environment. It warns that the first account has admin permissions and that the in-memory account is cleared when the backend process restarts.
- Access and refresh tokens live only in `sessionStorage`; refresh is single-use and rotates. A failed refresh or HTTP 401 returns to sign-in and reopens the stream with the new credential. A 403 or WebSocket 4403 is a permissions refusal and does not sign the operator out; WebSocket 4401 clears the session.
- The sign-in screen follows the same dark/light tokens as the console, keeps visible labels and errors, and never echoes a password or token.

## 5. Design tokens

The brand palette is two colours: Stream Blue `#1E56CD` and Vanilla Cloud `#FDF8F2` (memory.md D-099). Nothing else is used: no tint, no third colour, no translucent overlay. Dark is the default: a Stream Blue field with Vanilla Cloud type. Light is the same pair inverted: a Vanilla Cloud field with Stream Blue type. Both pairs measure 6.09 : 1 against each other, so either theme reads at WCAG AA. Surfaces match the field and are separated by borders, because the palette has no second tint. Muted text is the same colour as primary text, so hierarchy comes from size and weight, not colour. All ratios below were computed with the WCAG relative-luminance formula against the stated background.

### 5.1 Colour — dark theme (default)

|Token|Value|Contrast|Use|
|---|---|---|---|
|`bg.base`|`#1E56CD`|—|App background|
|`bg.surface`|`#1E56CD`|—|Cards, panels, tables (separated by `border.default`)|
|`border.default`|`#FDF8F2`|6.09 : 1 on `bg.base` · 6.09 : 1 on `bg.surface`|Hairlines and control boundaries; never the sole separator for essential info|
|`text.primary`|`#FDF8F2`|6.09 : 1 on `bg.base` · 6.09 : 1 on `bg.surface`|Body, headings|
|`text.muted`|`#FDF8F2`|6.09 : 1 on `bg.base` · 6.09 : 1 on `bg.surface`|Secondary labels, metadata (same colour as primary)|
|`accent`|`#FDF8F2`|6.09 : 1 on `bg.base` · 6.09 : 1 on `bg.surface`|Links, focus, primary actions|

### 5.2 Colour — light theme

|Token|Value|Contrast|Use|
|---|---|---|---|
|`bg.base`|`#FDF8F2`|—|App background|
|`bg.surface`|`#FDF8F2`|—|Cards, panels, tables (separated by `border.default`)|
|`border.default`|`#1E56CD`|6.09 : 1 on `bg.base` · 6.09 : 1 on `bg.surface`|Hairlines and control boundaries (WCAG 1.4.11)|
|`text.primary`|`#1E56CD`|6.09 : 1 on `bg.base` · 6.09 : 1 on `bg.surface`|Body, headings|
|`text.muted`|`#1E56CD`|6.09 : 1 on `bg.base` · 6.09 : 1 on `bg.surface`|Secondary labels (same colour as primary)|
|`accent`|`#1E56CD`|6.09 : 1 on `bg.base` · 6.09 : 1 on `bg.surface`|Links, focus, primary actions|

### 5.3 Severity palette

Severity has six levels, and the palette has two colours, so **colour does not tell the levels apart**. Each level is written out in words, and the filled and outlined badges differ by shape as well as by the word. The base value is the fill, border, or chart mark, and also the 3 px alert rail; the text value is for any text rendered on a background.

|Severity|Base (fill / border / chart)|Text|Label|Badge|
|---|---|---|---|---|
|`critical`|`#FDF8F2` dark · `#1E56CD` light|`#FDF8F2` dark · `#1E56CD` light — 6.09 / 6.09|`Critical`|Filled|
|`high`|`#FDF8F2` dark · `#1E56CD` light|`#FDF8F2` dark · `#1E56CD` light — 6.09 / 6.09|`High`|Filled|
|`medium`|`#FDF8F2` dark · `#1E56CD` light|`#FDF8F2` dark · `#1E56CD` light — 6.09 / 6.09|`Medium`|Outlined|
|`low`|`#FDF8F2` dark · `#1E56CD` light|`#FDF8F2` dark · `#1E56CD` light — 6.09 / 6.09|`Low`|Outlined|
|`info`|`#FDF8F2` dark · `#1E56CD` light|`#FDF8F2` dark · `#1E56CD` light — 6.09 / 6.09|`Info`|Outlined|
|`benign`|`#FDF8F2` dark · `#1E56CD` light|`#FDF8F2` dark · `#1E56CD` light — 6.09 / 6.09|`Benign`|Outlined|

_Ratios are `on bg.base` / `on bg.surface`. Every text value clears WCAG AA (≥ 4.5 : 1) on both surfaces in both themes._

**Badge rule.** A severity badge is one of two shapes. Critical and high are filled with the foreground colour and carry the ground colour as text. Medium, low, info and benign are outlined with the foreground colour and carry the foreground colour as text. The filled badge text is `--color-on-severity`: `#1E56CD` on dark and `#FDF8F2` on light. Measured on the fill: critical 6.09, high 6.09, medium 6.09, low 6.09, info 6.09, benign 6.09, all ≥ 4.5 : 1. White text on these fills fails (1.00 on the dark fill) and is prohibited.

**Charts.** Six severity series cannot be told apart by colour. Any chart that plots more than one severity needs a legend, direct labels, or a pattern in addition to the colour.

**Focus ring.** 2 px `accent`, offset 2 px. Measured against the adjacent background: 6.09 : 1 (dark) and 6.09 : 1 (light) — above the 3 : 1 non-text requirement.

### 5.4 Typography

The UI uses Inter throughout, in sentence case, with uppercase reserved for short labels and the top navigation. Data (IPs, hashes, log lines, scores) uses JetBrains Mono.

| Token          | Size / line-height                    | Weight | Use                                       |
|---|---|---|---|
| `font.display` | Inter, system-ui fallback             | —      | Display headings and KPI titles           |
| `font.sans`    | Inter, system-ui fallback             | —      | All UI text                               |
| `font.mono`    | JetBrains Mono, ui-monospace fallback | —      | IPs, ports, hashes, log lines, scores     |
| `type.hero`    | 64 / 68                               | 600    | Landing page headline                     |
| `type.stat`    | 48 / 52                               | 600    | Landing page figures                      |
| `type.display` | 32 / 36                               | 600    | KPI values                                |
| `type.h1`      | 24 / 32                               | 600    | Page titles                               |
| `type.h2`      | 18 / 26                               | 600    | Section headings                          |
| `type.body`    | 14 / 20                               | 400    | Default text                              |
| `type.body-sm` | 13 / 18                               | 400    | Table cells, dense lists                  |
| `type.caption` | 12 / 16                               | 400    | Metadata, axis labels — never below 12 px |

Minimum text size is 12 px. Numeric columns use tabular figures so values align vertically.

### 5.5 Spacing, radius, elevation

- **Spacing scale (4 px base):** 4, 8, 12, 16, 24, 32, 48, 64. No off-scale values.
- **Radius:** 4 px inputs and badges, 8 px cards, 12 px modals, 999 px pills.
- **Elevation:** flat by default. Elevation is reserved for overlays — dropdowns, modals, toasts, command palette. Cards on a page use `border.default`, not a shadow.
- **Density modes:** comfortable (row 44 px) and compact (row 32 px), persisted per user. Compact is the default for tables with more than 50 rows.

### 5.6 Iconography

Lucide, 16 px in dense contexts and 20 px elsewhere, always with an accessible label when the icon is the only content. Severity additionally uses the word label from §5.3.

## 6. Component library

All primitives live in `dashboard/src/components/ui` and are the only approved building blocks (R-22, R-27).

| Component                                    | Contract                                                                                                                                                         |
|---|---|
| `Button`                                     | variants: `primary` `secondary` `ghost` `danger`; sizes: `sm` `md`; always renders a real `<button>`; `loading` state swaps the label for a spinner and disables |
| `Badge`                                      | severity or neutral; enforces the badge rule in §5.3                                                                                                             |
| `Card` / `Panel`                             | titled container with optional actions slot and a built-in loading/empty/error state                                                                             |
| `DataTable`                                  | virtualised, sortable, column picker, row selection, sticky header, empty state                                                                                  |
| `Modal` / `ConfirmDialog`                    | focus trap, `Esc` to close, returns focus to the trigger; destructive confirms require typing the target name                                                    |
| `SeverityPill`, `ScoreMeter`                 | score meter is a 0–1 bar with the band threshold marked                                                                                                          |
| `Timeline`, `TimeSeriesChart`, `EntityGraph` | D3-based, all accept a `reducedMotion` flag                                                                                                                      |
| `Toast`                                      | success / warning / error; auto-dismiss except errors                                                                                                            |
| `CommandPalette`                             | `⌘K`; navigates, filters, and runs saved hunts                                                                                                                   |
| `EmptyState`, `ErrorState`, `Skeleton`       | required by R-29                                                                                                                                                 |

## 7. Data visualisation

| Chart                         | Library  | Spec                                                                                                               |
|---|---|---|
| Alert volume by severity      | Chart.js | Stacked area, severity palette, brushable x-axis, y-axis starts at 0 — never truncate a count axis                 |
| Flow volume + anomaly score   | D3       | Dual axis, explicit axis labels and units, score axis 0–1 fixed                                                    |
| Entity relationship graph     | D3 force | Node size = flow volume, fill = peak severity, edge width = flow count; ≥ 2,000 nodes switches to adjacency matrix |
| Threat family mix             | Chart.js | Horizontal bars, sorted descending, counts labelled at bar end                                                     |
| Drift PSI                     | Chart.js | Horizontal bars with a 0.25 threshold marker line                                                                  |
| Score distribution comparison | D3       | Two overlaid histograms with a legend and the threshold marked                                                     |

Chart rules: every axis is labelled with units; every series has a legend entry; colours come only from the severity palette or the categorical chart ramp; no 3D, no pie charts with more than four slices, no dual axes without labelled units on both.

## 8. States, motion, responsiveness

### 8.1 Required states

| State                  | Treatment                                                                                                                        |
|---|---|
| **Loading**            | Skeletons matching the final layout. Spinners only for actions under 1 s.                                                        |
| **Empty**              | Say what is empty and what to do: "No open critical alerts in the last 24 h." + a link to widen the filter. Never a blank panel. |
| **Error**              | What failed, whether it is retrying, and a Retry action. Never a raw stack trace in the UI.                                      |
| **Partial / degraded** | Explicit badge: `partial evidence — log model unavailable`. Partial results are labelled, never presented as complete.           |
| **Stale**              | If live data stops arriving, show `last update 2 m ago` in the header rather than silently showing old numbers.                  |
| **Forbidden**          | 403 state explaining the required role and how to request it.                                                                    |

### 8.2 Motion

- Durations: 120 ms micro-feedback, 200 ms panels, 300 ms page transitions. Nothing over 300 ms.
- Easing: `ease-out` for entering, `ease-in` for leaving.
- **All** motion respects `prefers-reduced-motion: reduce`, which disables animation and swaps the live feed to discrete updates.
- Motion is for continuity (where did this row come from), never decoration.

### 8.3 Responsive breakpoints

| Breakpoint   | Behaviour                                                                                                      |
|---|---|
| ≥ 1440 px    | Full layout, side-by-side panels, entity graph always visible                                                  |
| 1024–1439 px | Panels stack in pairs, nav rail collapses to icons by default                                                  |
| 768–1023 px  | Single column, nav becomes a drawer, tables keep the 4 most important columns                                  |
| < 768 px     | Triage-focused: alert list and alert detail only. A banner states that the full console needs a larger screen. |

The product is desktop-first. Mobile supports the triage loop and nothing else, and says so.

## 9. Accessibility (NFR-09)

Target **WCAG 2.1 AA**, verified in CI where automatable and audited per release.

- **Contrast:** all text pairs in §5.1–§5.3 meet 4.5 : 1; large text and UI components meet 3 : 1. Numbers above are computed, not estimated.
- **Keyboard:** every action reachable and operable by keyboard. Visible focus ring per §5.3. A documented shortcut set (`⌘K`, `j`/`k`, `Enter`, `1`/`2`/`3`, `Esc`, `/`) with an in-app shortcut reference.
- **Screen readers:** semantic landmarks, one `h1` per page, table headers wired via `scope`, live regions (`aria-live="polite"`) for new alerts and toasts, `aria-live="assertive"` for critical alerts only.
- **Not colour alone:** severity = colour + text label (§5.3). Charts have a data-table alternative toggled by a "view as table" control.
- **Motion:** `prefers-reduced-motion` fully honoured (§8.2).
- **Forms:** every field has a persistent visible label (placeholder is not a label), inline validation with `aria-describedby`, errors announced.
- **Testing:** `eslint-plugin-jsx-a11y` in CI, `@axe-core/react` assertions in component tests, and one manual screen-reader pass per release with the result recorded in the release note.

## 10. Content and copy guidelines

- **Plain language, present tense.** "Repeated failed logins followed by a success from a new host" — not "anomalous authentication pattern detected".
- **Numbers with units and a baseline.** "1,204 destination ports vs. baseline 12" beats "high port count".
- **No hedging in the verdict bar.** The score and the band are stated; uncertainty is expressed by the confidence qualifier (`partial evidence`), not by vague adjectives.
- **Never blame the user.** "This query returned no results for the last hour" — not "Invalid search".
- **Never fabricate.** If the model cannot explain, the UI says so. Inventing a plausible reason is a defect (R-06, R-70).
- **Timestamps** in UTC with a local-time tooltip, always with the date when older than 24 h.
- **Glossary:** domain terms (`PSI`, `beaconing`, `half-open`) link to a definition tooltip; the same glossary lives in [memory.md](memory.md#glossary).

## 11. Design deliverables and next steps

| Deliverable                                      | Owner       | Status                                                                                                                                                         |
|---|---|---|
| Design tokens as Tailwind config + CSS variables | Design/FE   | Built — T-401 DONE                                                                                                                                             |
| UI primitive components (§6)                     | FE          | Built — T-402 DONE                                                                                                                                             |
| Alert triage screen (highest value)              | FE          | Built — T-404 DONE                                                                                                                                             |
| Overview dashboard                               | FE          | Built — T-403 DONE                                                                                                                                             |
| D3 entity graph + time-series                    | FE          | Built — T-406 DONE                                                                                                                                             |
| Accessibility audit of the first three screens   | Design      | Automated axe and keyboard checks complete (T-413); manual screen-reader pass remains unrun, see [release-note.md](release-note.md#accessibility-t-413-nfr-09) |
| Authentication gate and first-admin setup (§4.9) | FE/platform | Sign-in/session flow built (T-417); human visual sign-off pending. Durable account and refresh state are follow-up infrastructure (D-081).                     |

Implementation status is tracked in [task.md](task.md); this document remains the source of truth for intended behaviour. A component that disagrees with §5 or §6 is wrong, not the document.

## 12. Change log

| Date       | Version | Change                                                                                                                                                                                                                                                                                                                                                         |
|---|---|---|
| 2026-10-02 | 0.1     | Initial UI/UX specification. Severity and accent tokens validated against measured WCAG contrast ratios.                                                                                                                                                                                                                                                       |
| 2026-10-07 | 0.2     | Clarified §4.7's recorded-only comparison: metadata-only version list, per-version metrics read, eval@2 ten-bin equal-width histogram, shared overlay with both thresholds and run provenance, and visible unavailability for missing/older reports; see D-080. Refreshed §11 implementation statuses and kept the manual screen-reader pass explicitly unrun. |
| 2026-10-07 | 0.3     | Added §4.9's session gate, safe first-admin setup, tab-scoped token lifecycle, and distinction between expired credentials and permission refusals; no default account. Accounts and refresh state remain process-local (D-081).                                                                                                                               |
| 2026-10-17 | 0.4     | Restyled to the blue reference: blue-only palette (§5), Inter for UI text, plain cards in place of the decorative overview. Removed the connection indicator, reconnect banner, staleness stamps, and explanatory text from every screen (§6, §8.1). Added an unauthenticated landing page at `/`; other paths show sign-in.                                   |
| 2026-10-17 | 0.5     | Rebuilt the landing page to the reference layout: hero headline, halftone art field (artwork supplied as `dashboard/public/landing-hero.jpg`), three feature cards, primary and secondary CTAs. Added `type.hero` (64/68) and `type.stat` (48/52) to §5.4.                                                                                                     |
| 2026-10-17 | 0.6 | Re-based the palette on the brand sheet: Mariana Blue field and Grey type in dark, Dawning Mist field and Deep Blue accent in light. Replaced the cobalt values in §5.1 and §5.2; updated the severity text and badge ratios and the focus ring to match. |
| 2026-10-17 | 0.7 | Toned the severity hues down to sit with the brand palette and kept each text variant at 4.5:1 or better. Replaced the symbol glyphs with the severity word, so every severity is written out in words; the §5.3 Glyph column is now Label. |
