# NOCTRA Terminology Playbook
*Dogfooding security jargon — plain English first, formal technical always available.*

Analysts using NOCTRA are often founders, IT generalists or engineers, not trained SOC
operators. The pain point: jargon (blast radius, MITRE, SOAR, action_type) reads like a
different language. This playbook is the rulebook we eat our own cooking by — the UI keeps
every term formal and precise, but a plain-English gloss is never more than one
hover/focus away.

## Rules

1. **Every technical term in the UI is dogfooded** — it exists in
   `dashboard/src/constants/terms.ts` with a `plain` gloss and a `formal` definition,
   or it is annotated inline with `<Term plain="…" formal="…">`.
2. **Display stays formal.** Never dumb down the label — `REVOKE_CREDENTIALS` stays
   `REVOKE_CREDENTIALS`, `MITRE T1078` stays `MITRE T1078`. The plain gloss explains it.
3. **First occurrence on a screen may render the plain gloss inline** (e.g. the case
   page's "Blast radius — affected assets" heading), then dotted-underline for the rest.
4. **Tooltip contract** — title: the term + "in plain English"; body: one-sentence gloss;
   footer: "Technical" + the formal definition. Never color-only, never a dead tooltip
   (if a term has no gloss, it renders as plain text).
5. **Add, don't hack.** New jargon in copy → add to `terms.ts` (and this table). A
   one-off never gets a tooltip.

## The dictionary

| Term | Plain (tooltip) | Formal |
| --- | --- | --- |
| blast radius | What's affected — every account, host, IP and file connected to this incident. | Entity graph reachable from the case's root entity. |
| confidence | How sure NOCTRA is, based on the evidence it actually has. | Normalized model/heuristic probability (0–100%). |
| MITRE | A shared industry catalog of attacker techniques. | MITRE ATT&CK knowledge base of adversary tactics and techniques. |
| T1078 | Valid Accounts — the attacker signed in with a real credential. | MITRE ATT&CK T1078: Valid Accounts. |
| T1566 | Phishing — an email designed to trick someone. | MITRE ATT&CK T1566: Phishing. |
| T1048 | Exfiltration — data moving out to an attacker-controlled place. | MITRE ATT&CK T1048: Exfiltration Over Alternative Protocol. |
| T1098 | Account manipulation — attacker changed account settings to keep access. | MITRE ATT&CK T1098: Account Manipulation. |
| SOAR | Automation that turns rules into recorded actions. | Security Orchestration, Automation and Response engine. |
| playbook | A saved, repeatable sequence of automated steps. | Reusable SOAR workflow definition. |
| record-only | NOCTRA writes the action to the log but never runs it. | SOAR in record-only mode: action row persisted, no external side effects. |
| reversible | The action can be undone; NOCTRA tells you how. | Compensating control drafted before approval. |
| REVOKE_CREDENTIALS | Revoke this login so the stolen password stops working. | SOAR action type: disable/rotate credential, invalidate sessions. |
| connector | A live link to one of your tools. | Ingestion connector: authenticated source with sync status. |
| telemetry | The raw signals your tools send NOCTRA. | Structured event stream normalized for detection. |
| entity | A thing NOCTRA tracks — account, host, IP, domain or file. | Typed node in the entity graph. |
| IOC | A known-bad indicator — suspicious IP, hash or domain. | Indicator of Compromise. |
| reputation | How trustworthy an IP or domain looks. | Threat-intel reputation score. |
| provenance | Where a piece of evidence came from. | Source attribution for an evidence record. |
| remediation | The fix for what went wrong. | Planned corrective action targeting the root cause. |
| case | One incident NOCTRA walks you through. | Investigation unit aggregating evidence + decision state. |
| decision | Your call — approve, decline, or reverse. | Human gate in the analyst loop, persisted + audited. |
| undo | The exact step to reverse an action. | Compensating action recorded with the original. |
| detection | A rule or model that flags unusual behavior. | Heuristic/ML/rule evaluation producing an alert. |
| pending decision | A case waiting for your approve or decline call. | Case in `pending` decision state with a drafted action. |
| auto-recorded | Recorded automatically by a rule, still reversible and audited. | SOAR action auto-recorded by rule evaluation, record-only. |

## Audit — jargon density before this pass (grep hits)

| Screen | Hits | Dogfooded now |
| --- | --- | --- |
| SoarPage | 43 | ✅ (SOAR, playbook ×4, record-only, action types, status labels) |
| CasePage | 20 | ✅ (blast radius, MITRE, T1078, action type, reversible, confidence, record-only) |
| ReputationPage | 19 | ✅ (reputation, blacklist) |
| BriefPage | 15 | ✅ (needs your decision, auto-recorded) |
| AlertDetailModal | 14 | ✅ (MITRE, technique ids, reputation) |
| DashboardOverviewPage | 11 | ✅ (MITRE technique ids) |

Component: `dashboard/src/components/ui/Term.tsx` — `<Term mono>REVOKE_CREDENTIALS</Term>`.
Primitives widened to accept ReactNode so annotations can sit in page headers, empty
states, badges and table cells: `PageHeader.title/description`, `EmptyState.description`.
