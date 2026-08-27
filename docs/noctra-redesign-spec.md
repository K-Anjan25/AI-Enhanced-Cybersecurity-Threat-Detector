# NOCTRA — Product, Brand, UX/UI & Frontend Redesign Specification

Status: **Active** — Stage 1 implemented (see §32 roadmap). Supersedes the AXIOM AI
identity (Phase 20) and the Obsidian Ember exploration (Phase 17). NOCTRA is the
final brand.

---

## 1. Executive Summary

This repository built a capable multi-tenant SOC platform: ML detection, entity
graphs, SOAR, rules, reputation, audit, analytics, Kafka streaming, and — in
Phase 18 — an autonomous analyst loop (`simulate → brief → feed → case →
approve/decline/revert → report`). The frontend, however, still presents a
generic SOC cockpit: the primary surfaces answer *"how many alerts do I have?"*
instead of *"what does NOCTRA need me to know?"*

This redesign re-centers the product on the **Case** and the **analyst
relationship**: NOCTRA is an employee who investigates, explains in plain
English, shows what is affected, proposes one reversible action, and asks for a
human decision. Everything technical survives, reframed as **Advanced /
deep-dive** experience behind progressive disclosure.

Stage 1 (this pass) ships: the NOCTRA brand (full stack, including the LLM
persona and generated reports), a new visual identity (dark-first ink
foundation, periwinkle accent), the new navigation architecture, the
Analyst-Inbox home, and trust-accurate language ("recorded", never "executed",
for record-only SOAR).

## 2. Repository Understanding

**Stack.** FastAPI backend (`backend/app`, `/api/v1`), scikit-learn ml-service
(`ml-service/app`, port 8001), React 18 + Vite + Tailwind v3 + Redux Toolkit +
react-query dashboard (`dashboard/src`), Postgres, optional Kafka, Docker
Compose + k8s manifests, pytest (114 backend / 13 ml) and `tsc + vite build`
gating in CI.

**Auth model.** JWT access/refresh; `COOKIE_AUTH=true` in compose/k8s means
httpOnly cookies — the frontend never holds tokens (`utils/token.ts` keeps only
an `auth_status` flag). ABAC: roles ADMIN/ANALYST/USER × clearance levels;
`/me` returns the effective permission set which gates routes and nav.

**Data isolation.** Every tenant table carries `org_id`; lists/scoping are
org-filtered server-side. Admins get cross-tenant views under `/admin/*`.

**Detection pipeline.** `POST /analyze` and `POST /upload-logs` → ml-service
predict (network IsolationForest normalized to 0..1; log TF-IDF classifier;
heuristic fallbacks when the service is down) → alert persisted → entity
extraction/linking → MITRE mapping → threat-intel enrichment → SOAR rule
evaluation → record-only `SoarAction` rows + Kafka events.

**Analyst loop (Phase 18).** `services/scenario.py` fabricates realistic
incidents (credential leak T1078, phishing T1566, exfiltration T1048,
compromised API key T1098), builds a real blast-radius graph, asks the LLM
(`llm_client`, Anthropic Messages API with a deterministic templated fallback)
for the analysis contract `{headline, what_happened, why_it_matters,
blast_radius_summary, recommended_action{action_type,target,rationale,undo},
confidence, model, fallback}`, and stores it on a `Case` (`kind='analyst'`).
Human transitions approve/decline/revert; approve runs the action through
SOAR (**record-only**), stores `soar_action_id`, and generates a markdown
report; every transition writes an append-only audit row.

**Honest-constraints found in audit (already fixed on this branch):** network
severity bands were mis-mapped (all network alerts read LOW), self-registration
could grant ADMIN, error details were swallowed app-wide, 9 Tailwind tokens
were dead, the profile never loaded (react-query `meta` misuse). The redesign
builds on a corrected base: **backend 114 passed / 2 skipped, ml 13 passed,
dashboard builds clean.**

## 3. Phase 18 Interpretation

The loop the frontend must make obvious:

```
SENSE → REASON → EXPLAIN → BLAST RADIUS → PROPOSE REVERSIBLE ACTION
      → HUMAN APPROVES / DECLINES → RECORD DECISION → REPORT
```

Consequences for design:

- The **unit of work is a Case**, not an alert. Alerts are evidence.
- The **home screen is a decision inbox**, not a KPI wall.
- NOCTRA speaks in the first person, plainly: *"NOCTRA found a credential leak."*
- Every recommendation ships with **why it matters**, **what is affected**,
  **confidence**, and **how to undo it**.
- Decisions are **recorded and reported** — the audit trail and the report are
  product features, not admin afterthoughts.

## 4. Current UX Audit (pre-redesign)

| Finding | Severity | Disposition |
| --- | --- | --- |
| Home ("Dashboard") showed a fake `96/100` posture score, hard-coded "14:15 SQL Injection" alerts, "All Systems Operational" | High — fabricates data | Removed; rebuilt as Analyst Inbox on real `/analyst/brief` data |
| Two competing homes (Brief at `/`, legacy SOC Cockpit at `/dashboard`) with overlapping KPI cards | Medium | Brief becomes **Home**; Cockpit demoted to Investigate deep-dive |
| Language says "Executed"/"Execute actions" although SOAR is record-only | High — trust | Re-worded to "recorded" everywhere (§16) |
| Nav mixed product surfaces and admin ("Inbox & Brief, Cases Queue, Actions Log, Incident Reports, Threat Graph, Alert Telemetry, SOAR Automation, SOC Cockpit") | Medium | Re-grouped into MAIN / INVESTIGATE / AUTOMATE / SYSTEM (§8) |
| `/admin/roles`, `/admin/engine-settings` were unreachable from nav | Medium (fixed earlier) | Now grouped under AUTOMATE/SYSTEM |
| Case page is a single long scroll with the decision gate at the very bottom | Medium | Stage 2: case workspace with sticky decision rail |
| Admin dashboard showed invented metrics ("12 analysts", "84 rules") | Medium (fixed earlier) | Wired to real endpoints |
| Raw `slate/blue` classes on the Phase 19/20 pages broke the token system | Medium | Migrated to tokens in Stage 1 |

