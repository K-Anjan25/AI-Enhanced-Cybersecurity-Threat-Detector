# System Design — Deployment Topology

> UML **Deployment / System Design** view of all services and how they connect.

```mermaid
flowchart LR
    subgraph SOC["SOC Dashboard (React/Vite)"]
        USER["<b>:user</b> Analyst / Admin"]
        UI["SPA pages (Login, Alerts, Analytics, Admin)<br/>Redux + React-Query + Axios"]
    end

    subgraph API["API Layer — FastAPI (uvicorn :8000)"]
        ROUTERS["REST Routers /api/v1<br/>auth · users · alerts · ingest · admin<br/>engine · audit · analytics · rules · reputation"]
        ABAC["ABAC Policy Engine<br/>core/abac.py"]
    end

    subgraph ML["AI Threat Detection Microservice (:8001)"]
        MLAPI["FastAPI /predict/{network,log,email,dns}"]
        MODELS["IsolationForest · TF-IDF+LR<br/>heuristic fallbacks"]
    end

    subgraph DATA["Data Layer"]
        PG[("PostgreSQL threat_ai_db<br/>9 tables")]
        KAFKA[("Kafka/Zookeeper (optional)<br/>docker compose")]
        SMTP["SMTP (optional)<br/>reset emails"]
    end

    USER --> UI
    UI -- "HTTPS/JSON<br/>Bearer JWT" --> ROUTERS
    ROUTERS --> ABAC
    ABAC --> PG
    ROUTERS -- "ingest/analytics" --> ALERT_SVC["Services<br/>alert_service / item_service"]
    ALERT_SVC -- "HTTP /predict/*" --> MLAPI
    MLAPI --> MODELS
    ALERT_SVC --> PG
    ALERT_SVC -- "kafka producer (optional)" --> KAFKA
    KAFKA -- "kafka consumer" --> LD["log scan -> SecurityAlert"]
    ROUTERS -- "forgot/reset password" --> SMTP
```

## Notes

- **Running now:** backend uvicorn on `:8000`, dashboard Vite on `:3000`,
  PostgreSQL on `5432` (`threat_ai_db`).
- **Optional services:** ML service (`:8001`) and Kafka are opt-in. They are
  toggled via `ENABLE_KAFKA` in `backend/app/core/config.py`. When the ML
  service is unreachable, `ml_client.py` calls fail; the local heuristic
  fallbacks live *inside* the ML service itself.
- **Auth boundary:** every dashboard request carries a `Bearer <JWT>`; the
  backend validates it in `get_current_user` and then evaluates the ABAC policy
  for the route's required permission.