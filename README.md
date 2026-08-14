# AI-Enhanced Cybersecurity Threat Detector

An end-to-end cybersecurity system that detects anomalous network traffic, malicious logs, phishing emails, and suspicious DNS queries using machine learning and stream processing.

The project supports both **local (REST)** and **streaming (Kafka)** execution modes.

---

## Architecture

```
 ┌────────────┐   REST / Kafka   ┌─────────────┐   HTTP   ┌─────────────┐
 │  Dashboard │ ───────────────▶ │   Backend   │ ───────▶ │  ML Service │
 │  (React)   │ ◀─────────────── │  (FastAPI)  │ ◀─────── │  (FastAPI)  │
 └────────────┘                  └─────────────┘          └─────────────┘
                                       │                      │
                                       ▼                      ▼
                                  PostgreSQL (alerts,      scikit-learn models
                                  users, audit, rules)     (IsolationForest,
                                                           TF-IDF + logistic)
```

- Events are ingested via REST or Kafka
- The backend calls the ML service for prediction and stores alerts in PostgreSQL
- The React dashboard visualizes alerts, analytics, incident management, entity/attack-graph pivoting, SOAR automation, admin controls, and audit logs

## Tech Stack

- **Backend**: Python / FastAPI, SQLAlchemy, PostgreSQL (SQLite for tests), JWT auth (JTI + refresh tokens), optional Kafka streaming
- **ML Service**: Python / FastAPI, scikit-learn (IsolationForest), TF-IDF + LogisticRegression, pandas, joblib
- **Frontend**: React, TypeScript, Tailwind CSS, Redux Toolkit, Recharts
- **Infrastructure**: Docker, Docker Compose (Kafka, Zookeeper, PostgreSQL)

## Project Structure

```
AI-Enhanced-Cybersecurity-Threat-Detector/
├── backend/                # FastAPI backend service
│   ├── app/
│   │   ├── api/v1/endpoints/  # auth, users, alerts, ingest, admin, engine,
│   │   │                       # audit, analytics, rules, reputation
│   │   ├── core/               # config, database, security
│   │   ├── models/             # ORM models (User, SecurityAlert, DetectionRule,
│   │   │                       # IpReputation, EngineSetting, AuditLog, ...)
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # alert, item, user, ml_client, kafka
│   │   ├── utils/              # helpers (severity, pagination, audit)
│   │   └── main.py
│   ├── tests/               # pytest (unit + API tests)
│   ├── requirements.txt
│   └── pyproject.toml
├── ml-service/             # FastAPI ML microservice
│   ├── app/
│   │   ├── main.py             # /predict/* endpoints
│   │   ├── network_model.py    # IsolationForest flow anomaly detection
│   │   ├── log_model.py        # log attack classification
│   │   ├── email_model.py      # phishing detection
│   │   ├── dns_model.py        # DNS / domain threat scoring
│   │   ├── training.py         # shared training lib (CLI + /retrain)
│   │   └── feature_extractor.py
│   ├── train.py             # CLI: retrain all models (requires datasets)
│   └── model/               # trained .pkl artifacts + manifest.json
├── dashboard/               # React frontend
│   └── src/
│       ├── pages/               # ThreatAlerts, Incidents, Entities, SOAR,
│       │                       #   LogHistory, AIAnalytics, Login
│       ├── pages/admin/         # engine settings, audit logs
│       ├── features/            # dashboard, auth, account, admin
│       ├── api/                 # axios clients
│       ├── store/               # Redux (auth/me/refresh)
│       └── styles/              # Tailwind + custom token theme
├── docker/                  # Kafka, Zookeeper, PostgreSQL compose
├── datasets/                # Local training data (not committed)
├── diagrams/                # Architecture diagrams
├── docs/                    # Requirements, DB design, traceability, ML pipeline
├── k8s/                     # Kubernetes manifests (v3)
└── README.md
```

## Datasets

Public datasets used **only for local model training**:

- CICIDS2017 (network flows)
- UNSW-NB15 (network intrusion)

Stored locally under `/datasets`, excluded from version control.

## Running the Project (Local)

### 1. Run the whole app with Docker (lightweight, ~1 GB budget)

```bash
cd docker
docker compose up -d
```

Now the compose file runs the **complete application stack** (`docker compose up -d`):

