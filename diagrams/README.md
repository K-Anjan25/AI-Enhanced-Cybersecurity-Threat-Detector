# System Diagrams

UML and architectural diagrams for the **AI-Enhanced Cybersecurity Threat Detector**.

All diagrams are written in [Mermaid](https://mermaid.js.org/) — paste them into
[Mermaid Live Editor](https://mermaid.live/), or render them natively on
GitHub/GitLab when viewed from a Markdown file.

## Index

| File | Diagram | UML type |
| --- | --- | --- |
| [`target-design.md`](target-design.md) | **v3 target** deployment topology + data flow (Kafka, multi-tenant, SOAR, K8s-ready) | Deployment / System Design |
| [`target-architecture.md`](target-architecture.md) | **v3 target** layered architecture (event-driven microservices) | Architecture / Component |
| [`system-design.md`](system-design.md) | v2 deployment topology of all services & how they connect | Deployment / System Design |
| [`system-architecture.md`](system-architecture.md) | v2 layered view of the application stack | Architecture / Component |
| [`class-diagram.md`](class-diagram.md) | Backend domain classes & their relationships | Class Diagram |
| [`component-diagram.md`](component-diagram.md) | v3 microservice components, interfaces & Kafka topics | Component Diagram |
| [`state-diagram.md`](state-diagram.md) | ScanBatch & Case (incident) state machines | State Machine Diagram |
| [`activity-diagram.md`](activity-diagram.md) | End-to-end log → alert → incident pipeline (ML failover) | Activity Diagram |
| [`timing-diagram.md`](timing-diagram.md) | Login rate-limit/lockout & session/refresh lifecycle | Timing Diagram |
| [`usecase-diagram.md`](usecase-diagram.md) | Actors and functional use cases | Use Case Diagram |
| [`sequence-diagram.md`](sequence-diagram.md) | Login → dashboard → alert ingest message flow | Sequence Diagram |
| [`collaboration-diagram.md`](collaboration-diagram.md) | Object communications for a SOC workflow | Collaboration / Communication |

## Repository layout

```text
backend/     FastAPI REST API (port 8000) + SQLAlchemy models + ABAC policy engine
dashboard/   React (Vite) SPA, Redux + React-Query (port 3000)
ml-service/  AI threat detection microservice (port 8001): network/log/email/DNS models
docker/      docker-compose for PostgreSQL + Kafka + Zookeeper
datasets/    training datasets (CICIDS2017 ...)
```

## How to keep them up to date

The diagrams are generated straight from the code. When you change the API
surface, permission catalog (`backend/app/core/abac.py`), data models
(`backend/app/models/*`), or dashboard pages, update the corresponding diagram
in the same change.

## Alert tables — what lives where

The system deliberately uses **two alert tables plus one session table**. They
serve different purposes and are **not** duplicated data:

| Table | Written by | Purpose |
| --- | --- | --- |
| `security_alerts` (`SecurityAlert`) | Engine detections (Kafka/log-scan) | The operational alert feed shown on Threat Alerts. Filterable, paginated (`GET /alerts`), drives KPIs. |
| `scanned_alerts` (`ScannedAlert`) | `process_batch` for uploaded files | Evidence rows for each flagged line in a user-uploaded log batch. Backs drill-down on upload scans. |
| `scan_batches` (`ScanBatch`) | `POST /upload-logs` | One row per upload session; tracks `pending → processing → completed/failed` so history survives restarts. |

Every uploaded-file anomaly also produces a `security_alerts` row (type
`scanned_log`), so uploaded threats still appear in the main feed while the
`scanned_alerts` row preserves the original log line as evidence.

> **Current state:** models are `Org` (multi-tenant v3), `User`, `SecurityAlert`,
> `ScannedAlert`, `ScanBatch`, `Case` (incident lifecycle), `TokenBlocklist`,
> `DetectionRule`, `IpReputation`, `EngineSetting`, `AuditLog`. All
> tenant-owned tables carry `org_id` (`users`, `security_alerts`,
> `scanned_alerts`, `scan_batches`, `cases`); `register` assigns the seeded
> `default` org and `ensure_default_org` backfills legacy rows on startup.
> `GET /alerts` is paginated (`?page=&limit=` → `{items,total,page,limit}`).
> Log uploads run in a background task with persisted `scan_batches` history;
> the ML client retries then falls back to heuristics when the service is
> unreachable; MITRE ATT&CK mapping tags every alert with
> tactic/technique via `mitre.map_alert`.
>
> **Security hardening:** `/login` is rate-limited and locks accounts after N
> consecutive failures (`failed_login_attempts`, `is_blocked`); JWTs move to
> httpOnly SameSite cookies when `COOKIE_AUTH=true` (no tokens in
> localStorage); `audit_logs` is append-only (ORM rejects UPDATE/DELETE);
> `reset_link` is only echoed in non-production environments; `X-Request-ID`
> tracing + structured access logs and `/health/live` + `/health/ready` probes
> are available.
>
> **Multi-tenancy (v3, Phase 1):** Kafka topics are now `raw-logs`,
> `raw-flows`, `events.normalized`, `alerts.raised`, `actions.executed`,
> `audit.events`; producer helpers are tenant-keyed and publish per-topic.

> **Phase 2 (in progress):** SOAR (Security Orchestration, Automation and
> Response) evaluates raised alerts against active `DetectionRule`s and
> executes/publishes `actions.executed` (`soar_actions` audit table;
> `POST /soar/evaluate` dry-run + `POST /soar/trigger/{id}`). The
> entity/attack-graph service extracts nodes (ip, domain, hash, email, file)
> and directed edges (`entities`, `entity_links`) from every persisted alert
> (`GET /entities[/{id}/graph]`). MITRE + threat-intel + graph context now
> accompany each alert end-to-end.