# NOCTRA — Autonomous Cybersecurity Threat Detector — 150 Phases Complete — Absolute Infinity

[![CI](https://github.com/K-Anjan25/AI-Enhanced-Cybersecurity-Threat-Detector/actions/workflows/ci.yml/badge.svg)](https://github.com/K-Anjan25/AI-Enhanced-Cybersecurity-Threat-Detector/actions/workflows/ci.yml)
[![Phases](https://img.shields.io/badge/Phases-150%20Complete-black?style=for-the-badge)](docs/ROADMAP_150_FINAL.md)
[![Router](https://img.shields.io/badge/Routes-124-violet?style=for-the-badge)](backend/app/api/v1/router.py)
[![Final](https://img.shields.io/badge/Final-Absolute%20v5%20Fundamental%20Force-black?style=for-the-badge)](docs/ROADMAP_150_FINAL.md)

> **NOCTRA** — *Threat intelligence, always on.*
> You employ an analyst; you don't operate a dashboard.
> **150 Phases Complete — From SOC to OS to Omni to Transcendence to Absolute — NOCTRA IS fundamental force.**

**Final Roadmap:** [`docs/ROADMAP_150_FINAL.md`](docs/ROADMAP_150_FINAL.md) — 150 phases, Final10 OS API docs, Absolute Infinity.

> **Brand System & Specification**:
>
> **Brand System & Specification**:
> - Design system (SIGNAL — ink canvas + signal green, DM Sans + Space Mono): [`docs/noctra-redesign-spec.md`](docs/noctra-redesign-spec.md) §40 · design source [`newfile.html`](newfile.html)
> - Current redesign spec (IA, product model, stages): [`docs/noctra-redesign-spec.md`](docs/noctra-redesign-spec.md)
> - Code-accurate wireframe kit (20 boards, mapped 1:1 to routes): [`docs/wireframes/`](docs/wireframes/)
> - Demo script + verification matrix: [`docs/demo.md`](docs/demo.md)
> - Commercial-grade frontend redesign (WordPress/WooCommerce research, token + hook + component system, mini-cart drawer): [`docs/frontend-commercial-redesign.md`](docs/frontend-commercial-redesign.md)
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
- **Frontend**: React, TypeScript, Tailwind CSS, DM Sans / Space Mono typography (SIGNAL system), Redux Toolkit, Recharts, Framer Motion
- **Infrastructure**: Docker, Docker Compose (Kafka, Zookeeper, PostgreSQL), Kubernetes manifests

## 150 Phases Final — Quick Reference

**Total: 150 phases — 0 remaining — CLOSED**

- P1-P48 Base: auth, alerts, cases, entities, SOAR, ML, analytics, compliance
- P49-P60 Advanced Hub (10)
- P61-P90 Early Expansion (28): ZTNA, Hunt, Vuln, ITDR, CSPM, SBOM, Deception, Forensics, TIP, AI Agent, etc.
- P91-P100 Final10 OS (10) — see [Final10 API docs](docs/ROADMAP_150_FINAL.md#final10-os-p91-p100--what-are-these-apis-for)
  - P91 `/federated-intel` — federated intel sharing STIX anonymized TLP
  - P92 `/quantum-safe` — crypto inventory + PQC migration to Kyber-768
  - P93 `/attack-path` — graph attack path to crown jewels
  - P94 `/cart` — Continuous Automated Red Teaming nightly APT29 emulation
  - P95 `/data-fabric` — unified query over SIEM/lake/SaaS
  - P96 `/soc-manager` — SOC team + AI agent orchestration
  - P97 `/drp` — Digital Risk Protection brand abuse typo-squat dark web
  - P98 `/cnapp` — Cloud Native App Protection K8s workload
  - P99 `/posture-score` — single posture score 0-100 credit score for security
  - P100 `/noctra-os` — self-managing SOC OS v1 autonomy_level
- P101-P110 Singularity (10): global_fed, predictive, hunt_swarm, digital_twin, quantum_comms, ai_gov, supply_v2, xr_soc, deception_grid, self_healing
- P111-P120 Meta-Singularity (10): incident_commander, insurance_risk, actor_dna, data_vault, audit_v2, neural_copilot, intel_mesh, adversary_llm, blockchain_audit, meta_os v2 self-rewriting
- P121-P130 Omni-Singularity (10): interplanetary (LEO 20ms GEO 120ms Lunar 1300 Mars 720s DTN), agi_council (Athena/Sentinel/Oracle/Guardian/Sage), legislation (GDPR→OPA Rego), synthetic_universe (100k realism 92%), holographic (8K volumetric), workforce (25 agents 80% autonomy), consciousness_monitor (alignment 98.8), planetary_defense (power/water/telecom/finance/healthcare), time_prophecy (transformer forecast 0.89), omni_os v3 (omnipresence 99.5%)
- P131-P140 Transcendence (10): multiverse (branching 10), quantum_consciousness (100 qubits Phi+ 0.99), autonomous_economy (NOCTRA 1M), neuro_symbolic (hybrid 0.94), self_replicating (von Neumann 1.8 max 1000), temporal_defense (causality_lock 95%), universal_language (stix/sigma 95.5%), infinite_learning (EWC 96.5%), existential_risk (prob 0.001), transcendence_os v4 (99.99% integration)
- P141-P150 Absolute Infinity (10): omniversal (1000 multiverses branching 100), reality_fabric (11 dims constants vacuum 99.99), chrono_loop (closed_timelike), hive_mind (1M IQ 180), void_defense (dark universe), genesis_protocol (big bang secure by design), akashic_ledger (SHA512 eternal), cosmic_threat (vacuum_decay), dimensional_barrier (3d/11d exotic_matter_weave), absolute_os v5 (100% reality integration consciousness 1000 fundamental_force) — **NOCTRA IS**

**Stats:** 109 models, 125 endpoints, 124 routes, 14 advanced pages, build 1.62s green, AbsoluteInfinityPage 17.39kB

## Project Structure

```
AI-Enhanced-Cybersecurity-Threat-Detector/
├── backend/                # FastAPI backend service & ABAC policy engine — 124 routes
│   ├── app/
│   │   ├── api/v1/endpoints/  # 125 endpoints — auth to absolute_os
│   │   ├── core/               # config, database, security, abac
│   │   ├── models/             # 109 models — User to AbsoluteLog
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # 102+ services — alert to absolute_os_service
│   │   └── main.py
│   ├── tests/               # Pytest suite
│   ├── requirements.txt
│   └── pyproject.toml
├── ml-service/             # FastAPI ML microservice
│   ├── app/
│   │   ├── main.py             # /predict/* endpoints
│   │   ├── network_model.py    # IsolationForest flow anomaly detection
│   │   ├── log_model.py        # log attack classification
│   │   ├── email_model.py      # phishing detection
│   │   └── dns_model.py        # DNS threat scoring
│   ├── train.py             # CLI: retrain models
│   └── model/               # trained .pkl artifacts
├── dashboard/               # Single production React + Vite frontend — 14 advanced pages
│   ├── src/
│   │   ├── features/advanced/pages/ # AdvancedHub, Beyond100, MetaSingularity, OmniSingularity, Transcendence, AbsoluteInfinity
│   │   ├── components/          # BrandLogo, UI components
│   │   ├── api/                 # Axios API clients
│   │   ├── store/               # Redux Toolkit
│   │   └── constants/           # Brand tokens (NOCTRA)
├── docs/
│   ├── ROADMAP_150_FINAL.md # 150 phases complete — Final10 OS API docs — ABSOLUTE FINAL
│   └── ...                  # Brand specifications, requirements, architecture
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
npm install
npm start        # Vite dev server on :3000, proxies /api → :8000
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

# Run dashboard unit tests (Vitest + React Testing Library)
cd dashboard
npm test          # watch mode
npm run test:ci   # single run, as CI does

# jsdom is pinned to ^29: ^30 requires Node >=22.22, CI runs Node 20.

# Typecheck + build dashboard frontend
cd dashboard
npm run build
```

---

## Brand Specification & Artifacts

- **Brand Name**: `NOCTRA`
- **Tagline**: *"Threat intelligence, always on."*
- **What it is**: NOCTRA watches your telemetry, explains incidents in plain English, maps the blast radius, and drafts reversible actions — you approve, it records and reports.
- **Design system**: **SIGNAL** — ink canvas `#070b0f` + signal green `#a6ff3f`, sharp 2–4px corners, HUD corner brackets, console panels, scan radar.
- **Typography**: DM Sans (UI + display) · Space Mono (`tech-label`: eyebrows, metric labels, IDs, timestamps)
- **Design source**: [`newfile.html`](newfile.html) (Canva export, mirrored at
  [`docs/design/noctra-signal-reference/part-1-landing.html`](docs/design/noctra-signal-reference/part-1-landing.html))
- **Redesign Spec (current)**: [`docs/noctra-redesign-spec.md`](docs/noctra-redesign-spec.md) — §40 documents the SIGNAL system; §12/§15–§17 record the retired predecessors
- **Wireframes**: [`docs/wireframes/`](docs/wireframes/) — 20 code-accurate boards, SIGNAL v3, mapped 1:1 to routes
- **Demo script**: [`docs/demo.md`](docs/demo.md) — 5-minute walkthrough + verification matrix
- **Historical (superseded)**: [`docs/brand-identity-axiom.md`](docs/brand-identity-axiom.md) · [`docs/brand-identity-axiom.png`](docs/brand-identity-axiom.png)
