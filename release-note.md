# AEGIS — Release note

|                  |                                                                                                                        |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Document**     | The release note: what a release contains and what was verified before it shipped                                      |
| **Version**      | 0.1 — **pre-release**. Sections are filled in by the task that can measure them, and only with measured results (R-74) |
| **Last updated** | 2026-10-07 (Tuesday)                                                                                                   |
| **Related**      | [prd.md](prd.md) · [task.md](task.md) · [memory.md](memory.md) · [design.md](design.md)                                |

**This note is deliberately incomplete, and says which parts are.** A number appears here only
after the run that produced it is recorded in [memory.md](memory.md); a check appears only with
the command that ran it and its result. Anything not yet measured is listed under
[Not yet recorded](#not-yet-recorded) with the task that owns it, rather than left as a blank a
reader might mistake for a pass. T-510 (v1.0) is the task that publishes this note.

## Scope of the current build

Every screen design.md §3 names except `/admin/connectors` (T-422) is built: the overview, alert
triage with its batch export, the traffic explorer, the log explorer, the hunt console, model ops
with drift, and the admin screens. E4's remaining work is the one screen design.md §3 still leaves unbuilt
(**T-422**); the accessibility pass (T-413), the frontend-test rule (T-414), the overview's aggregate
(T-416), the persistent log read model (T-419) and the flow read model (T-418) have landed. E5 — load, failure drills, Kubernetes, release engineering — is
untouched.

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

## Counts and completeness (T-416, FR-50)

Measured 2026-10-06. The overview's figures — the KPI tiles, the severity series, the entity list and
the family mix — come from **one request**, `GET /api/v1/overview`, which aggregates the selected
window where the rows are.

| Claim                                                       | Evidence                                                                                                             |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| One request fills the tiles, the series and the entity list | 1 `/api/v1/overview` request per window, 0 `/api/v1/alerts` requests, asserted on the wire in the page test          |
| Counts are the window's, not a read of it                   | `counts_are_the_window_s_own_and_not_capped`: 5,050 rows counted in full against the 5,000-row cap the page walk had |
| No partial-coverage language remains on the screen          | asserted absent (the half of the change a screenshot cannot show)                                                    |
| Every entity renders its host or user value                 | `kind`/`value` from the entity registry; an id it has not seen renders as `entity <id>` and the panel says so        |
| A capped list says it is one                                | `entities_capped`/`families_capped` are true only when the window held _more_ than the limit, boundary tested        |

The arithmetic is defended by thirteen planted defects — an occurrence sum replaced by a row count
in both the arithmetic and the SQL, a dropped blank family, a `min` where the fold needs `max`, an
unknown band dropped from the tile and from the series, a cap flag off by one on each list, a
hard-coded `families_capped`, the family statement's `LIMIT` removed, the in-memory store not
forwarding its family limit, and an unnamed id rendered as named. Thirteen were killed; the two
that survived the first pass were the cap boundary on each list, which is why that boundary now has
its own test.

What is **not** yet true: the aggregation SQL is written and tested but not executed — the overview
still reads the in-process store until the database session D-030 records is wired (T-419's
neighbour problem). Naming is per-process, so an id written by another process or before a restart
renders as `entity <id>`. Both are stated on the screen rather than papered over.

## The flow read model (T-418, FR-52)

Measured 2026-10-07. The traffic explorer no longer counts records that raised an alert: its volume
is accepted flow records, its edges are flow relationships, and a deployment that names
`AEGIS_DATABASE_URL` reads them from `flow_events`, a PostgreSQL table written on ingest.

| Claim                                                      | Evidence                                                                                                                                          |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Volume is traffic, not the alerted subset                  | a test seeds alerts on one address and flows on another; the busiest address, busiest pair and byte totals follow the flows (`test_flows_api.py`) |
| Edges are flow relationships                               | an edge is a source/target pair with its own record count, not a correlation trace                                                                |
| Counts are complete for the window                         | `totals` covers every accepted record; a cap on the entity or edge **list** moves the list and not the count, and `*_capped` says so              |
| A read survives the process that accepted it               | `test_flow_store_live.py::test_a_read_survives_the_process_that_accepted_it`, against PostgreSQL 16.2 over a unix-socket DSN                      |
| A window the in-process rollup would refuse is answered    | a three-day window at `bucket_minutes=1440`; the rollup refuses anything past its own span, naming its own `max_span_seconds`                     |
| The panel's permanent caveat has lost the T-418 half       | asserted absent on the Traffic screen, alongside the API's own caveats arriving verbatim                                                          |
| A deployment without a database is told what it is reading | `source: "rollup"` plus a sentence naming `AEGIS_DATABASE_URL` and the minute granularity; `AEGIS_FLOW_STORE=off` gets its own sentence           |
| An unreachable store is a 503, not an empty screen         | both the flow route and the ingest write, asserted in `test_flows_source_api.py`                                                                  |

Reproduce with:

```
cd backend && ../.venv/bin/python -m pytest -q --no-cov tests/test_flow_read_model.py tests/test_flow_source.py \
  tests/test_flow_statements.py tests/test_flow_store.py tests/test_flows_api.py tests/test_flows_source_api.py
cd dashboard && npx vitest run src/features/traffic
```

What is **not** yet true: `flow_events` is unpartitioned and swept by nothing, so no plan removes an
old row and the retention report names it rather than implying otherwise; the default deployment
reads the minute-grained 60-minute in-process rollup, so the store's exactness is a capability a
deployment configures rather than a property of a default install; an alert attaches to an address
only when the alert's entity value _is_ that address, and flow detections are keyed by source
address, so a destination-side alert is named in the caveats as a partial rather than shown on a row;
and the store's SQL is exercised through the store, not through the HTTP route, because D-030's
database session is still not wired into the request path.

## The log read model (T-419, FR-52)

Measured 2026-10-07. The log explorer no longer reads only the last 20,000 lines in memory: a
deployment that names `AEGIS_DATABASE_URL` answers from `log_events`, a PostgreSQL table written on
ingest, and the API says which of the two read models answered.

| Claim                                                             | Evidence                                                                                                                  |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| A read survives a restart and a second worker                     | `test_log_store_live.py::test_a_second_client_reads_what_the_first_wrote`, against PostgreSQL 16.2                        |
| A window older than the tail's retention is readable              | 2-hour-old window: the store answers, the tail refuses it — same test module, both halves asserted                        |
| A host that has logged nothing since is findable by filter        | the store's window, host and level filters are SQL `WHERE` clauses; the live test reads a quiet host's stored lines       |
| The caveat about the missing store is gone                        | asserted absent on the Logs screen; a tail deployment keeps its own "not a store" sentence, which is still true for it    |
| The picker offers only windows the answering source can read      | `spansFor`: 1/5/15 min for a tail, plus 1 h/24 h for a store; the page test drives a 24 h read on the wire                |
| Counts and rows arrive with the sentence that qualifies them      | the API's caveats, carried verbatim — the store's own set, including that nothing evicts `log_events` yet                 |
| An unreachable store is a 503, not an empty screen                | both log routes and the ingest write, asserted in `test_logs_source_api.py`                                               |
| The fold does not depend on which source answered                 | `log_keys.cluster_key` is written at ingest and used by both; `test_log_store_live.py` folds the same lines both ways     |
| A URL this build cannot open asynchronously is refused at startup | `test_log_engine.py`: the builder names `postgresql+psycopg://`, and `require_async_dialect` refuses a synchronous engine |

What is **not** yet true: nothing evicts `log_events`, so a stored read reports its aged-out count as
"not reportable" (`null`) rather than as zero, and the API says so in a sentence; there is no text
search over stored lines — the reads are by window, host, service, level and cluster key — so the
hunt console's `message` term still carries the reason it is unsearchable; and the alert and
threshold stores remain in-process until D-030's database session is wired into the request path.

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
