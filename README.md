# NOCTRA — Autonomous Cybersecurity Threat Detector

[![CI](https://github.com/K-Anjan25/AI-Enhanced-Cybersecurity-Threat-Detector/actions/workflows/ci.yml/badge.svg)](https://github.com/K-Anjan25/AI-Enhanced-Cybersecurity-Threat-Detector/actions/workflows/ci.yml)

> **NOCTRA** — *Your autonomous security analyst.* (See less. Know more.)
> You employ an analyst; you don't operate a dashboard.
>
> **Brand System & Specification**:
> - Current redesign spec (IA, Night Shift tokens, product model): [`docs/noctra-redesign-spec.md`](docs/noctra-redesign-spec.md)
> - Commercial-grade frontend redesign (WordPress/WooCommerce research, token + hook + component system, landing, mini-cart drawer): [`docs/frontend-commercial-redesign.md`](docs/frontend-commercial-redesign.md)
> - Historical: [`docs/brand-identity-axiom.md`](docs/brand-identity-axiom.md) (superseded)

An end-to-end cybersecurity threat detection platform that analyzes network flows, security logs, credential abuse, and DNS anomalies with self-evident AI reasoning, blast-radius asset mapping, and reversible remediation actions that NOCTRA records — never executes — pending your one-click approval.

The project supports both **local (REST)** and **streaming (Kafka)** execution modes.

---

## Architecture

```
 ┌────────────┐   REST / Kafka   ┌─────────────┐   HTTP   ┌─────────────┐
 │ Dashboard  │ ───────────────▶ │   Backend   │ ───────▶ │  ML Service │
 │(React+Vite)│ ◀─────────────── │  (FastAPI)  │ ◀─────── │  (FastAPI)  │
 └────────────┘                  └─────────────┘          └─────────────┘
                                       │                      │
                                       ▼                      ▼
                                  PostgreSQL (alerts,      scikit-learn models
                                  users, audit, rules)     (IsolationForest,
                                                           TF-IDF + logistic)
```

- Security telemetry and events are ingested via REST or Kafka connectors (Okta, CrowdStrike, GuardDuty, Cloudflare WAF).
- The backend leverages ML models and Anthropic LLM reasoning to evaluate incidents and map connected blast radius assets.
- The NOCTRA React dashboard visualizes SOC incident briefs, blast-radius graph nodes, the interactive analyst chat, SOAR playbooks, and decision audit logs.

## Tech Stack

- **Backend**: Python / FastAPI, SQLAlchemy, PostgreSQL (SQLite for tests), JWT auth (JTI + refresh tokens), optional Kafka streaming
- **ML Service**: Python / FastAPI, scikit-learn (IsolationForest), TF-IDF + LogisticRegression, pandas, joblib
- **Frontend**: React, TypeScript, Tailwind CSS, Sora / Inter / JetBrains Mono typography, Redux Toolkit, Recharts, Framer Motion
- **Infrastructure**: Docker, Docker Compose (Kafka, Zookeeper, PostgreSQL), Kubernetes manifests

## Project Structure

```
AI-Enhanced-Cybersecurity-Threat-Detector/
├── backend/                # FastAPI backend service & ABAC policy engine
│   ├── app/
│   │   ├── api/v1/endpoints/  # auth, users, alerts, ingest, admin, engine,
│   │   │                       # audit, analytics, rules, analyst, connectors
│   │   ├── core/               # config, database, security, abac
│   │   ├── models/             # ORM models (User, SecurityAlert, DetectionRule,
│   │   │                       # IpReputation, EngineSetting, AuditLog, Case)
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # alert, item, user, ml_client, analyst, soar
│   │   └── main.py
│   ├── tests/               # Pytest suite (113 passing tests)
│   ├── requirements.txt
│   └── pyproject.toml
├── ml-service/             # FastAPI ML microservice (13 passing tests)
│   ├── app/
│   │   ├── main.py             # /predict/* endpoints
│   │   ├── network_model.py    # IsolationForest flow anomaly detection
│   │   ├── log_model.py        # log attack classification
│   │   ├── email_model.py      # phishing detection
│   │   └── dns_model.py        # DNS threat scoring
│   ├── train.py             # CLI: retrain models
│   └── model/               # trained .pkl artifacts
├── dashboard/               # Single production React + Vite frontend
│   ├── src/
│   │   ├── pages/               # BriefPage, CasePage, FeedPage, Incidents,
│   │   │                       #   EntitiesPage, SoarPage, AIAnalytics
│   │   ├── components/          # BrandLogo, UI components, Bento Layout
│   │   ├── api/                 # Axios API clients
│   │   ├── store/               # Redux Toolkit
│   │   └── constants/           # Brand tokens (NOCTRA)
├── docs/                    # Brand specifications, requirements, architecture
└── README.md
```

## Running the Application

### 1. Docker Compose (Complete Stack)

```bash
cd docker
docker compose up -d
```

- **NOCTRA Dashboard**: `http://localhost:3000`
- **FastAPI Backend**: `http://localhost:8000`
- **ML Microservice**: `http://localhost:8001`
- **PostgreSQL**: `localhost:5431`

### 2. Manual Development Setup

#### ML Service
```bash
cd ml-service
python -m uvicorn app.main:app --port 8001
```

#### Backend API
```bash
cd backend
python -m uvicorn app.main:app --port 8000
```

#### NOCTRA Dashboard
```bash
cd dashboard
npm run dev
```

---

## Test Suites

```bash
# Run backend test suite
cd backend
pytest tests

# Run ML service test suite
cd ml-service
pytest tests

# Build dashboard frontend
cd dashboard
npm run build
```

---

## Brand Specification & Artifacts

- **Brand Name**: `NOCTRA`
- **Tagline**: *"Your autonomous security analyst."* (secondary: *"See less. Know more."*)
- **What it is**: NOCTRA watches your telemetry, explains incidents in plain English, maps the blast radius, and drafts reversible actions — you approve, it records and reports.
- **Typography**: Sora / Inter / JetBrains Mono
- **Redesign Spec (current)**: [`docs/noctra-redesign-spec.md`](docs/noctra-redesign-spec.md)
- **Historical (superseded)**: [`docs/brand-identity-axiom.md`](docs/brand-identity-axiom.md) · [`docs/brand-identity-axiom.png`](docs/brand-identity-axiom.png)
