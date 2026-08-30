# NOCTRA — an autonomous AI security analyst for small companies

[![CI](https://github.com/K-Anjan25/AI-Enhanced-Cybersecurity-Threat-Detector/actions/workflows/ci.yml/badge.svg)](https://github.com/K-Anjan25/AI-Enhanced-Cybersecurity-Threat-Detector/actions/workflows/ci.yml)

> **NOCTRA** — *Threat intelligence, always on.*
> You employ an analyst; you don't operate a dashboard.

Most small companies cannot staff a SOC. A single analyst costs $77–101K a year
and covers business hours only; round-the-clock in-house coverage means four to
five people. The usual alternatives — an MSSP or an MDR — run $3–15K a month and
still hand back shallow investigations, because rotating analysts never learn
your environment.

NOCTRA is the analyst. It triages every alert, explains its reasoning in plain
English, says what the incident means *for your organisation specifically*, and
proposes a reversible action — which it records and never executes until you
approve it.

**What makes the reasoning trustworthy:**

- **Every number traces to a real row.** Where a signal cannot be measured, the
  product says "not measured" rather than showing a flattering constant.
- **Organisational context on every case.** How many hops the attacker is from
  your crown jewels, what it does to your posture score, and whether the
  credential involved is already leaked publicly.
- **Nothing runs without you.** Actions are recorded with an explicit undo path
  and wait for one-click approval.

> **Brand System & Specification**:
> - Design system (SIGNAL — ink canvas + signal green, DM Sans + Space Mono): [`docs/noctra-redesign-spec.md`](docs/noctra-redesign-spec.md) §40 · design source [`newfile.html`](newfile.html)
> - Current redesign spec (IA, product model, stages): [`docs/noctra-redesign-spec.md`](docs/noctra-redesign-spec.md)
> - Code-accurate wireframe kit (20 boards, mapped 1:1 to routes): [`docs/wireframes/`](docs/wireframes/)
> - Demo script + verification matrix: [`docs/demo.md`](docs/demo.md)
> - Commercial-grade frontend redesign: [`docs/frontend-commercial-redesign.md`](docs/frontend-commercial-redesign.md)
> - Historical roadmap (contains withdrawn speculative phases): [`docs/ROADMAP_150_FINAL.md`](docs/ROADMAP_150_FINAL.md)

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

## Capabilities

The analyst loop is the product; everything below feeds it.

**Core loop** — ingest telemetry (Okta, CrowdStrike, GuardDuty, Cloudflare WAF)
→ detect with ML and LLM reasoning → open a case with blast radius → propose a
reversible action → human approves → audited record.

**Risk context wired into every case:**

| Capability | Route | What it contributes |
|---|---|---|
| Posture score | `/posture-score` | One 0–100 NIST-CSF score from real vuln, CSPM, case-closure, retention and compliance rows. Unmeasurable dimensions are excluded and reported, not guessed. |
| Attack paths | `/attack-path` | Dijkstra search over real exposures, assets and observed entity links to your crown jewels, plus the single choke point that breaks each path. |
| Digital risk protection | `/drp` | Offline typosquat generation against your real domains. External dark-web and breach lookups run only when a provider key is configured, and report the gap when not. |
| Autonomy control | `/noctra-os` | Metrics counted from real cases, including the recommendation-accept rate that justifies raising the autonomy level. |

These four surface directly on the case and brief screens through the shared
`CaseImpact` component — when a module has no real data, it renders nothing.

**Supporting surfaces:** vulnerabilities, cloud posture (CSPM), SBOM/supply
chain, zero-trust access, compliance packs, hunting, deception, forensics,
threat-intel platform, SOAR playbooks, reporting and admin/RBAC.

**Labs** (exploratory, clearly labelled in the UI): SOC TV wall and the
remaining research surfaces.

### Scope note

Earlier revisions advertised 150 "phases". Two groups have been withdrawn:

- **50 speculative modules** (multiverse SOC, AGI council, akashic ledger and
  similar) — 6,493 lines that modelled nothing real.
- **6 mock-data modules** (federated intel, quantum-safe, data fabric, CNAPP,
  continuous red teaming, SOC manager). These were more dangerous than the
  first group because they looked plausible: CNAPP invented Kubernetes
  clusters with a fabricated CVE, quantum-safe returned three hardcoded
  algorithms, and SOC manager marked every orchestration step complete in a
  loop. A buyer could not tell these from real findings.

All 56 were referenced by no other code. What remains is the product that can
actually be demonstrated.

## Project Structure

```
AI-Enhanced-Cybersecurity-Threat-Detector/
├── backend/                # FastAPI backend service & ABAC policy engine
│   ├── app/
│   │   ├── api/v1/endpoints/  # REST endpoints
│   │   ├── core/               # config, database, security, abac
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # Domain services
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
│   │   ├── features/advanced/pages/ # Security Operations + Labs surfaces
│   │   ├── components/          # BrandLogo, UI components
│   │   ├── api/                 # Axios API clients
│   │   ├── store/               # Redux Toolkit
│   │   └── constants/           # Brand tokens (NOCTRA)
├── docs/
│   ├── ROADMAP_150_FINAL.md # Historical roadmap (speculative phases withdrawn)
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