## 5. Current Frontend Architecture Audit

```
dashboard/src/
  App.tsx                  # routes + role/permission gating (flat)
  index.tsx                # providers: Redux, react-query, Toast, ErrorBoundary
  layouts/DashboardLayout  # shell: sidebar + navbar + density toggle
  components/ui/*          # 17 primitives (Button, Modal, Toast, …) + index barrel
  components/{BrandLogo,Navbar,PageTransition,ErrorBoundary}
  pages/*                  # 18 route pages (mixed old "admin/*" + new surfaces)
  features/{auth,account,admin,dashboard,entities,incidents}
  api/*                    # 13 axios clients, one per domain
  types/* store/* utils/* validators/* constants/{brand,tableColumns}
```

Strengths: semantic Tailwind tokens, primitive library with a barrel, one API
client per domain, permission-aware routing, error-boundary → audit telemetry.
Weaknesses: page components are giant and self-contained; feature folders are
inconsistent (some domains have `features/`, others live in `pages/`); state is
split between Redux (auth only) and ad-hoc `useState` fetching.

## 6. Product Model

**The Case is the central object.** Everything connects through it:

| Capability | Role in the model |
| --- | --- |
| Alert | Case **evidence** |
| Entity / graph | Case **blast radius** & investigation |
| ML + heuristics | **Senses** raw events |
| LLM analysis | **Reasoning** (brief, why-it-matters, confidence) |
| SOAR | **Proposed & recorded action** (record-only today) |
| Audit log | **Decision history** |
| Report | **Case outcome** (markdown, downloadable) |
| Analytics | **Intelligence** (trends, benchmark) |

A Case answers, in order: What happened? Why does it matter? What is affected?
What does NOCTRA think? What does NOCTRA recommend? What needs my approval?
What happened afterward?

## 7. New Information Architecture

```
PUBLIC      /welcome  /login  /register  /reset-password

PRIMARY     /            Home — Analyst Inbox (greeting, needs-decision lead case)
            /feed        Cases  (URL preserved; label "Cases")
            /case/:id    Case workspace
            /actions     Actions — recorded containment log
            /reports     Reports — generated case reports

INVESTIGATE /alerts      Alerts (evidence stream)
            /entities    Entities & Threat Graph
            /analytics   Analytics (trends, ML benchmark, explain)
            /dashboard   SOC Cockpit (legacy overview, deep dive)

AUTOMATE    /soar        SOAR (actions, playbooks, dry-run)
            /admin/rules Rules            (URL preserved)

SYSTEM      /admin/system-logs   Audit
            /admin/reputation    Reputation
            /admin/engine-settings Engine
            /profile             Your settings
ADMIN       /admin  /admin/users  /admin/tenants  /admin/roles
```

No route is removed; labels change, URLs stay. Deep links keep working.

## 8. Navigation Architecture

Sidebar (collapsible, 264px → 68px):

```
[NOCTRA mark + wordmark]                    [«]

MAIN
  Home            /             Home icon
  Cases           /feed         Inbox        · pending-count pill
  Actions         /actions      ShieldCheck
  Reports         /reports      ScrollText

INVESTIGATE
  Alerts          /alerts       TriangleAlert
  Entities & Graph /entities    Share2
  Analytics       /analytics    BarChart3
  SOC Cockpit     /dashboard    LayoutDashboard

AUTOMATE                (rules:write / admin visible)
  SOAR            /soar         Workflow
  Rules           /admin/rules  ListChecks

SYSTEM                  (audit:read / users:manage visible)
  Audit           /admin/system-logs   ScrollText
  Reputation      /admin/reputation    Ban
  Engine          /admin/engine-settings Settings2
  Users           /admin/users         KeyRound   (admin)
  Tenants         /admin/tenants       Building2  (admin)
  Roles           /admin/roles         ShieldCheck (admin)

[avatar · role]  [density toggle]
```

Rationale: four MAIN items mirror the product loop; everything else is grouped
by verb (investigate / automate / system). Labels were evaluated against the
directive's proposal — "Entities & Graph" replaces separate Entities/Threat
Graph entries because they are one surface today; "SOC Cockpit" kept as the
legacy overview's honest name.

## 9. NOCTRA Brand Strategy

**Brand style system (user-locked, 2026-08-27).**

