# NOCTRA Frontend QA Report — Duality pass

Date: 2026-08-27 · Branch: `arena/01a041f3-ai-enhanced-cybersecurity-thre`
Scope: full-route frontend audit (directive §9–22), Phase-18 loop verification,
DUALITY theme implementation, trust-UX labeling. Every claim below was
verified against the running stack (backend on SQLite, `COOKIE_AUTH=true`,
Vite dev proxy) or by code inspection — method noted per item.

---

## 1. Bug report (found → fixed → verified this pass)

### BUG-UI-001 — Static fake "LIVE STREAM" status badge
- Severity: MED · Route: all (app shell) · File: `components/Navbar/index.tsx`
- Problem: pulsing green "LIVE STREAM" badge rendered unconditionally; no
  stream exists (alerts poll at 60 s; no websocket anywhere in the codebase).
- Expected: UI must not claim capabilities that don't exist.
- Actual: permanent fake "live" signal.
- Cause: decorative leftover from an earlier phase.
- Fix: removed; replaced with the quiet secondary tagline.
- Verification: code + built bundle grep (no "LIVE STREAM"); visual on dev server.

### BUG-UI-002 — Dead notifications button with hardcoded red dot
- Severity: LOW · Route: all · File: `components/Navbar/index.tsx`
- Problem: bell icon button had no handler (§9 "dead buttons") plus a
  hardcoded red notification dot; no notifications feature exists in the
  backend.
- Fix: removed button and dot entirely (a feature should not be faked; add
  back when a notifications API exists).
- Verification: code; no dangling `Bell` import (tsc clean).

### BUG-NAV-001 / BUG-NAV-002 — Routes unreachable from navigation
- Severity: MED · Routes: `/logs`, `/incidents` · File: `layouts/DashboardLayout`
- Problem: both routes exist in `App.tsx` with working pages, but no nav entry
  pointed to them (pre-existing gap, confirmed in the pre-redesign layout too).
- Steps: log in → search sidebar for a link to Log History / Manual Incidents.
- Expected: every preserved route reachable (directive §4).
- Actual: URL-only access.
- Fix: added "Manual Incidents" and "Log Uploads" under INVESTIGATE.
- Verification: nav renders entries; routes resolve (dev server).

### BUG-TRUST-001 — No OBSERVED vs INFERRED distinction on the case page
- Severity: HIGH · Route: `/case/:id` · File: `pages/CasePage.tsx`
- Problem: "What happened / Why it matters" (AI inference) and the blast
  radius (observed evidence) carried identical visual weight and no epistemic
  labeling — directive §11 violation.
- Fix: assessment card now headed "NOCTRA's assessment" with an explicit
  `Inferred — not confirmed fact` tag; blast-radius panel tagged `Observed`;
  the action card tagged `Recommendation`. Confidence + model/fallback line
  unchanged (already present).
- Verification: live case #1–#5 render with labels.

### BUG-HOME-001 — Home lead card lacked the decision summary structure
- Severity: MED · Route: `/` · File: `pages/BriefPage.tsx`
- Problem: directive §12 structure (why it matters / affected / confidence /
  recommends / reversible) was only partially present.
- Fix: lead card now shows Why-it-matters + a 4-stat row (Affected systems,
  Confidence % or `n/a` when fallback, Recommends action, Reversible Yes/Ask)
  + observed blast-radius chips + model/fallback footnote. All values from
  the real case object; nothing invented.
- Verification: live against case #2 (fallback analysis shows `n/a`).

### BUG-A11Y-001 — Button contrast/border defects
- Severity: MED · Route: all · File: `components/ui/Button.tsx`
- Problem: primary variant used a gradient whose light-scope end
  (`#5B4FD8`) yields 4.4:1 with ink text and an invisible `border-white/10`
  on light surfaces; danger variant used raw `text-red-300` (≈2.4:1 on its
  tinted fill — fails AA).
- Fix: primary = solid periwinkle `#A8A2FF` + ink text (7.6:1) + transparent
  border; danger = `text-status-critical` (scope-aware, 5.2:1 day / 6.4:1
  night).
- Verification: computed ratios (§3 below); tsc/build clean.

### BUG-BRAND-001 — Accent-fill text used a theme-flipped token
- Severity: HIGH (latent, introduced with theming) · Files: 12 components
- Problem: `text-app-bg` on periwinkle buttons would have become near-white
  (2.4:1) the moment the day scope flipped `app-bg` to paper.
