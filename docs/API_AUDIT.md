# API audit — what exists, what it does, what is left

Generated against the running application on 2026-08-30. Counts come from the
live OpenAPI schema (258 paths, 66 groups) cross-referenced against every API
path literal in `dashboard/src`.

This document describes each capability in plain terms — what an operator gets
from it, named by the button or page where possible — and classifies it.

---

## 1. Summary

| | Count |
|---|---|
| API paths | 258 |
| Route groups | 66 |
| Reachable from the UI | 183 paths |
| No UI caller | 75 paths |
| Backend tests | 489 passing, 2 skipped (29 files) |
| Frontend tests | 137 passing (19 files) |
| Type check / build | clean |

"No UI caller" is not the same as "broken". Of the 79, roughly half are
machine-facing by design (SCIM, health, OAuth callbacks, webhook ingest). The
genuinely missing surfaces are listed in §5.

---

## 2. The core product loop — necessary, working

This is the autonomous-analyst path an SMB actually buys. Everything here is
wired end to end and covered by tests.

| Capability | Where the user meets it | What it does, plainly |
|---|---|---|
| Sign in / session | Login screen | Proves who you are and keeps you signed in. Includes password reset and token refresh. |
| Alert intake | *Upload logs*, connector webhooks | Takes raw logs or events from a connected tool and turns them into alerts. |
| Connectors | **Settings → Integrations**, *Configure* | Connects Okta, GitHub, Slack, Google Workspace, Azure AD. Handles the secret, the polling schedule, and now the source's time zone. |
| Decision feed | **Inbox / Brief** | The short list of things that need a human answer today, instead of a wall of alerts. |
| Case detail | **Case page** | One incident: what happened, what it touches, what NOCTRA suggests doing. |
| Why this verdict | **Case page → Why this verdict** | Shows each signal that moved the confidence figure, by how much, and every signal that could not be checked. The arithmetic adds up so you can audit it. |
| Approve / Decline / Revert | Buttons on the case page | The human decision. Approve runs the containment action; revert undoes it. |
| Ask NOCTRA | **Case page → Ask NOCTRA** | Ask a question about this specific case in plain language. |
| Case report / export | *Export*, *Download PDF* | A written record of the incident and what was decided. |
| Blast radius | Case page graph | Which other machines and accounts are connected to this one. |
| Response times | **Operate → Response Times** | How long the loop actually takes: detect, triage, decide, contain. Measured, with sample sizes. |

---

## 3. Supporting capabilities — needed, working

Real features with real data behind them, reachable from the UI.

| Capability | Where | What it does, plainly |
|---|---|---|
| Alerts list | **Alerts** | Every alert, filterable. The raw feed behind the cases. |
| Entities | **Entities** | People, machines and addresses seen across alerts, and how they link. |
| Detection rules | **Admin → Rules**, Sigma pages | The rules that decide what counts as suspicious. Includes testing a rule before enabling it. |
| SOAR playbooks | **Automation** | Pre-agreed response steps, so approving a case does something specific. |
| Detection coverage | **Operate → Detection Coverage** | Which attacker techniques you could actually catch, and where the gaps are. *Show only uncovered* narrows it to the gaps. |
| Asset inventory | **Operate → Asset Inventory** | Your machines and who owns them, with search and a crown-jewel filter. Feeds attack-path and blast-radius. |
| Data retention | **Operate → Data Retention** | How long each kind of record is kept. Legal holds can be placed and released here. |
| Erasure requests | **Operate → Erasure Requests** | GDPR right-to-erasure queue, with the one-month deadline tracked. |
| Approvals | **Operate → Approvals** | Actions waiting on a second pair of eyes before they run. Shows what is blocked, for how long, and which review stage it is at. You cannot approve a request you raised. |
| Attack paths | Case context, `/attack-path` | The route an attacker could take from an exposed service to something valuable. |
| Posture score | **Dashboard** | A single NIST-CSF-shaped number for how well set up you are, with the dimensions behind it. |
| Vulnerabilities, CSPM, SBOM, ZTNA, ITDR, deception, forensics, threat intel | **Modules** pages | Each shows the records that capability holds for your tenant. All 22 configured endpoints verified reachable. |
| Reports | **Reports** | Scheduled and on-demand summaries. |
| Admin: users, roles, API keys, SSO/SCIM, tenants, audit log | **Admin** | Who can use the system and what they did. |
| Compliance packs | **Compliance** | Evidence collection mapped to a framework. |

