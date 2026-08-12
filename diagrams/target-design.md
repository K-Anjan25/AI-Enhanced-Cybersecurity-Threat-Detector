# Target System Design — Deployment Topology & Data Flow (v3)

> Deployment view of the restructured platform, mapped to **Docker Compose
> today → Kubernetes tomorrow**. All services expose `/health/live` +
> `/health/ready`; shared config via env + a small config service.

```mermaid
flowchart LR
    subgraph BROWSER["Browser"]
        SPA["React SOC Console"]
    end

    subgraph EDGE["Edge (Compose: nginx | K8s: Ingress)"]
        GW["API Gateway<br/>JWT cookies · X-Tenant-ID · rate limit"]
    end

    subgraph APP["App Plane"]
        API["api-service (FastAPI :8000)<br/>REST + WS"]
    end

    subgraph ING["Ingest Plane"]
        ING1["ingest-service (:8002)<br/>uploads + normalization"]
        COL["agents/collectors (future)"]
    end

    subgraph KB["Event Backbone (Kafka :9092)"]
        T1["raw-logs"]
        T2["raw-flows"]
        T3["alerts.raised"]
        T4["actions.executed"]
    end

    subgraph DET["Detection Plane"]
        DW["detection-worker<br/>(consumer group)"]
        MLS["ml-serving (:8001)<br/>log/network/dns/email"]
        TI["threat-intel-service (:8003)"]
        SOAR["playbook-engine (:8004)"]
    end

    subgraph MGT["Management Plane"]
        CASE["case-service (:8005)"]
        GRA["graph-service (:8006)"]
        TRN["ml-training (cron/CI)"]
    end

    subgraph DATA["Data Plane (Compose services)"]
        PG[("Postgres :5432")]
        CH[("ClickHouse :8123 (Phase 2)")]
        RD[("Redis :6379")]
        MC[("MinIO :9000 — archives,<br/>model artifacts")]
        REG["MLflow Registry (:5000)"]
    end

    SPA -- HTTPS/JSON + WS --> GW
    GW --> API
    API --> PG & RD

    ING1 --> T1 & T2
    COL --> T1
    API -- "submit events" --> ING1

    T1 & T2 --> DW
    DW --> MLS & TI
    DW -- "alerts.raised" --> T3
    DW --> PG & CH

    T3 --> SOAR & CASE
    SOAR -- "actions.executed" --> T4
    SOAR --> PG
    CASE --> PG
    GRA --> PG
    GW --> CASE & GRA

    MLS --> REG
    TRN --> REG
    REG --> MC
    TRN --> RD
```

## Data flow — one alert end to end

```mermaid
sequenceDiagram
    participant C as Collector/Upload
    participant I as ingest-service
    participant K as Kafka
    participant D as detection-worker
    participant M as ml-serving
    participant S as playbook-engine (SOAR)
    participant Cs as case-service
    participant G as graph-service
    participant P as Postgres

    C->>I: raw log / flow
    I->>K: raw-logs (tenant-keyed partition)
    D->>K: consume raw-logs
    D->>M: predict (features)
    M-->>D: anomaly_score, is_anomaly
    D->>D: dedupe by event_id (Redis)
    D->>P: upsert SecurityAlert (org_id)
    D->>K: alerts.raised
    S->>K: consume alerts.raised
    S->>S: evaluate playbook (severity, tags)
    S->>P: containment decision / audit
    S->>K: actions.executed
    Cs->>K: consume alerts.raised
    Cs->>P: auto-create incident if HIGH+
    G->>K: consume alerts.raised
    G->>P: link entities/edges (attack path)
    G-->>UI: graph updates (WS)
```

## Multi-tenancy design

| Concern | Approach |
| --- | --- |
| Identity | JWT carries `user_id`, `org_id`, roles; tenant resolved at gateway |
| Data isolation | `org_id` on every tenant-owned table; **Postgres RLS** as defense-in-depth |
| Kafka | per-tenant routing key → partition locality; consumer groups per org where needed |
| UI | org-scoped menus; cross-tenant visibility only via admin service |
| Quotas | per-org rate limits + storage quotas in Redis/ClickHouse |

## K8s-readiness (built in from day one)

- All services = **stateless 12-factor** containers (state only in data plane).
- Config via env; secrets via K8s Secrets (Vault later).
- Liveness/readiness probes on every service.
- Horizontal scaling: API/detection/ingest scale via replicas; Kafka partitions
  set accordingly.
- Observability: structured logs + `X-Request-ID`, metrics (Prometheus) and
  tracing (OpenTelemetry) added in Phase 2.
- Helm chart / Kustomize manifests land in `deploy/k8s`.

## Migration phases

| Phase | Scope | Deliverable |
| --- | --- | --- |
| **1 — Event backbone + multi-tenant core** | Kafka producers/consumers, ingest-service, detection-worker, `org_id` model + RLS, cases, threat-intel, ATT&CK tags | Compose runs; monolith split; tests green |
| **2 — Analytics + automation + graphs** | ClickHouse, SOAR playbooks + adapters, Neo4j graph, MLflow registry + feature store | Real-time dashboards, auto-containment, attack graphs |
| **3 — K8s** | Helm/Kustomize, HPA, OpenTelemetry, managed Kafka/Postgres/Redis | Production rollout |

## What stays vs what changes

| Aspect | Current (v2) | Target (v3) |
| --- | --- | --- |
| Dashboard | React + Redux | Same, + Graph Explorer, Cases UI, WS live feed |
| Backend | FastAPI monolith (`backend/`) | API service + ingest + detection + case + graph + intel + SOAR |
| Eventing | optional Kafka flag | Kafka = mandatory backbone |
| Log analytics | Postgres only | ClickHouse for long-term/trends |
| ML | heuristics + trained models in one svc | train/serve separated, versioned, feature store |
| Tenancy | single-tenant | multi-tenant `org_id` + RLS |
| Auth | JWT + ABAC | JWT(cookies) + ABAC, tenant-scoped |
| Rules | DetectionRule table | Rules + SOAR playbooks + ATT&CK mapper |
