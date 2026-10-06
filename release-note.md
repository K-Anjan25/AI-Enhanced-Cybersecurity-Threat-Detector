# AEGIS — Release note

|                  |                                                                                                                        |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Document**     | The release note: what a release contains and what was verified before it shipped                                      |
| **Version**      | 0.1 — **pre-release**. Sections are filled in by the task that can measure them, and only with measured results (R-74) |
| **Last updated** | 2026-10-06 (Monday)                                                                                                    |
| **Related**      | [prd.md](prd.md) · [task.md](task.md) · [memory.md](memory.md) · [design.md](design.md)                                |

**This note is deliberately incomplete, and says which parts are.** A number appears here only
after the run that produced it is recorded in [memory.md](memory.md); a check appears only with
the command that ran it and its result. Anything not yet measured is listed under
[Not yet recorded](#not-yet-recorded) with the task that owns it, rather than left as a blank a
reader might mistake for a pass. T-510 (v1.0) is the task that publishes this note.

## Scope of the current build

Every screen design.md §3 names except `/admin/connectors` (T-422) is built: the overview, alert
triage with its batch export, the traffic explorer, the log explorer, the hunt console, model ops
with drift, and the admin screens. E4's remaining work is the accessibility and frontend-test
polish (T-413, T-414) and the read models that make the built screens complete rather than capped
(T-416, T-418, T-419). E5 — load, failure drills, Kubernetes, release engineering — is untouched.

## Accessibility (T-413, NFR-09)

Target: **WCAG 2.1 AA** (design.md §9). Measured 2026-10-06 on the three core screens — Overview
(monitor), Alert triage (the loop) and the Hunt console (investigate).

| Check                                                                                                  | Result                                                                                    |
| ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| axe-core, WCAG 2.0/2.1 A+AA **and** best-practice rules                                                | **0 violations at every impact level** on all three screens (not just 0 critical/serious) |
| Structure: one `h1`, no positive `tabindex`, scoped table headers, no focusable-but-inoperable element | **0 findings** on all three screens                                                       |
| Landmarks: exactly one `main`, plus `banner` and `navigation`, read through the shell                  | **0 findings** on all three routes                                                        |
| Keyboard: every interactive control reachable by tabbing from the start of the document                | **3 of 3 (Overview), 21 of 22 (Alert triage), 28 of 28 (Hunt)** tab stops reached         |
| `eslint-plugin-jsx-a11y` (recommended set), in CI                                                      | passing                                                                                   |
| Contrast: every published ratio recomputed against the shipped tokens (T-401)                          | passing                                                                                   |

Alert triage's twenty-second control is the evidence panel's unselected tab. The ARIA tabs pattern
keeps exactly one tab in the tab order on purpose and reaches the others with the arrow keys, so the
audit counts those as reachable only while the tablist still has a tab stop of its own — a tablist
with every tab at `tabindex="-1"` is reported as unreachable. `EvidencePanel.test.tsx` asserts the
arrows move the selection, and deleting the arrow handler fails that test.

Reproduce with:

```
cd dashboard && npx vitest run src/test/a11y.test.ts src/features/overview/pages/OverviewPage.test.tsx \
  src/features/triage/pages/TriagePage.test.tsx src/features/hunt/pages/HuntPage.test.tsx
```

**Screen-reader pass: not performed, and this note says so rather than implying otherwise.**
design.md §9 requires _one manual screen-reader pass per release with the result recorded in the
release note_. This environment has no screen reader and no audio output, so the pass could not be
run, and a run that did not happen is not a pass. What was done instead, and what it does not
cover:

- **Done:** a machine-readable structure audit (`src/test/a11y.ts`) that asserts the reading-order
  properties a screen reader depends on — one `h1` per screen, the `banner`/`navigation`/`main`
  landmarks, a named list for the queue, `scope` on every table header, no positive `tabindex`, and
  no focusable element that is not a native control or an operable role. Plus a keyboard walk that
  fails if any control on the screen cannot be reached by tabbing.
- **Not covered:** anything that needs a human ear — whether live regions are announced in the
  right order during a burst of alerts, whether the verdict announcement interrupts usefully or
  annoyingly, pronunciation, and whether the reading order of the four detail panels matches how
  an analyst reads them.
- **Outstanding, owned by T-510:** run the pass on a machine with VoiceOver (macOS) or NVDA
  (Windows) against the three core screens, record the transcript and the findings here, and file
  what it turns up as tasks. The checklist to walk: the triage loop end to end without a mouse;
  a `1`/`2`/`3` verdict announced; a new alert arriving while the queue is open; `⌘K` and `?`
  announcing their dialogs; and one table read with its headers.

## Not yet recorded

| Item                                                       | Owner       | Status       |
| ---------------------------------------------------------- | ----------- | ------------ |
| Sustained ingest under load (5,000 flows/s, 10,000 logs/s) | T-501       | not run      |
| p95 latency per stage against the NFR-01 budget            | T-502       | not run      |
| Failure-mode drills from architecture.md §14               | T-503       | not run      |
| Kubernetes deployment on a clean cluster                   | T-504       | not run      |
| Grafana dashboards and alert rules                         | T-505       | not run      |
| Security review against architecture.md §12                | T-506       | not run      |
| Backup and restore rehearsal                               | T-507       | not run      |
| Model metrics for the shipped model (release gate Q-07)    | T-202/T-208 | not measured |
| Manual screen-reader pass                                  | T-510       | not run      |