| Attribute | Value |
| --- | --- |
| Brand style | Intelligence Infrastructure |
| Wordmark | Sora SemiBold, uppercase, slightly extended tracking; sparkle-A detail (exact logo spec, supersedes the interim neo-grotesk lockup) |
| Logo style | Folded-ribbon "N" (blade/origami zigzag), diagonal violet gradient #6C5CE7→#9D7CFF, 4-point insight sparkle #B18CFF; divider lockup |
| Visual language | Editorial Enterprise |
| Interface style | Operational Minimalism |
| Motion style | Purposeful Intelligence (state-change only; reduced-motion honored) |
| Color style | NOCTRA violet gradient family (#6C5CE7 → #9D7CFF → #C9C4FF) |

**Avoid list (hard):** cyberpunk · neon · gaming · hacker · sci-fi · generic
AI purple · generic shield logos · generic lock logos · generic brain logos.
Current state complies: abstract non-shield mark, periwinkle (not deep
"AI purple" — see §15 audit), no glow/neon, gradients flattened, motion
limited to state communication.

**Positioning.** For small companies without a security team, NOCTRA is the
analyst they employ: it watches continuously, explains plainly, acts only with
approval, and writes everything down.

**Personality.** The night-shift analyst: calm, precise, plain-spoken,
accountable. Never alarmist, never cryptic, never flashy.

**Proof points (all real, in-product):** plain-English case briefs; blast
radius from a real entity graph; reversible recommendations with undo steps;
recorded decisions + downloadable reports; full audit trail.

**Name story.** NOCTRA ← *nocturnal* — the analyst who works while you sleep.

## 10. Brand Voice

- Speak like a trusted colleague, third person: **NOCTRA found…**, **NOCTRA recommends…**
- Plain English first; technical terms live behind "Details" in deep-dive views.
- Short sentences. No buzzwords. No ALL-CAPS alarm.
- Never fabricate: numbers, statuses and outcomes must come from the API.
- Calm under pressure: severity is communicated with a label + dot, never a
  flashing red wall.

Do / don't:

| ✅ | ❌ |
| --- | --- |
| "NOCTRA found a credential leak." | "CRITICAL THREAT DETECTION EVENT IDENTIFIED" |
| "3 systems may be affected." | "BLAST RADIUS: 3 ASSETS" |
| "NOCTRA recommends revoking this credential." | "AI ENGINE SUGGESTS REMEDIATION" |
| "Action recorded. You can reverse it." | "Action executed." (record-only) |
| "Nothing needs you right now." | "NO DATA FOUND" |

## 11. Naming / Wording System

| Concept | Wording |
| --- | --- |
| Nav | Home · Cases · Actions · Reports · Alerts · Entities & Graph · Analytics · SOAR · Rules · Audit · Reputation · Engine |
| Case states | Awaiting your decision · Approved — action recorded · Declined · Reversed — compensating record |
| Buttons | Review decision · Approve — record action · Decline · Reverse action · Download report · Simulate incident |
| AI attribution | "NOCTRA's read:" / "Reasoned by {model}" / "Built-in reasoning (ML service unavailable)" |
| Evidence vs inference | "Observed:" (from data) vs "NOCTRA infers:" (from reasoning) — Stage 2 case workspace |
| Loading | "NOCTRA is opening the case…" / "Reading your brief…" |
| Empty | "Nothing needs you right now." / "No cases yet — simulate one to see NOCTRA work." |
| Errors | "Couldn't reach NOCTRA. Retrying is safe." + real API detail |
| Fallback AI | "Built-in reasoning" badge when `analysis.fallback` is true |

## 12. Logo Concept — "The Insight Fold" (exact brand spec, 2026-08-27)

A bold geometric **N** built as a folded ribbon — a blade/origami zigzag with
faceted planes — carrying a 4-pointed **insight sparkle** at its top-right
corner. Reads as: N = name, fold = structured intelligence, sparkle = the
finding/insight. Supersedes the interim "Night Signal" arc-and-dot mark.

Construction (32-grid): one continuous ribbon path (left bar → diagonal →
right bar), diagonal gradient `#6C5CE7` (top-left) → `#9D7CFF`
(bottom-right); two flat facet overlays (white 10%/5%) along the fold line
through the diagonal band — flat vector, no 3D, no bevel, no outer glow.
Sparkle `#B18CFF` at the N's top-right corner.

## 13. SVG Logo Specification

- **Icon:** folded-ribbon N, gradient `#6C5CE7→#9D7CFF` diagonal, sparkle
  `#B18CFF`. Legible at 16px; facet overlays may drop below 20px.
- **Wordmark:** "NOCTRA" — Sora SemiBold, uppercase, tracking +50…+80;
  white `#FFFFFF` on dark, near-black on light (adaptive token). The "A"
  carries a small `#B18CFF` sparkle at its apex.
- **Tagline:** "YOUR AUTONOMOUS SECURITY ANALYST" — Inter Medium, uppercase,
  tracking +180, `#9D7CFF`, beneath the wordmark (logotype color; WCAG
  logotype exemption applies).
- **Lockup:** [icon] [thin vertical divider] [wordmark over tagline];
  clear space = one sparkle height on all sides.
- **Favicon/app icon:** rounded-square badge `#0B0E1A` (r=8) with the mark
  at 85% scale — `public/favicon.svg`; sizes 512/192/64/32/16 via the same
  SVG.
- **Monochrome:** everything `currentColor` (facet overlays off) for loading
  and empty states.
- Implementation: `components/BrandLogo.tsx` (single source; `collapsed`,
  `size`, `withWordmark`, `mono` props). Brand sheet:
  `docs/brand/noctra-logo-sheet.png`.

## 14. Iconography System

Single family: **lucide-react** (already the dependency), 1.5px stroke feel,
sizes 14/16/20. Usage rules: navigation gets icons; severity uses **dot +
label** (never icon-only); AI moments use `Sparkles` sparingly; system status
uses `Activity`. No mixed icon styles, no decorative icon walls.

## 15. Color Exploration

Round 1 (direction) and Round 2 (accent audit — "is violet actually the
strongest NOCTRA-owned accent?", researched 2026-08-27):

**Round 1 — direction**

| Direction | Appraisal |
| --- | --- |
| A. Obsidian Ember (Phase 17: amber/sage on near-black) | Warm, distinctive — but reads "hearth", not "precision"; amber collides with warning semantics. Retired. |
| B. Navy + cyan "AI SOC" | The cliché the directive bans. Rejected. |
| C. Light editorial (Notion-like) + ink | Approachable, but indistinct from generic SaaS. Rejected as primary. |
| D. **Ink + violet-family accent** (chosen) | Deep *neutral* ink (not navy) foundation for calm long sessions; one restrained accent for brand + primary action; hue-separated severity ramp. Distinctive, security-native, not cyberpunk. |

**Round 2 — which accent can NOCTRA own?**

Competitive color claims in security (researched): blue dominates the
category (Zscaler, Fortinet, Microsoft, Palo Alto et al.); red = CrowdStrike
`#FC0000`; orange = Splunk `#FF6600` / Palo Alto; green = Tenable; **deep
saturated purple `#4500b6→#6100ff` = SentinelOne — explicitly positioned as
"autonomous AI security"** — i.e. NOCTRA's exact territory — with Wiz also
building its cloud-security brand on purple.

Elimination: red/amber/green are claimed by severity semantics (a red brand
accent next to a CRITICAL badge is noise); blue is the category cliché the
directive bans; teal sits too close to success-green and is well-populated;
magenta leans toward the critical family. **The violet family is the only hue
with full semantic headroom** — but the *mid-violet* zone (`#7C3AED`–`#8B7CF6`)
is exactly where SentinelOne/Wiz live, and the original Phase-14 NOCTRA violet
(`#7c3aed`) sat squarely in it.

Verdict: **stay in the violet family, but own its light end — periwinkle
`#A8A2FF`.** Rationale: (1) perceptually distinct at a glance from deep

> **Superseded (exact brand spec, 2026-08-27):** the user's final logo
> specification locks the brand to the violet gradient `#6C5CE7 → #9D7CFF`
> with sparkle `#B18CFF` ("do not change the purple gradient to another
> hue"). This supersedes the periwinkle position above by explicit
> direction; the mid-violet proximity risk noted here was accepted.
> App tokens reconciled to the same family (see §16); all AA pairs
> re-verified — `#9D7CFF` on ink 6.2:1, `#6C5CE7` on white 4.86:1 /
> paper 4.53:1, ink text on lavender fills 5.54:1, white on badge 4.86:1.
saturated "AI purple" (reads moonlight-on-ink, matching the night story);
(2) unclaimed in security branding; (3) strongest contrast of the family on
ink — 8.5:1 on `app-bg`, 11.8:1 for `#C9C4FF` (WCAG AA/AAA), vs 5.8:1 for
`#8B7CF6`; (4) no severity-collision. The deeper `#8B7CF6` is demoted to the
first categorical dataviz color, where it earns its keep.

## 16. Final Color System (DUALITY: day workspace + night canvas)

Structural dual scopes, not a toggle. Day workspace (`:root`): paper
`#F7F7F5`, white surfaces, ink text — lists, tables, settings, admin.
Night canvas (`.night` scope): ink surfaces — AI briefs, reasoning, evidence,
blast radius, reports. Semantic Tailwind tokens resolve to CSS custom
properties so both scopes share one component vocabulary; status/severity
text variants flip with the scope (see `docs/noctra-qa-report.md` §3 for the
full computed-contrast table; all text pairs ≥ AA).

Roles (Tailwind token → hex):

| Token | Value | Use |
| --- | --- | --- |
| `app-void` | `#08090D` | deepest layer (scrollback, wells) |
| `app-bg` | `#0C0E14` | page background |
| `app-surface` | `#14161D` | cards, tables |
| `app-surface-raised` | `#1A1D26` | hover/raised |
| `app-subtle` | `#1B1E28` | table headers, input fills |
| `app-navy` (legacy name) | `#10131C` | the "night canvas" editorial panels (Brief lead card, blast radius, reports) |
| `accent-primary` | `#9D7CFF` | lavender (gradient end) — brand, primary buttons, links |
| `accent-secondary` | `#6C5CE7` day / `#C9C4FF` night | deep violet accent text on light; bright lavender on ink |
| `status-success` | `#4CC38A` | approved, healthy |
| `status-warning` | `#E5A54B` | awaiting decision, high severity |
| `status-critical` | `#F26D6D` | critical severity, destructive |
| `content-primary` | `#ECEEF4` | text |
| `content-secondary` | `#A6ACBF` | secondary text |
| `content-tertiary` | `#6E7487` | muted text |
| `line-subtle` / `line-bright` | `#232735` / `#323850` | borders |
| `brand.*` | violet family | legacy aliases remapped |

Severity ramp (dot + label always): LOW `#52B788` · MEDIUM `#E5A54B` ·
HIGH `#F0824F` · CRITICAL `#F26D6D`. Dataviz categorical: `chart-1..5` =
`#8B7CF6, #4FB8A8, #E5A54B, #E77A8B, #7E87A3`. All text-bearing pairs meet
WCAG AA on their surfaces; severity is never color-alone (dot + text label).

Light theme: defined for future (paper `#F7F7F5`, ink text, same accents
darkened); not shipped in Stage 1 — documented, reversible.

## 17. Typography System

- **Wordmark:** Inter (precision neo-grotesk) — semibold, wide uppercase
  tracking. Infrastructure-grade; the mark is abstract, the wordmark is
  engineered. (Locked per §9 brand-style brief.)
- **Display:** Sora Variable — page titles, case headlines (calm geometric authority); one display headline per view.
- **UI:** Inter Variable — body, tables, controls.
- **Mono:** JetBrains Mono — indicators, IDs, scores, code/report surfaces.
- Scale: 28/20/16/14/13/12/11 with 0.6875rem (`xxs`) for dense table meta.
  Editorial rule: one display headline per screen; everything else recedes.

## 18. Design Tokens

Single source: `tailwind.config.js` (+ `constants/brand.ts` for non-CSS
contexts). Tokens are semantic (role-named), never literal in components —
Stage 1 removes the remaining raw `slate/blue` literals from primary surfaces.
Shadows: `card` (soft dark), `navy` (canvas depth), `overlay`/`raised`
(menus/toasts). **No glow shadows on buttons** — accent color carries the
brand, not halo effects. Motion tokens:
`fade-in 160ms`, `fade-up 240ms`, `scale-in 140ms`, `slide-in-right 180ms`.

## 19. UI Design Language

- **Analyst-inbox layout**, not dashboard grids: greeting → lead case → list.
- **Night canvas panels** (`app-navy`) for NOCTRA's voice (briefs, blast
  radius, reports) — the analyst "speaks" from a darker, editorial surface.
- **Editorial hierarchy:** headline → summary → evidence; whitespace over
  borders; one primary action per view.
- **Progressive disclosure:** plain-English first; "Technical details"
  expanders for MITRE, scores, rule names.
- **Decision gates** are always visible and honest (Approve records; Decline
  changes nothing; Reverse compensates).

## 20. UX Principles

1. Answer "what needs me?" before anything else.
2. Never fabricate — every number traces to an API.
3. One reversible recommendation per case, always with undo.
4. Plain English by default; depth on demand.
5. Color is mood, labels are meaning (severity = dot + text).
6. The human decides; NOCTRA records.
7. Calm motion that explains state; nothing blinks at the user.

## 21. Screen-by-Screen Wireframes (textual)

**2 Login / 3 Register / 3b Reset** — purpose: door, not billboard. Centered
card on ink, NOCTRA lockup, tagline, email/username + password (Formik+Yup),
submit → `/` (Login) with toast; link to register/reset; errors via
`getApiError`. Data: `/login` (form-encoded), `/register` (USER/ANALYST only),
`/forgot-password`, `/reset-password`. States: loading on button, inline
field errors, server error card. Mobile: single column, 100% width.

**4 Onboarding (Stage 3)** — first-login checklist: 1) meet NOCTRA (60s
brief), 2) connect a source (connectors), 3) simulate an incident, 4) approve
your first decision. Persisted per-user flag. Purpose: teach the loop by
doing it.

