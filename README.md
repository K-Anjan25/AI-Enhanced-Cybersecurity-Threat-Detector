# AEGIS — AI-Enhanced Cybersecurity Threat Detector

Transformer models over **network flow records** and **system logs** to detect anomalies and
predict cybersecurity threats before they become confirmed incidents.

> **Status: Sprint S0.** The planning documents and the backend / ml-service skeletons exist and
> are tested. No models have been trained and no datasets have been fetched. See
> [memory.md](memory.md) for the authoritative current state.

## Read these first

The project is documented before it is coded. Start with the PRD, then the architecture.

| Document | What it answers |
|---|---|
| [prd.md](prd.md) | What we are building, for whom, and what "done" means |
| [architecture.md](architecture.md) | How the system and the models are designed |
| [rules.md](rules.md) | How we write code — 89 binding rules with an enforcement column |
| [design.md](design.md) | How it looks and behaves, down to measured contrast ratios |
| [task.md](task.md) | What we build, in what order, with acceptance criteria |
| [memory.md](memory.md) | Decisions, data sources, glossary, and the measurement ledger |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to set up, run, test, and extend the system |

## Repository layout

```
prd.md architecture.md rules.md design.md task.md memory.md
backend/      FastAPI ingest + query API        (T-002 — skeleton, tested)
ml-service/   Transformer inference service     (T-003 — skeleton, tested)
dashboard/    React + TypeScript dashboard      (T-004 — not started)
data/         datasets, gitignored              (R-40 — never committed)
```

## Running what exists

Requires Python 3.11+ (3.11.2 verified). From the repository root:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e "backend[dev]" "ml-service[dev]"

# backend
cd backend
cp .env.example .env                       # then set AEGIS_SECRET_KEY
python -m pytest -q                        # 20 tests
uvicorn app.main:app --host 0.0.0.0 --port 8000
#   GET /healthz   liveness
#   GET /readyz    readiness (503 when a dependency probe is not ok)

# ml-service
cd ../ml-service
python -m pytest -q                        # 15 tests
uvicorn aegis_ml.serving.app:app --host 0.0.0.0 --port 8001
#   GET /internal/healthz  reports "no_model_loaded" until a model is promoted
```

`AEGIS_SECRET_KEY` is required and refuses placeholder values; generate one with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## Checks

One command runs everything CI runs:

```bash
./scripts/check_all.sh              # 20 checks across 5 suites
./scripts/check_all.sh backend      # or one: docs|infra|backend|ml|dashboard
```

| Suite | Checks |
|---|---|
| **docs** | `ruff`, `black`, `mypy` on `scripts/`, and `scripts/check_docs.py` — cross-document links, anchors, requirement/task/rule ids, table integrity |
| **infra** | `scripts/check_compose.py` — compose file verified against the real application code |
| **backend** | `ruff`, `black`, `mypy --strict`, `bandit`, `lint-imports` (R-15), `pytest` with the 80% coverage gate |
| **ml-service** | `ruff`, `black`, `mypy --strict`, `pytest` |
| **dashboard** | `tsc --noEmit`, `eslint` (incl. a11y), `vitest` (incl. the WCAG contrast suite), `vite build` |

The planning documents are the specification, so broken anchors and dangling requirement ids
fail the build rather than rotting silently. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to
extend each part of the system.

## What is deliberately not here yet

No `docker-compose.yml` (T-005), no CI workflow (T-006), no dashboard (T-004), and no model code
(T-201 onward). Docker is unavailable in the current development sandbox, so the compose file will
be written but cannot be executed here — see the sandbox note in
[memory.md](memory.md#environment-and-setup).

Datasets (UNSW-NB15, CIC-IDS2017) are large and are **never committed** (R-40). They must be
fetched from a machine with general internet access and their checksums recorded in
[memory.md](memory.md#data-sources).
