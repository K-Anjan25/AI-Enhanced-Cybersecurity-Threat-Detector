# Target System Architecture — Layered View (v3)

> Architectural **target state** after the restructure.
> Strategy: **event-driven microservices on Kafka**, **K8s-ready**, running on
> Docker Compose today. Stack: Python (FastAPI) kept for API/ML, Go/Rust only
> if the hot path demands it later.

```mermaid
flowchart TB
    subgraph P["PRESENTATION (React SPA)"]
        UI["SOC Dashboard v3"]
        PAGES["Alerts · Cases · Graph Explorer · Analytics<br/>SOAR Playbooks · Admin/Tenants · Threat Intel"]
        REALTIME["WebSocket / SSE live feed"]
        GRAPH["Graph explorer (React Flow / Cytoscape)"]
    end

    subgraph EDGE["EDGE / GATEWAY"]
        LB["Ingress: Nginx/Traefik · TLS"]
        GW["API Gateway: auth (httpOnly cookie JWT)<br/>tenant resolution (X-Tenant-ID) · rate limit"]
    end

    subgraph API["API / PLATFORM"]
        API1["api-service (FastAPI)<br/>REST: alerts, cases, rules, reputation, admin"]
        WS["WS-gateway: realtime events"]
    end

    subgraph INGEST["INGEST"]
        IN1["ingest-service: file/API ingestion<br/>validate + normalize"]
        COL["Collectors/agents (future)<br/>log shippers, network taps"]
        PR["producers -> Kafka raw-* topics"]
    end

    subgraph STREAM["EVENT BACKBONE (Kafka + Schema Registry)"]
        K1["raw-logs / raw-flows"]
        K2["events.normalized"]
        K3["alerts.raised"]
        K4["actions.executed"]
        K5["audit.events"]
    end

    subgraph DETECT["DETECTION"]
        DW["detection-worker (Kafka consumer)<br/>normalize -> features -> score"]
        ML["ml-serving (online predict)<br/>log/network/dns/email + fallback heuristics"]
        INTEL["threat-intel-service<br/>IoC feeds, enrichment, reputation cache"]
        ATTACK["ATT&CK mapper: technique tagging"]
    end

    subgraph ORCH["ORCHESTRATION / SOAR"]
        SOAR["playbook-engine: on alert.raised<br/>evaluate rules -> actions"]
        AD["action adapters: block IP, quarantine,<br/>notify, ticketing"]
    end

    subgraph CASE["INCIDENT MANAGEMENT"]
        CASE["case-service: lifecycle, assignment,<br/>comments, SLA timers"]
    end

    subgraph GRAPH["ENTITIES"]
        GS["graph-service: entity resolution +<br/>relationships, attack paths"]
        NEO[("Neo4j (Phase 2)<br/>fallback: Postgres edges")]
    end

    subgraph MLPLAT["ML TRAIN / SERVE"]
        TR["ml-training: versioned jobs,<br/>eval, drift checks"]
        FS["feature-store (Feast or simple SQL)"]
        REG["model-registry (MLflow / MinIO artifacts)"]
    end

    subgraph DATA["DATA PLANE"]
        PG[("PostgreSQL: orgs, users,<br/>cases, alerts, rules, reputation")]
        CH[("ClickHouse: long-term logs + analytics (Phase 2)")]
        RD[("Redis: cache, rate-limit,<br/>idempotency, pub/sub")]
        S3[("MinIO/S3: raw archives, model artifacts")]
    end

    UI --> PAGES & REALTIME & GRAPH
    PAGES --> LB --> GW
    REALTIME --> WS
    WS --> API1
    GW --> API1
    API1 --> PG & RD

    IN1 --> PR
    COL --> PR
    PR --> K1
    K1 --> DW
    DW --> K2
    DW --> ML & INTEL
    ML --> REG --> TR
    TR --> FS --> ML
    DW --> ATTACK
    ATTACK --> K3
    K3 --> SOAR & CASE
    SOAR --> K4
    SOAR --> AD
    CASE --> PG
    GS --> NEO
    GW --> CASE
    K3 --> GS
    GS --> GRAPH
    K5 --> PG
    INTEL --> RD
    API1 --> S3
```

## Layer responsibilities

| Layer | Responsibility | Notes |
| --- | --- | --- |
| Presentation | SOC dashboard, realtime feed, graph explorer | React; per-tenant UI isolation |
| Edge/Gateway | TLS, auth, tenant resolution, rate limit | Stateless; scales horizontally |
| API/Platform | REST for dashboard + admin; WS gateway | FastAPI; thin, delegates to services |
| Ingest | Normalize files/events, publish to Kafka | Push everything into the backbone |
| Event backbone | Durable, ordered, replayable event log | Kafka topics = system of record for events |
| Detection | Consume → feature → score → dedupe → alert | Idempotent consumers; `event_id` dedup |
| SOAR | Playbooks + action adapters | Auto-containment w/ human-in-the-loop |
| Incident | Case lifecycle & SLA | Links alerts, entities, audit trail |
| Entities | Entity resolution, relationship graph, attack paths | Neo4j Phase 2; Postgres edges first |
| ML platform | Train/serve/version models, feature store | MLflow registry, Feast optional |
| Data plane | Transactional core, analytics, cache, archive | Compose now, K8s + managed later |