**5 Home / Analyst Inbox (Stage 1 shipped)** —
```
Good morning.                                    [Simulate incident ▾]
Tuesday, 1 April · NOCTRA is watching 128 assets

┌─ NEEDS YOUR DECISION (1) ─────────────────────────────────────┐
│ CRITICAL · dot+label          Awaiting your decision          │
│ Leaked corporate credential is being used to sign in          │
│ A set of company credentials appears to have leaked… (2 lines)│
│ Why it matters: valid stolen login acts as a trusted employee.│
│ Affected: 4 entities · Confidence: 90% · Reasoned by fallback │
│ NOCTRA recommends: REVOKE_CREDENTIALS on account:jdoe         │
│ Undo: re-enable the account + forced reset                    │
│                       [Review decision →]  [Decline]          │
└──────────────────────────────────────────────────────────────┘
Also waiting (2):  case #12 Phishing payload on ws-eng-042  [→]
Recently handled:  case #9 approved · case #7 reversed        [→ Reports]
Sources: Okta · EDR · GuardDuty · Cloudflare — all connected   [sync]
```
Data: `GET /analyst/brief` (pending_count, handled_today, watching,
top_cases), `GET /analyst/connectors`, `POST /analyst/simulate`. Empty:
"Nothing needs you right now." + last-handled + simulate. Error: card with
retry. Loading: skeleton. No fabricated numbers.