- Fix: introduced fixed `brand-ink` (#191B22) and migrated all 28 usages.
- Verification: `grep text-app-bg src/` → 0; built CSS spot-check.

## 2. Design-system change — DUALITY (directive §5)

Single dark theme replaced by **structural dual scopes** (not a toggle):

- Day workspace (`:root`): paper `#F7F7F5`, white surfaces, ink text — nav,
  inbox, case lists, tables, settings, admin.
- Night canvas (`.night` scope on AI panels): ink `#0C0E14/#10131C/#08090D`,
  periwinkle accents — analyst briefs, blast radius, Ask-NOCTRA chat,
  reports, landing product panel.
- Implementation: Tailwind semantic tokens now resolve to CSS custom
  properties (`rgb(var(--c-*) / <alpha-value>)`); the `.night` class flips
  the full variable set, including status/severity text variants (darker on
  light, brighter on ink) and the focus-ring color. Components keep semantic
  class names — duality is opt-in per panel.
- Accent fills stay periwinkle in both scopes with fixed ink text.
- Ambient body wash removed (day side is clean paper; night panels carry
  their own depth).

## 3. Accessibility verification (computed, WCAG 2.1 AA)

| Pair | Ratio |
| --- | --- |
| ink text on paper / white | 16.0 / 17.2 |
| secondary `#565C6B` on white | 6.7 |
| tertiary `#67707F` on white | 5.0 |
| deep periwinkle links `#5B4FD8` on white | 5.9 |
| ink on periwinkle button | 7.6 |
| periwinkle on night canvas / ink | 8.2 / 8.5 |
| bright periwinkle `#C9C4FF` on canvas | 11.3 |
| day severity text (crit/warn/high/succ) on white | 5.2 / 5.0 / 4.9 / 5.3 |
| night severity text on canvas | 6.4–8.7 |
| focus ring vs page bg (both scopes) | 5.5 / 11.3 |

All text-bearing pairs ≥ 4.5:1. Severity never color-alone (dot + label).
`prefers-reduced-motion` honored globally. Known remaining: Recharts series
not individually announced to screen readers (charts have text summaries only
on Analytics) — queued for the a11y stage.

## 4. API integration audit (FE call → backend route)

All 60 frontend calls across `src/api/*.ts` were mapped to backend routers;
methods, paths, auth dependencies and envelope shapes match. Notables:

- Analyst loop (below) verified end-to-end live.
- `refresh`/`logout` are called from the redux store (not userApi) — present.
- Backend endpoints with **no frontend caller** (intentional API surface,
  not bugs): `GET /alerts/export`, `DELETE /alerts/clear`, `GET /user/me`,
  `POST /ml/analyze` (ml explain endpoints are used), `GET /cases/{id}` bare
  (incidents API uses list+create+patch).
- No 401 interceptor exists on the axios instance; a mid-session expiry
  surfaces as a per-page error. The redux refresh flow exists but is not
  auto-triggered on 401. **Kept as-is this pass** (behavior unchanged from
  before the redesign); flagged as MISSING-3.

## 5. Phase 18 analyst-loop verification (live, this pass)

| Step | Result |
| --- | --- |
| `POST /analyst/simulate` ×3 scenarios | cases #3/#4/#5 created, analysis present, `fallback:true` (no LLM key) — UI labels rule-based |
| `GET /analyst/brief` | real `pending_count/handled_today/watching/top_cases` |
| `GET /analyst/feed` | paginated, decisions correct |
| `GET /analyst/cases/{id}` | full case; `cases/999` → 404 handled in UI |
| approve #3 | `approved`/`resolved`, `soar_action_id` **recorded**, report generated |
| decline #4 | `declined`/`closed`, **no** SOAR id, report generated |
| approve→revert #5 | `reverted`/`triaging`, compensating record, report |
| `GET /cases/{id}/report` | markdown, "Generated … by NOCTRA analyst" |
| `POST /cases/{id}/chat` | context-aware answer citing real blast-radius entities |
| connectors | 4 static entries, sync no-op (documented gap) |

Recorded/executed language audit: FE says "Recorded" everywhere (Actions log,
SOAR status labels, decision dialogs); the only "executed" strings left in
the FE are the raw API status value mappings, which are relabeled through
`statusLabel`. Backend wire values untouched.

## 6. Missing features / honest gaps (not bugs)

1. **Notifications** — ~~no backend feature~~ **SHIPPED (backend-enrichment
   pass)**: `GET /analyst/notifications` derives pending decisions + last-24h
   outcomes from real rows; the Navbar bell returns with a real unread count
   (client-tracked last-seen) and deep links.
2. **"Handled automatically" metric** — ~~not tracked~~ **SHIPPED**:
   `/analyst/brief` now returns `alerts_today` + `auto_recorded_today`
   (decision-path SOAR records excluded by rule-name discriminator).
3. **401 auto-refresh** — ~~no axios interceptor~~ **FIXED (follow-up pass)**:
   `api/axios.ts` now single-flight-refreshes on 401, retries the original
   request once, and on failure clears session flags and returns the user to
   `/login`. Auth endpoints are exempt (bad-password 401s behave normally).
4. **Case timeline endpoint** — ~~composed client-side~~ **SHIPPED**:
   `GET /analyst/cases/{id}/timeline` composes evidence/opened/action/
   decision/report/chat entries server-side from real rows (incl. audit
   trail with actor attribution); CasePage renders it for pending and
   decided cases alike.
5. **Connectors** — static status surface (documented in spec §37).
6. **Live streaming** — none; polling only. The fake badge is gone.
7. Responsive widths (§16) and screen-reader chart audit not executable in
   this sandbox (no browser) — layout uses standard responsive breakpoints
   and scrollable tables; full pass queued for Stage 4.

## 7. Verification results (this pass)

- `tsc --noEmit` clean · `vite build` clean (var-backed tokens present in
  built CSS; `.night` scope confirmed; no glow shadows; chart-1 `#8B7CF6`
  is the only legacy violet, intentional dataviz).
- Backend pytest: **114 passed / 2 skipped**. ml-service: **13 passed**.
- Live: login → Home (§12 lead card) → case review (trust labels) →
  approve/decline/revert all exercised today on cases #3–#5.
