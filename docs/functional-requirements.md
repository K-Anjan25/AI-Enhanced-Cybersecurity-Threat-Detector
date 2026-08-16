# Functional Requirements

**System:** AI-Enhanced Cybersecurity Threat Detector (v3 target)
**Owner / source:** SOC platform scope (multi-tenant, event-driven, K8s-ready)
**Document type:** Functional Requirements Specification (FRS)

Each requirement has a stable ID (`FR-xx`), a priority (MoSCoW: **M**ust, **S**hould,
**C**ould, **W**on't-this-release), and traceability into
[traceability-matrix.md](traceability-matrix.md).

---

## 1. Authentication & Authorization (AUTH)

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-AUTH-01 | Must | The system shall allow a user to register with a unique username and email and a password. |
| FR-AUTH-02 | Must | The system shall authenticate a registered user with username/email + password. |
| FR-AUTH-03 | Must | The system shall issue a short-lived access token and a refresh token on login. |
| FR-AUTH-04 | Must | The system shall support httpOnly `SameSite=Strict` cookie-based sessions when `COOKIE_AUTH=true` (no tokens in localStorage). |
| FR-AUTH-05 | Must | The system shall allow the client to refresh an expired access token using the refresh token. |
| FR-AUTH-06 | Must | The system shall revoke the refresh token (JTI blocklist) on logout. |
| FR-AUTH-07 | Must | The system shall rate-limit `/login` (default 10/min per client) and return 429 on exhaustion. |
| FR-AUTH-08 | Must | The system shall lock an account (`is_blocked`) after `LOGIN_MAX_ATTEMPTS` consecutive failures and reject further login. |
| FR-AUTH-09 | Must | The system shall reset `failed_login_attempts` on a successful login. |
| FR-AUTH-10 | Should | The system shall offer password reset via email; the reset link is only echoed by the API in non-production environments. |
| FR-AUTH-11 | Must | The system shall expose the current user's profile (`GET /user/me`). |
| FR-AUTH-12 | Must | The system shall allow a user to change their own password. |
| FR-AUTH-13 | Should | The system shall support role-based defaults: `USER`, `ANALYST`, `ADMIN`. |

## 2. Access Control (ABAC)

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-ABAC-01 | Must | The system shall evaluate permissions from subject attributes (role, clearance level, department, blocked/active status). |
| FR-ABAC-02 | Must | The system shall gate every protected endpoint with a permission check (`require_permission` / `require_any_permission`). |
| FR-ABAC-03 | Must | The system shall deny access to blocked or inactive accounts (empty permission set). |
| FR-ABAC-04 | Must | The system shall enforce clearance requirements for sensitive actions (e.g. `engine:update`, `audit:read`, `users:manage` require clearance 4). |
| FR-ABAC-05 | Should | The system shall evaluate resource-side conditions (e.g. analysts cannot export/clear CRITICAL alerts). |
| FR-ABAC-06 | Must | The system shall return 403 when an authenticated user lacks a permission. |

## 3. Multi-Tenancy (v3)

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-TENANT-01 | Must | The system shall represent organizations (`Org`) as first-class entities with a unique `slug`. |
| FR-TENANT-02 | Must | New registrations shall be assigned to a default organization. |
| FR-TENANT-03 | Must | Tenant-owned rows (users, alerts, scanned alerts, scan batches, cases) shall carry `org_id`. |
| FR-TENANT-04 | Must | On startup, the system shall seed a default org and backfill any legacy rows missing `org_id`. |
| FR-TENANT-05 | Must | The system shall scope every tenant-owned query to the current user's `org_id`. |
| FR-TENANT-06 | Should | Admin endpoints shall support cross-tenant listing/filtering for SOC administrators. |

## 4. Threat Ingestion & Detection

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-DETECT-01 | Must | The system shall accept a single log or network-flow record via `POST /analyze`. |
| FR-DETECT-02 | Must | The system shall classify records as network flows (contains `bytes` + `duration`) or system logs. |
| FR-DETECT-03 | Must | The system shall call the ML service for a prediction and map the anomaly score to a severity. |
| FR-DETECT-04 | Must | When the ML service is unreachable, the system shall retry (2 retries, 0.3/0.6 s backoff) then fall back to heuristics with a `fallback: True` flag. |
| FR-DETECT-05 | Must | Anomalous records shall be persisted as `SecurityAlert` rows. |
| FR-DETECT-06 | Must | Every alert shall be tagged with a MITRE ATT&CK tactic + technique via the mapper. |
| FR-DETECT-07 | Should | Every alert shall be enriched with source-IP reputation context from the threat-intel store. |
| FR-DETECT-08 | Must | The system shall support batch upload (`POST /upload-logs`) with a persisted `ScanBatch` session. |
| FR-DETECT-09 | Must | Uploaded scans shall run in a background task (`pending → processing → completed|failed`). |
| FR-DETECT-10 | Must | Each flagged line in a batch shall produce a `ScannedAlert` evidence row plus a `SecurityAlert` feed row. |
| FR-DETECT-11 | Must | The system shall expose upload progress/history via `GET /uploads/{id}`. |
| FR-DETECT-12 | Must | The system shall support toggling Kafka publishing (`ENABLE_KAFKA`) for raw logs, raw flows, normalized events, raised alerts, executed actions, and audit events. |

## 5. Alert & Incident Management

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-ALERT-01 | Must | The system shall list alerts, paginated and ordered most-recent-first. |
| FR-ALERT-02 | Must | The system shall expose alert statistics (total, severity distribution, by type, recent) for dashboard KPIs. |
| FR-ALERT-03 | Must | The system shall support exporting alerts as CSV. |
| FR-ALERT-04 | Must | The system shall allow clearing alerts (permission `alerts:delete`). |
| FR-ALERT-05 | Must | The system shall allow creating an incident `Case` linked optionally to a source alert. |
| FR-ALERT-06 | Must | The system shall support case lifecycle: `open → triaging → resolved → closed`, org-scoped. |
| FR-ALERT-07 | Must | The system shall allow updating case status, priority, assignee, title and description. |
| FR-ALERT-08 | Must | The system shall reject invalid case status/priority values with 400. |
| FR-ALERT-09 | Must | Case and alert actions shall be written to the append-only audit trail. |

## 6. Detection Engine Administration

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-ENGINE-01 | Must | The system shall expose engine settings (sensitivity, concurrent scans, auto-quarantine, retention). |
| FR-ENGINE-02 | Must | The system shall allow updating engine settings with the `engine:update` permission. |
| FR-ENGINE-03 | Should | The system shall manage detection rules (CRUD, name-unique, active toggle, severity). |
| FR-ENGINE-04 | Should | The system shall manage IP reputation entries (upsert, list, block flag) with `reputation:*` permissions. |

## 7. Audit & Observability

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-AUDIT-01 | Must | The system shall record administrative and triage actions in `audit_logs`. |
| FR-AUDIT-02 | Must | The audit log shall be append-only (ORM rejects UPDATE/DELETE). |
| FR-AUDIT-03 | Must | The system shall expose paginated audit logs with `audit:read` permission. |
| FR-AUDIT-04 | Should | The system shall expose `/health/live` and `/health/ready` probes. |
| FR-AUDIT-05 | Should | Requests shall be traceable via `X-Request-ID` in structured access logs. |

## 8. Dashboard (UX)

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-UI-01 | Must | The dashboard shall provide login/register flows using cookie-based auth. |
| FR-UI-02 | Must | The dashboard shall visualize threat alert KPIs and charts (severity distribution, recent alerts). |
| FR-UI-03 | Must | The dashboard shall list, filter and export alerts. |
| FR-UI-04 | Should | The dashboard shall provide incident/case management screens. |
| FR-UI-05 | Should | The dashboard shall expose admin controls (engine settings, rules, IP reputation). |
| FR-UI-06 | Should | The dashboard shall render the audit log and per-role access states. |
| FR-UI-07 | Should | The dashboard shall display MITRE ATT&CK + threat-intel context per alert. |

## 9. Streaming / Eventing (v3 target)

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-STREAM-01 | Must | The system shall publish normalized events to `events.normalized` (tenant-keyed). |
| FR-STREAM-02 | Must | The system shall publish raised alerts to `alerts.raised`. |
| FR-STREAM-03 | Should | The system shall consume alerts to drive automated actions via `actions.executed` (SOAR engine + manual trigger). |
| FR-STREAM-04 | Should | The system shall extract threat entities and build an attack graph from the event backbone. |
| FR-STREAM-05 | Could | The system shall support training-serving pipeline for the ML service (train → serve). |