**6 Cases list (`/feed`)** — table: headline, severity dot+label, decision
state pill, opened date; row → case. Filters: state. Data: `GET /analyst/feed`
paginated. States: skeleton, empty ("No cases yet — simulate one"), error,
pagination.

**7–11 Case workspace (`/case/:id`, Stage 2)** — two-column on desktop:
left = narrative (Brief → Why it matters → Blast radius (canvas panel, chips +
links) → Evidence & timeline (alert, entities, audit refs) → Report preview);
right sticky rail = status, confidence, **Recommendation card**
(action/target/undo), **Decision gate** (Approve — record action / Decline /
Reverse), decision history. States 8–11 are the same screen with the rail in
pending/approved/declined/reverted configuration; approved adds "action
recorded · SOAR id …", reverted adds the compensating record. Technical
details (MITRE, score, rule) behind an expander. Mobile: rail becomes a
sticky bottom bar with the primary action.

**12 Actions (`/actions`)** — "recorded containment log": table of approved /
reversed cases — action type, target, SOAR id, state (`Recorded` /
`Reversed`), reverse button (approved only). Search by target/type. Data:
`/analyst/feed` filtered client-side + `POST /analyst/cases/{id}/revert`.
Copy: "Actions are **recorded** (record-only SOAR); reversing files a
compensating record."

**13 Reports (`/reports`)** — left list (case, state, decided date), right
report preview in a night-canvas mono pane; Download markdown; View case.
Data: `report` field on feed/case. Empty: "Reports appear once you decide."

**14 Threat Graph / 15 Alerts / 16 Entities / 17 Analytics / 18 SOAR /
19 Rules / 20 Reputation / 21 Audit / 22 Settings / 23 Admin** — deep-dive
surfaces (existing pages, re-tokened). Grouped under Investigate/Automate/
System. Each keeps: skeleton/empty/error states, `getApiError` messages,
permission-gated entry. Alerts adds "Open as case" (Stage 2: prefill
CreateIncident with source_alert_id). Analytics keeps trends/benchmark/
explain with the question-led chart titles from §31.

**24 Loading** — skeleton tables; NOCTRA mono mark pulse ≤ 2 loops; text
"Reading your brief…". **25 Empty** — mark + one calm sentence + one action.
**26 Error** — card: what failed, real detail, retry; offline adds
"Retrying is safe — nothing is lost." **27 AI fallback** — "Built-in
reasoning" badge when `analysis.fallback`; explain drawer shows indicators.
**28 Mobile** — sidebar → drawer; decision rail → bottom bar; tables →
card lists; report preview reflows; approve/decline reachable one-thumbed.

## 22. User Flows

- **Decision flow (primary):** Home lead case → Review decision → Case rail
  (brief, affected, confidence, undo) → Approve — record action → confirm →
  state pill "Approved — action recorded" + report link.
- **Reverse flow:** Case or Actions → Reverse action → confirm (undo text
  shown) → "Reversed — compensating record".
- **Simulate/demo flow:** Home → Simulate ▾ (4 scenarios) → lands on new case.
- **Deep-dive flow:** Alert row → detail modal → "Open as case" (Stage 2).
- **Admin flow:** Users/Roles/Tenants/Rules/Engine under SYSTEM/AUTOMATE.

## 23. Case Lifecycle

```
Sensed ─ Reasoned ─ Recommended          (decision: pending)
   └─ Awaiting your decision ────────── Approve ─► Approved · action recorded
                                          │            └─ Reverse ─► Reverted · compensating record
                                          └─ Decline ─► Declined · no change
Every transition: decided_by/at + audit row (ANALYST_CASE_*) + markdown report.
```

## 24. Component Architecture

Primitives (existing, kept): Button, Card, Modal, ConfirmDialog, Select,
Badge/SeverityBadge/StatusBadge, Toast(+bridge), Skeleton*, EmptyState,
StatCard, PageHeader, Breadcrumbs, BackButton, Spinner/LoadingState,
TableWithAction, ErrorBoundary, PageTransition. **Add (Stage 2):** Drawer,
Tooltip, Tabs, CommandMenu (⌘K).

