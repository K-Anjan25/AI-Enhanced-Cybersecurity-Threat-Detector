# AEGIS — AI-Enhanced Cybersecurity Threat Detector

Transformer models over **network flow records** and **system logs** to detect anomalies and
predict cybersecurity threats before they become confirmed incidents.

> **Status: sprint S2 / milestone M3 (backend and API).** E0 and E1 are done, E2 is done
> except the release gate Q-07 still owes, and E3 has reached the notification path — alerts
> are produced, deduplicated and grouped, carry an immutable analyst verdict, are pushed over
> a WebSocket with an SSE and REST fallback that resumes from a cursor, and can be delivered
> to registered webhooks as HMAC-signed events with bounded retries; querying alerts still
> needs a database connection (T-319). The dashboard is still the shell from T-004. See
> [memory.md](memory.md) for the authoritative current state, and [task.md](task.md) for
> per-task status.

## Read these first

The project is documented before it is coded. Start with the PRD, then the architecture.

| Document                           | What it answers                                                 |
| ---------------------------------- | --------------------------------------------------------------- |
| [prd.md](prd.md)                   | What we are building, for whom, and what "done" means           |
| [architecture.md](architecture.md) | How the system and the models are designed                      |
| [rules.md](rules.md)               | How we write code — 89 binding rules with an enforcement column |
| [design.md](design.md)             | How it looks and behaves, down to measured contrast ratios      |
| [task.md](task.md)                 | What we build, in what order, with acceptance criteria          |
| [memory.md](memory.md)             | Decisions, data sources, glossary, and the measurement ledger   |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to set up, run, test, and extend the system                 |

## Repository layout

```
prd.md architecture.md rules.md design.md task.md memory.md
backend/      FastAPI ingest, query, auth, messaging, correlation, verdicts, stream, webhooks
              (T-301…T-311)
ml-service/   Data pipeline, FlowNet/LogNet, scoring and the training harness
dashboard/    React + TypeScript dashboard — the shell only; E4 has not started
data/         datasets, gitignored                              (R-40 — never committed)
docker/       compose stack, written but never run here         (no Docker in this sandbox)
k8s/          manifests, statically checked but never applied
scripts/      fetch, generate, train, evaluate, and the check suite
```

## Running what exists

Requires Python 3.11+ (3.11.2 verified) and Node 22. From the repository root:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e "backend[dev]" -e "ml-service[dev]" -r requirements-dev.txt
(cd dashboard && npm ci)

# backend
cd backend
cp .env.example .env                       # then set AEGIS_SECRET_KEY
python -m pytest -q                        # 524 tests, 10 skipped (need a live PostgreSQL)
uvicorn app.main:app --host 0.0.0.0 --port 8000
#   GET /healthz                     liveness
#   GET /readyz                      readiness (503 when a dependency probe is not ok)
#   WS  /api/v1/alerts/ws            live alerts; ?after=<sequence> resumes, ?token via subprotocol
#   GET /api/v1/alerts/stream        SSE fallback (Last-Event-ID resumes)
#   GET /api/v1/alerts/notifications REST fallback; ?after=<sequence> for the cursor
#   POST /api/v1/webhooks            register an outbound webhook; the secret is returned once
#   GET  /api/v1/webhooks            list targets (never their secrets)
#   DELETE /api/v1/webhooks/{id}     remove a target

# ml-service
cd ../ml-service
python -m pytest -q                        # 531 tests, 16 skipped (need torch, an extra)
uvicorn aegis_ml.serving.app:app --host 0.0.0.0 --port 8001
#   GET /internal/healthz  reports "no_model_loaded" until a model is promoted
```

`AEGIS_SECRET_KEY` is required and refuses placeholder values; generate one with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`. `torch` is the
`ml-service[training]` extra and the ONNX stack is `[onnx]`; neither is needed to run the
service or the test suite, and both are absent from the sandbox by choice.

## Checks

One command runs everything CI runs:

```bash
./scripts/check_all.sh              # 25 checks across 6 suites
./scripts/check_all.sh backend      # or one: docs|infra|backend|ml|dashboard|hooks
```

| Suite          | Checks                                                                                                                                         |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **docs**       | `ruff`, `black`, `mypy` on `scripts/`, and `scripts/check_docs.py` — cross-document links, anchors, requirement/task/rule ids, table integrity |
| **infra**      | `check_compose.py`, `check_k8s.py`, the dataset manifest, and the frontend import boundaries                                                   |
| **backend**    | `ruff`, `black`, `mypy --strict`, `bandit`, `lint-imports` (R-15), `pytest` with the 80% coverage gate                                         |
| **ml-service** | `ruff`, `black`, `mypy --strict`, `pytest`                                                                                                     |
| **dashboard**  | `tsc --noEmit`, `eslint` (incl. a11y), `stylelint`, `prettier`, `vitest` (incl. the WCAG contrast suite), `vite build`                         |
| **hooks**      | the same 14 pre-commit hooks CI runs, because a local hook is bypassable with `--no-verify`                                                    |

The planning documents are the specification, so broken anchors and dangling requirement ids
fail the build rather than rotting silently. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to
extend each part of the system.

## What is verified, and what is not

Verified here, on every run: the test suites and checks above, on 2 vCPU with Python 3.11.2
and Node 22. The checks that exist to catch a class of defect were proven to fail on an
injected violation before being trusted, and several real defects were found that way —
the ledger in [memory.md](memory.md#change-log) records each one.

**Not verified, and each says so where it lives:** the compose stack and its images (no Docker
daemon in this sandbox — T-005), the Alembic migration against a live PostgreSQL (D-030), the
Kubernetes manifests (never applied — T-504), the Kafka broker calls (no broker — D-035), and
the machine NFR-01 specifies for latency (2 vCPU here, not 4 — D-023). The SQLAlchemy adapters
behind the correlator's `CaseStore` and the verdict ledger are not written yet (D-037, D-038):
each needs a table the migration does not have — an evidence index, and a home for verdict
history — and the schema defects the alert row needs — `Float` scores and an unconstrained
severity string — are tracked as T-321. The alert stream is verified at the ASGI level over all
three transports, but its hub is in-process (a multi-replica deployment needs a shared bus, D-039)
and uvicorn needs the `ws` extra to serve the socket, which is not installed here — so uvicorn's
own WebSocket transport is not exercised. Webhooks are verified without a network too: the
allowlist, the address verdicts, the signature scheme and the retry policy are exercised against
an injected transport, but **no HTTP client ships** — connecting to the pinned address, refusing
redirects and enforcing the timeout are a `Protocol`'s contract, not behaviour measured here
(D-040) — retries run inline in the caller rather than on a delivery queue, and the target store
is in-memory.

Datasets (UNSW-NB15, CIC-IDS2017) are large and are **never committed** (R-40). The fetched
copies are hash-verified by `scripts/fetch_datasets.py` and recorded in
[memory.md](memory.md#data-sources).