---

## 4. Machine-facing — correctly has no UI

Not gaps. These are called by other systems, not clicked.

| Group | Why there is no page |
|---|---|
| `/scim/v2/*` (6) | Your identity provider calls these to create and remove users automatically. |
| `/health/live`, `/health/ready` | Load balancer and container orchestration probes. |
| `/connectors/{id}/oauth/callback` | The provider redirects here during "Connect". |
| `/connectors/ingest/{id}` | Where a connected tool pushes events. |
| `/ocsf/*`, `/stream/*` | Machine-readable event formats and the live event stream. |
| `/telemetry`, `/pwa/push/*` | Browser-side plumbing. |

---

## 5. Real gaps — no UI, and there should be

Ordered by how much the absence costs.

| Capability | Endpoints | Why it matters |
|---|---|---|
| **Risk scoring rules** | 2 | You can record which assets are critical, but not the rules that turn criticality into alert priority. Half the feature is exposed. |
| **Attack surface (exposure)** | 5 | Hostnames discovered from Certificate Transparency. Feeds attack-path search, so operators cannot see or correct the inputs to a conclusion the product draws. |
| **Hunt execution** | 3 | Hunts can be written and listed but not run or reviewed from the UI. |
| **Posture history / findings** | 2 | The score is shown; the trend and the individual findings behind it are not. |
| **Threat-intel export (STIX/MISP)** | 4 | Sharing indicators with other tools. Common ask in procurement. |
| **Alert export / clear** | 2 | Bulk operations an analyst expects. |
| **Board pack** | 2 | Generates an executive report; nothing triggers it. Now that it carries measured response times instead of invented ROI, it is worth exposing. |

---

## 6. Known weaknesses — labelled, not hidden

Each is honest in the API today; none reports a fabricated result.

| Area | State |
|---|---|
| **Archival** | Counts what is *eligible*; moves nothing. No archive destination is configured. Reported as `status: "not_configured"` with the reason. |
| **Sigma matching** | Keyword matching, not a full Sigma engine. Docstring says so. |
| **Jira ticketing** | Simplified issue creation. |
| **Dark web / breach lookup** | No client exists. Reports `enabled: false` regardless of whether an API key is set. |
| **Connector field mappings** | Verified against realistic payloads in each provider's documented shape (`test_provider_payloads.py`); this found and fixed two real bugs. Not verified against live traffic, which needs paid tenants. A wrong mapping shows as 0% event-time coverage for that source. |
| **Naive timestamps** | Read as UTC unless the connector declares a zone. |
| **Pre-logging dwell time** | Not measurable by anything downstream of the log. |

---

## 7. Requirements

**Functional.** The core loop — ingest, triage, explain, decide, act, report —
is complete and integrated. The two differentiators identified in the market
research are implemented: transparent per-alert reasoning, and measured
outcomes. The main functional gap is approval workflows (§5).

**Non-functional.**

| Property | State |
|---|---|
| Honesty | Enforced by tests. Failures are 5xx, empty is distinguished from failed, unmeasurable is named. |
| Auditability | Confidence arithmetic is reproducible; audit log covers admin actions. |
| Multi-tenancy | `org_id` scoping throughout; verified by tests. |
| Security | ABAC permissions, encrypted connector secrets, SSRF guard on poll endpoints, HMAC on webhooks. |
| Performance | Measured to 26k alerts / 10.5k cases. Coverage evaluation was 66s and is now 6ms; response times 612ms; reasoning 5ms. Query counts pinned by `test_metrics_scale.py`. Not load-tested for concurrency. |
| Reliability | No retry/backoff review; `ha` module exists but is unexercised. |

---

## 8. What next

1. **Expose exposure findings** — operators cannot audit inputs that already
   drive attack-path conclusions.
2. **Wire an archive destination**, or remove the archive action until there is
   one.
3. **Hunt execution from the UI** — hunts can be written but not run.
4. **Concurrency testing** — single-request cost is now known; behaviour under
   parallel load is not.
5. **Confirm mappings against live traffic** when a tenant is available. The
   payload-shape tests cover the parsing; only real traffic proves the provider
   sends what its documentation says.
