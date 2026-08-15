# Component Diagram — v3 Microservices

> UML **Component Diagram** (structural) showing how the v3 system is packaged
> into deployable components and the interfaces they expose / consume.
> Mirrors `target-architecture.md` at the component level (event-driven, K8s-ready).

```mermaid
flowchart LR
    subgraph Client["Client Layer"]
        UI["Dashboard SPA<br/>(React + Vite, port 3000)"]
        API_CLI["External SIEM / Agents<br/>(HTTP + Kafka producers)"]
    end

    subgraph Edge["Edge Layer"]
        GW["API Gateway / Reverse Proxy<br/>(cookies, TLS, rate limit)"]
    end

    subgraph Core["Backend (FastAPI, port 8000)"]
        AUTH["Auth Service<br/>(JWT httpOnly cookies, lockout)"]
        ABAC["ABAC Policy Engine"]
        INGEST["Ingestion Service<br/>(upload, batch scan)"]
        ALERT["Alert Service<br/>(process_log / process_batch)"]
        CASE["Case Service<br/>(incident lifecycle)"]
        MITRE["MITRE ATT&CK Mapper"]
        AUDIT["Audit Service<br/>(append-only)"]
    end

    subgraph Data["Data Layer"]
        PG[("PostgreSQL<br/>(tenanted tables)")]
    end

    subgraph ML["ML Layer"]
        MLSVC["ML Service<br/>(port 8001)"]
        MLPROXY["ML Client<br/>(retry + heuristic fallback)"]
    end

    subgraph Stream["Event Backbone (Kafka)"]
        T1["raw-logs"]
        T2["raw-flows"]
        T3["events.normalized"]
        T4["alerts.raised"]
        T5["actions.executed"]
        T6["audit.events"]
    end

    UI -->|HTTPS + cookies| GW
    API_CLI -->|ingest| GW
    GW --> AUTH
    GW --> INGEST
    INGEST --> ALERT
    ALERT --> MITRE
    MITRE --> PG
    ALERT --> PG
    CASE --> PG
    AUDIT --> PG
    AUTH --> ABAC
    ABAC -.guard.- ALERT
    ABAC -.guard.- CASE
    ABAC -.guard.- AUDIT

    INGEST -->|publish| T1
    INGEST -->|publish| T2
    ALERT -->|publish| T3
    ALERT -->|publish| T4
    CASE -->|publish| T5
    AUDIT -->|publish| T6

    ALERT -->|REST predict| MLPROXY
    MLPROXY -->|REST /predict*| MLSVC
    MLSVC --> MLPROXY
    MLPROXY --> ALERT
```

## Component responsibilities

| Component | Key interfaces | Depends on |
| --- | --- | --- |
| Auth Service | `POST /login`, `/refresh`, `/logout`, `/register` | PostgreSQL, ABAC |
| Ingestion Service | `POST /upload-logs`, `GET /uploads/{id}` | Kafka (`raw-logs`, `raw-flows`), PostgreSQL |
| Alert Service | `POST /analyze`, `GET /alerts` | ML Client, MITRE mapper, Kafka, PostgreSQL |
| MITRE Mapper | `map_alert(alert_type, message)` → tactic/technique | none (static rules) |
| Case Service | `GET/POST /cases`, `PATCH /cases/{id}` | ABAC, PostgreSQL, Kafka (`actions.executed`) |
| Audit Service | `GET /audit-logs` | PostgreSQL, Kafka (`audit.events`) |
| ML Client | retry + heuristic fallback | ML Service |
| ML Service | `/predict/log`, `/predict/network` | trained models |

> **Current state (v3 Phase 1):** Auth, Ingestion, Alert, Case, Audit and the ML
> client/mapper are implemented in `backend/app`. Kafka publishing is wired via
> `kafka_producer.py` (topics `raw-logs` … `audit.events`); consuming services
> (SOAR, threat-intel, entity graph) are the next phase.