- **dashboard** on `http://localhost:3000` — frontend (nginx), same-origin `/api` proxy
- **backend** on `http://localhost:8000` — API, migrations auto-run
- **ml-service** on `http://localhost:8001` — ML detection
- **postgres** on `localhost:5431` (`threatuser` / `threatpass` / `threatdb`)

Per-container memory limits sum to **~928 MiB**, sized for an 8 GB laptop
(host WSL2 VM capped via `%UserProfile%\.wslconfig`; on 8 GB use
`memory=2GB`, `processors=2`, `swap=2GB`).

Kafka/Zookeeper are **opt-in** (they need ~2 GiB on their own and are
excluded by default to keep the 1 GB budget):

```bash
docker compose --profile stream up -d
```

Backend is configured for the stack by default (`DATABASE_URL=...@postgres:5432/...`,
`ENABLE_KAFKA=false`, `ML_SERVICE_URL=http://ml-service:8001`). To instead run the
backend natively against the compose Postgres, export:
`DATABASE_URL=postgresql://threatuser:threatpass@localhost:5431/threatdb`, `ENABLE_KAFKA=true`.

### 2. Start the ML service

```bash
cd ml-service
pip install -r requirements.txt
python train.py        # optional: retrain models from datasets
python -m uvicorn app.main:app --reload --port 8001
```

The ml-service also exposes `POST /retrain` (retrains and hot-swaps models in
memory) and `GET /models` (returns the versioned `manifest.json`). In K8s,
`k8s/training.yaml` triggers retraining daily at 03:00 UTC.

### 3. Start the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # (Windows) / source .venv/bin/activate (Linux/mac)
pip install -r requirements.txt
pip install bcrypt==4.0.1     # pinned for passlib compatibility
uvicorn app.main:app --reload --port 8000
```

### 4. Start the dashboard

```bash
cd dashboard
npm install
npm start
```

Open http://localhost:3000, register an analyst/admin account, and sign in.

## Tests

```bash
# Backend (uses an in-memory SQLite test database)
cd backend
.venv\Scripts\python.exe -m pytest tests -q
```

## API Highlights

- `POST /api/v1/register`, `POST /api/v1/login`, `GET /api/v1/me`, `POST /api/v1/refresh`, `POST /api/v1/logout`
- `POST /api/v1/analyze`, `GET /api/v1/alerts`, `GET /api/v1/alerts/export`, `DELETE /api/v1/alerts/clear`
- `POST /api/v1/upload-logs`, `POST /api/v1/save-scanned-alerts`, `GET /api/v1/logs/history`
- `GET/PUT /api/v1/engine/settings`
- `GET /api/v1/analytics/overview`, `/api/v1/analytics/top-threats`, `/api/v1/analytics/trends`
- `GET /api/v1/audit-logs` (admin)
- `GET/POST/PUT/DELETE /api/v1/rules` (admin writes)
- `GET/POST /api/v1/reputation`, `GET/PATCH /api/v1/reputation/{ip}`
- `GET/POST /api/v1/cases`, `GET/PATCH /api/v1/cases/{id}` (incident management)
- `GET /api/v1/entities`, `GET /api/v1/entities/{id}/graph` (entity/attack-graph)
- `GET /api/v1/soar/actions`, `POST /api/v1/soar/evaluate`, `POST /api/v1/soar/trigger/{alert_id}` (SOAR)

ML service: `POST /predict/network`, `/predict/log`, `/predict/email`, `/predict/dns` (+ `/detail` and `/batch` variants), `GET /models`, `GET /health`.

---

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/functional-requirements.md`](docs/functional-requirements.md) | Functional requirements (FR-xx) by module, MoSCoW priorities |
| [`docs/non-functional-requirements.md`](docs/non-functional-requirements.md) | Non-functional requirements (NFR-xx) with measurable targets |
| [`docs/database-design.md`](docs/database-design.md) | ERD, table catalog, normalization (1NF/2NF/3NF/BCNF) analysis, indexes |
| [`docs/traceability-matrix.md`](docs/traceability-matrix.md) | FR/NFR → implementation → tests traceability |
| [`docs/ml-pipeline.md`](docs/ml-pipeline.md) | ML training → serving pipeline, model versioning, feature contract |
| [`k8s/README.md`](k8s/README.md) | Kubernetes manifests (backend, ml-service, dashboard, HPA, ingress) |
| [`diagrams/README.md`](diagrams/README.md) | UML + architecture diagrams (sequence, class, state, activity, timing, component, …) |