NOCTRA-specific (Stage 2, `features/cases/components/`): CaseCard,
CaseHeader, DecisionPill, AIBrief, BlastRadius, EvidencePanel,
RecommendationCard, ApprovalPanel, DecisionHistory, ReportPreview,
AnalystFeedRow, SystemHealth. Rule: one component per job; pages compose,
they don't reimplement.

## 25. Frontend Folder Architecture

Target (incremental; nothing breaks mid-move):

```
src/
  app/            App.tsx, routes/ (route table + guards)
  shared/         ui/ layouts/ charts/ hooks/ utils/
  features/
    auth/ account/            (move from features/auth, features/account — already there)
    inbox/   pages/HomePage            (was pages/BriefPage)
    cases/   pages/{CasesPage,CasePage} components/ hooks/
    actions/ reports/
    investigate/ alerts/ entities/ analytics/ cockpit/
    automate/ soar/ rules/
    system/  audit/ reputation/ engine/ admin/
  services/       api clients (from src/api)
  store/ theme/ (tokens.ts mirrors tailwind) constants/
```

Stays: `api/*` clients (moved to `services/` late), `components/ui` →
`shared/ui`, Redux auth slice. Deprecated: `pages/BriefPage.tsx` name (→
`features/inbox/pages/HomePage`), `constants/tableColumns` THREAT_ALERT
columns (unused). Added: feature folders above, `hooks/` (useBrief, useCase,
useDecision), CommandMenu. No duplicate clients or state stores.

## 26. API Integration Matrix (feature → client → endpoint → backend → UI state)

| Feature | Client | Endpoint(s) | Backend | UI state |
| --- | --- | --- | --- | --- |
| Home/Inbox | analystApi | `GET /analyst/brief`, `GET /analyst/connectors`, `POST /analyst/connectors/{id}/sync`, `POST /analyst/simulate?scenario_type` | analyst_service | loading/error/empty, pending lead case |
| Cases | analystApi | `GET /analyst/feed?page&limit` | Case(kind=analyst) | table + pagination |
| Case | analystApi | `GET /analyst/cases/{id}`, `POST …/approve|decline|revert`, `GET …/report`, `POST …/chat` | analyst_service, soar, report | pending/approved/declined/reverted rail, busy |
| Actions | analystApi | feed + `revert` (above) | SoarAction | recorded/reversed |
| Reports | analystApi | feed + `cases/{id}/report` | Case.report | list + preview + download |
| Alerts | alertApi | `GET /alerts`, `POST /analyze`, `POST /upload-logs`, `GET /uploads/{id}`, `GET /logs/history`, `POST /save-scanned-alerts` | SecurityAlert/ScanBatch | stream/poll/error |
| Entities | entityApi | `GET /entities`, `/entities/summary`, `/entities/path`, `/{id}/graph`, `POST /{id}/reputation` | Entity/EntityLink | table/graph/path |
| Analytics | analyticsApi, mlApi | `/analytics/overview|top-threats|trends`, `/ml/benchmark`, `/ml/explain/*` | alert_service→ml-service | charts, fallback msg |
| SOAR | soarApi, rulesApi | `/soar/actions|evaluate|trigger|playbooks CRUD`, `/rules` CRUD | SoarAction/Playbook | audit table, dry-run, 503 handling |
| Audit | auditApi | `GET /audit-logs` | AuditLog | filter+page |
| Reputation | reputationApi | `/rules`… no — `/reputation` CRUD + block/unblock | IpReputation | table+modals |
| Admin | adminApi | `/admin/orgs|roles`, `/users` CRUD, `/engine/settings` | Org/User/EngineSetting | roster/matrix/settings |
| Auth | userApi/userActions | `/login /refresh /logout /me /register /forgot /reset`, `/user/profile`, `/user/updatePassword` | User/ABAC | redux slice + gating |

No invented endpoints — everything above exists in `api/v1/router.py`.

## 27. State Matrix (per screen: L/E/Err/OK/partial/perm/offline/AI)

| Screen | Loading | Empty | Error | Partial/perm | AI states |
| --- | --- | --- | --- | --- | --- |
| Home | skeleton rows | "Nothing needs you right now" | card+retry | connectors fail → quiet | fallback badge on lead case |
| Cases | SkeletonTable | simulate CTA | toast+retry | pagination | — |
| Case | "NOCTRA is opening…" | 404 → back | inline | chat error → local msg | reasoning busy, fallback, confidence |
| Actions | skeleton | "No actions recorded yet" | card | search none | — |
| Reports | skeleton | "Reports appear once you decide" | card | — | "reasoned by {model}" |
| Alerts/Entities/Analytics/SOAR/Rules/Reputation/Audit/Admin | existing skeleton/empty/error + `getApiError`; 403 → "You don't have access to this view" | | | | ML down → "Built-in reasoning"/503 copy |

## 28. Responsive Strategy

Desktop 1280+ primary (inbox + case rail). 1024: sidebar auto-collapses to
icons. 768: sidebar → drawer; case rail → sections. 480: decision bar sticky
bottom; tables → card rows; report preview reflows; connectors → 1-col.
Never just shrink: primary actions stay thumb-reachable.

## 29. Accessibility Strategy

WCAG 2.2 AA: semantic landmarks (nav/main), `aria-current` on nav, focus
visible (global ring in globals.css), dialogs focus-trap + Esc + labelled,
tables with real `<th scope>`, charts get text summaries (Stage 2), severity
always dot+label, `prefers-reduced-motion` kills all animation (already
global), toasts `aria-live=polite`, contrast checked per §16.

## 30. Motion Strategy

Explain, don't entertain: page fade 160–240ms; lead-case entrance fade-up;
decision-state pill transition; drawer slide; AI "reasoning" = three-dot text
shimmer (no glow storms). Reduced-motion → instant. No pulsing severity.

## 31. Data Visualization Strategy

Charts answer questions: "What changed?" (7-day trend), "What is affected?"
(blast-radius graph), "What did NOCTRA resolve?" (decision mix over time,
Stage 2), "How sure is it?" (confidence distribution, Stage 3). Keep: trend
area, severity distribution, top patterns, benchmark table. Drop/de-emphasize
decorative KPI cards on primary surfaces. Palette per §16.

