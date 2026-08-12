# System Architecture — Layered View

> UML **Architecture / Component** view of the application stack.

```mermaid
flowchart TB
    subgraph P["PRESENTATION"]
        R["React Router<br/>RequireAuth (RBAC+ABAC)"]
        PG1["Pages: ThreatAlerts, LogHistory, AIAnalytics<br/>Profile, Account, Admin/*"]
        CMP["Components: AlertList, TableWithAction,<br/>Navbar, DashboardLayout, modals"]
    end
    subgraph C["CLIENT STATE / IO"]
        STORE["Redux (userSlice)<br/>token + permissions sync"]
        Q["react-query cache"]
        API1["api/*: axios interceptor<br/>injects Bearer token"]
        VAL["validators: yup schemas"]
    end
    subgraph A["APPLICATION / API (FastAPI)"]
        M["main.py (CORS, startup migrations)"]
        R1["Routers (11 modules)"]
        DEP["dependencies: get_db,<br/>get_current_user, require_permission"]
    end
    subgraph S["SERVICE / BUSINESS"]
        US["user_service: profile/password"]
        AS["alert_service: process_log, stats"]
        IS["item_service: rules, reputation,<br/>engine settings, audit"]
        ML1["ml_client: HTTP to ML svc"]
        KP["kafka_producer/consumer"]
    end
    subgraph POL["POLICY"]
        ABAC["core/abac.py<br/>subject_permissions, can(),<br/>require_permission"]
        SEC["core/security.py<br/>JWT access/refresh, bcrypt"]
    end
    subgraph D["DATA (SQLAlchemy ORM)"]
        M1["models: User, SecurityAlert, ScannedAlert,<br/>TokenBlocklist, DetectionRule,<br/>IpReputation, EngineSetting, AuditLog"]
    end
    subgraph EXT["EXTERNAL"]
        E1[("Postgres")]
        E2["ML Service :8001"]
        E3["Kafka :9092"]
        E4["SMTP"]
    end

    R --> PG1 --> CMP
    CMP --> STORE & Q
    CMP --> API1 --> VAL
    API1 -- HTTP JSON + JWT --> M
    M --> R1 --> DEP
    R1 --> US & AS & IS
    DEP --> POL --> SEC
    US & AS & IS --> M1 --> E1
    AS --> ML1 --> E2
    AS --> KP --> E3
    US --> E4
```

## Layer responsibilities

| Layer | Key files | Responsibility |
| --- | --- | --- |
| Presentation | `dashboard/src/{App,pages,features,layouts}/*` | Route/UI, permission-gated navigation |
| Client state/IO | `dashboard/src/{store,api,utils}/*` | Redux user state, axios JWT injection, query cache |
| Application/API | `backend/app/api/v1/*` | REST routes + dependency injection |
| Policy | `backend/app/core/{abac,security}.py` | ABAC decisions, JWT/bcrypt |
| Service | `backend/app/services/*` | Business logic, ML proxying, Kafka, audit |
| Data | `backend/app/models/*` | SQLAlchemy ORM mapped to Postgres |
| External | docker-compose services | Postgres, Kafka/Zookeeper, ML, SMTP |