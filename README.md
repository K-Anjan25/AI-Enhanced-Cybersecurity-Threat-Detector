# AEGIS — AI-Enhanced Cybersecurity Threat Detector

Transformer models over network flow records and system logs, to detect anomalies and
predict threats before they become confirmed incidents.

Current state: [memory.md](memory.md). Per-task status: [task.md](task.md).

## Run it

**Docker Compose (local)**

```bash
cd docker
export AEGIS_SECRET_KEY=$(openssl rand -hex 32)
export AEGIS_DEV_AUTH_SETUP_ENABLED=true
docker compose up -d --build
```

Dashboard: http://localhost:8080 · Backend API docs: http://localhost:8000/docs

**Kubernetes (local, one command)**

```bash
bash scripts/k8s-local.sh up     # Docker Desktop Kubernetes; use Git Bash on Windows
bash scripts/k8s-local.sh down
```

**Single container (any Docker host, or Render)**

```bash
docker build -f deploy/aegis/Dockerfile -t aegis .
docker run -p 8080:8080 -e AEGIS_SECRET_KEY=... -e AEGIS_DATABASE_URL=... aegis
```

Runs the dashboard, backend and ML service together. For Render, create a Blueprint from
this repository and select `render.yaml`; it deploys one service named `aegis`.

Full deployment steps, configuration and upgrades: [docs/deploy.md](docs/deploy.md).

## Develop

Requires Python 3.11+ and Node 22.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e "backend[dev]" -e "ml-service[dev]" -r requirements-dev.txt
(cd dashboard && npm ci)

cd backend && python -m pytest -q
cd ml-service && python -m pytest -q
```

Run the services directly:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000      # from backend/
uvicorn aegis_ml.serving.app:app --host 0.0.0.0 --port 8001   # from ml-service/
```

`AEGIS_SECRET_KEY` is required and must not be a placeholder. Generate one with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## Checks

```bash
./scripts/check_all.sh              # everything CI runs
./scripts/check_all.sh backend      # one suite: docs, infra, backend, ml, dashboard, hooks
```

## Documents

| Document                             | What it answers                            |
| ------------------------------------ | ------------------------------------------ |
| [prd.md](prd.md)                     | What we are building and what "done" means |
| [architecture.md](architecture.md)   | How the system and models are designed     |
| [rules.md](rules.md)                 | How we write code                          |
| [design.md](design.md)               | How the product looks and behaves          |
| [task.md](task.md)                   | What we build, in what order               |
| [memory.md](memory.md)               | Decisions, data sources and the change log |
| [api-reference.md](api-reference.md) | The generated API reference                |
| [CONTRIBUTING.md](CONTRIBUTING.md)   | How to set up, test and extend the system  |
| [docs/deploy.md](docs/deploy.md)     | Deployment guide                           |

## Limits to know

- The alert, audit and API-key stores are in memory and reset when the process restarts.
- The rate limiter is per process. Multi-replica deployments need a shared store.
- The ML service has no authentication on its scoring and model endpoints. Keep it private
  in any real deployment.
- On Render's free plan, services sleep when idle, so the first request can be slow.
- Datasets (UNSW-NB15, CIC-IDS2017) are large and never committed. They are fetched with
  `scripts/fetch_datasets.py`.

Anything not verified in this environment is recorded in [memory.md](memory.md).