## 32. Implementation Roadmap

- **Stage 1 (this pass):** brand foundation (full-stack NOCTRA), Night-Shift
  tokens, logo/favicon/html, shell + navigation IA, Home/Analyst Inbox,
  trust-accurate language, token migration of primary surfaces, spec doc.
- **Stage 2:** Case workspace (rail, evidence, timeline, decision history,
  report preview), Cases list polish, Alerts→case bridge, Drawer/Tabs/
  Tooltip, charts text summaries.
- **Stage 3:** Landing page (product-led, live case example), onboarding
  checklist, CommandMenu, light theme tokens, folder migration (§25).
- **Stage 4:** a11y audit pass, responsive hardening, motion polish, demo
  script + verification matrix.
- After each stage: `pytest` (backend+ml), `tsc --noEmit`, `vite build`.

## 33–36. Files Add / Modify / Deprecate / Preserved

**Added:** this spec; `public/favicon.svg` (new mark); Stage 2–3 items per §24/25.
**Modified (Stage 1):** `constants/brand.ts`, `components/BrandLogo.tsx`,
`index.html`, `tailwind.config.js`, `styles/globals.css`,
`layouts/DashboardLayout`, `App.tsx`, `pages/BriefPage|CasePage|ActionsPage|
ReportsPage|LandingPage|SoarPage` (copy + token migration), `ui/Button.tsx`,
`ui/PageHeader.tsx`, `features/auth/pages/Login.tsx` (dead `brand-sage`
gradient → accent tokens); backend `config.py`, `llm_client.py`, `report.py`,
`analyst_service.py`, `analyst.py` (persona strings), `tests/test_analyst.py`
(comments); `README.md`, `docs/brand-strategy.md`,
`docs/brand-identity-axiom.md` (supersession banners).
**Deprecated:** `pages/BriefPage.tsx` name (Stage 3 rename), unused
`THREAT_ALERT_COLUMNS`.
**Preserved:** every route, API client, backend endpoint, test, and
capability — none removed.

## 37. Missing Integrations (honest gaps)

- "Handled automatically" count is not tracked by `/analyst/brief` (only
  pending + handled-today); Inbox copy sticks to real numbers until the
  backend adds it.
- Case timeline/evidence endpoint doesn't exist; Stage 2 composes from
  `case.source_alert_id` + audit logs.
- Connectors are a static status surface (no live sync API) — presented as
  status, not telemetry.
- SOAR is record-only by design — UI language reflects it.

## 38. Open Questions / Input Needed (unanswered → documented assumptions)

1. **Brand scope** → assumed full-stack (reports/LLM produce user-facing text).
2. **Visual direction** → assumed dark-first ink + violet-family accent
   (name story, brand history, long-session calm); light theme specced for
   Stage 3. Accent later audited against the category (§15) and shifted to
   periwinkle `#A8A2FF`.
3. **Tagline** → "Your autonomous security analyst." (secondary:
   "See less. Know more.").
4. **Pacing** → staged per §32; repo green after every stage.
All reversible; say the word to re-aim.

## 39. Verification Results (Stage 1)

Verified 2026-08-27 on the working branch, after the Stage-1 changes:

- Backend pytest: **114 passed / 2 skipped** (persona/report strings updated;
  no test asserted the old AXIOM strings).
- ml-service pytest: **13 passed**.
- Dashboard: `tsc --noEmit` clean · `vite build` clean. Built CSS contains
  every semantic Night-Shift token (confirmed via compiled values, e.g.
  `bg-app-bg` → `rgb(12 14 20)` = `#0C0E14`); zero AXIOM strings in built
  assets.
- Live smoke (backend on SQLite, `COOKIE_AUTH=true` like docker-compose, +
  Vite dev server proxying `/api`):
  - register → login 200 (httpOnly cookies) → `GET /analyst/brief` returns
    real `pending_count` / `handled_today` / `watching` / `top_cases`.
  - `POST /analyst/simulate` → Case #1 `critical`, analysis flagged
    `fallback: true` with `model: "fallback-template"` (UI labels it
    rule-based, not model-inferred); blast radius 4 nodes.
  - `POST /analyst/cases/1/approve` → decision `approved`, status
    `resolved`, `soar_action_id` **recorded** (record-only SOAR — nothing
    executed), report generated.
  - Report line reads "Generated … by **NOCTRA analyst** (fallback-template
    (templated fallback))."; the UI downloads it as
    `noctra-report-case-1.md`.
  - Served dashboard title: "NOCTRA — Your autonomous security analyst.";
    favicon is the Night Signal mark.
- Intentional AXIOM remainder: the chat wire value `sender:"axiom"`
  (`types/analyst.ts`, CasePage seeding) — kept for compatibility, UI labels
  say NOCTRA.
- Not yet verified: full browser click-through of the new Inbox visual
  layout (live preview is running; screenshots/user pass pending).

### Addendum — Exact brand spec implementation (2026-08-27, latest pass)

- **Logo system replaced per the user's exact specification** (§12–13
  rewritten): folded-ribbon "N" with diagonal gradient `#6C5CE7→#9D7CFF`,
  faceted overlays, 4-point `#B18CFF` insight sparkle; Sora SemiBold
  wordmark with sparkle-A; "YOUR AUTONOMOUS SECURITY ANALYST" tagline in
  `#9D7CFF`; divider lockup; `#0B0E1A` badge favicon. Supersedes both the
  "Night Signal" mark and the interim neo-grotesk wordmark lockup.
- **Tokens reconciled to the same family**: accent-primary `#9D7CFF`,
  light-scope accent text `#6C5CE7`, night hover `#C9C4FF`, brand ink
  unchanged; ambient wash + `brand.ts` constants updated; zero periwinkle
  remains (grep + built CSS verified).
- **Contrast re-verified (all AA+)**: 6.2 / 4.86 / 4.53 / 5.54 / 4.86 —
  see §15 supersession note.
- **Brand sheet generated**: `docs/brand/noctra-logo-sheet.png`.
- tsc + vite build clean; favicon serving the badge mark; preview live.

### Addendum — Backend enrichment (2026-08-27, latest pass)

Three new analyst capabilities, all composed from real rows only:

- **Honest activity metrics** in `GET /analyst/brief`: `alerts_today`
  (detections investigated) + `auto_recorded_today` (SOAR responses recorded
  automatically by rules — decision-path records are excluded via their
  `analyst-recommended` / `revert::*` rule names; NULL rule names count as
  automation). Home's header now reads "N events investigated today · M
  automated responses recorded · K decisions by you · 1 waiting."
- **Server-side case record** `GET /analyst/cases/{id}/timeline`: entries
  from the source alert (evidence), case open, recorded SOAR action
  (record-only noted), decision (with actor username), report, and
  ANALYST_* audit entries (incl. consulted questions). Chronologically
  sorted; absent rows produce no entries. CasePage now renders this for
  pending *and* decided cases (replaces the client-composed version).
- **Derived notifications** `GET /analyst/notifications`: pending decisions
  + outcomes from the last 24 h. No unread-state table by design — the
  client tracks the last-seen timestamp. The Navbar bell is back, honestly:
  real badge count, dropdown with per-item deep links, truthful empty state.
- Tests: 4 new (brief metric discrimination incl. approve-not-auto, timeline
  composition + ordering + decline-has-no-action, notifications derivation,
  HTTP incl. 404). Suite: **118 passed / 2 skipped**. tsc + build clean.
  Live-verified on the preview stack (case #3 timeline shows actor
  attribution; notifications list 4 outcomes + 1 pending).

### Addendum — Stage 3: brand-style application + landing rebuild (2026-08-27)

- **Brand style brief locked** (§9 table): Intelligence Infrastructure /
  Precision Neo-Grotesk wordmark / Abstract Intelligence Mark / Editorial
  Enterprise / Operational Minimalism / Purposeful Intelligence / Lumen
  Enterprise + hard avoid list. Compliance pass: wordmark moved from Sora to
  Inter semibold wide-tracked uppercase (subline demoted to muted); remaining
  gradients flattened (PageHeader rule, Login CTA) — solid accent only.
- **Landing rebuilt** product-led: overline → statement → the loop as content
  (Sense→…→Report strip) → an example case on the night canvas (explicitly
  labeled "Example — illustrative", mirrors real case-card structure incl.
  record-only note) → numbered editorial pillars → record-only trust strip.
  Day hero + night example panel = duality demonstrated. One display
  headline per view enforced.
- Verified: tsc + build clean; `/welcome` serving.

### Addendum — Stage 3 start (⌘K command menu, onboarding, 2026-08-27)

- **Command menu** (`components/CommandMenu.tsx`): ⌘K/Ctrl+K app-wide (mounted
  in the shell), or the ⌘K chip / mobile search button in the Navbar.
  Keyboard-first (↑↓/↵/esc, combobox + listbox semantics,
  `aria-activedescendant`) over three groups: Navigate (11 routes), Cases
  (live decision-feed lookup — jump straight to any case), Actions (fire any
  of the four scenario simulations; navigates to the created case). Rendered
  on the night canvas — asking the analyst happens in the dark.
- **First-run onboarding checklist** (`components/OnboardingChecklist.tsx`):
  five steps walking the loop — telemetry flowing → first case → first
  decision → see it recorded → read the report. Completion is derived from
  real data (brief counts, feed decisions, report presence) or real visits
  (Actions/Reports page flags); never simulated. Dismissable, auto-hides
  when complete. Verified: tsc + build clean; hidden for the seeded demo
  user (all steps genuinely done), appears for fresh accounts.

### Addendum — Stage 2 progress (2026-08-27, later pass)

- **Alerts→Case bridge** (directive §4 mapping "Alert → Case Evidence"):
  CasePage now resolves `source_alert_id` against the alert list and renders
  an **Evidence (Observed)** night card — type, severity, source IP, MITRE
  and the raw message; states honestly when the alert row is no longer
  present. AlertDetailModal gains a direct "NOCTRA case #N →" link when a
  case was opened from that alert. Verified live (case #3 ↔ alert #3,
  credential_leak / T1078).
- **401 session interceptor** added (QA MISSING-3 fixed): single-flight
  `/refresh`, one retry, clean logout redirect; auth endpoints exempt.
- **Severity tokens unified**: shared `Badge.tsx` and `AlertDetailModal`
  migrated off status-/chart-4 colors onto the `severity-*` ramp — one
  system app-wide (SoarPage already used it).
- tsc + vite build clean; backend untouched (114/2 baseline holds).

### Addendum — Stage 1.2 (DUALITY, QA pass, 2026-08-27)

- Implemented DUALITY per directive §5: day workspace + night canvas as
  structural CSS-variable scopes (see QA report §2 and spec §16).
- Full-route frontend QA audit completed; 7 bug classes found and fixed
  (fake LIVE badge, dead notification button, two orphaned routes, missing
  Observed/Inferred labels, Home §12 structure, button contrast defects,
  theme-flip accent-text hazard) — `docs/noctra-qa-report.md`.
- Phase-18 loop re-verified live incl. decline and revert paths.
- Backend 114/2, ml 13, tsc + build clean after all changes.

- Accent audited against the category (§15 Round 2): mid-violet
  `#8B7CF6` sits in SentinelOne/Wiz territory → **primary accent shifted to
  periwinkle `#A8A2FF`** (logo, favicon, tokens, ambient wash); `#8B7CF6`
  retained only as dataviz chart-1.
- Button glow removed (`shadow-lumen`/`shadow-accent-glow` tokens deleted;
  all usages cleaned) — accent color carries the brand, not halos.
- Design-system naming ("Night Shift", "Lumen") removed from all surfaces and
  docs; copy states what the product *is* (your autonomous security analyst).
- Re-verified after changes: `tsc --noEmit` + `vite build` clean; built CSS
  carries the new accent (`rgb(168 162 255)`); no glow shadows in built CSS.
