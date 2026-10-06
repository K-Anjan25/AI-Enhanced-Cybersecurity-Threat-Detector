# AEGIS — AI-Enhanced Cybersecurity Threat Detector

Transformer models over **network flow records** and **system logs** to detect anomalies and
predict cybersecurity threats before they become confirmed incidents.

> **Status: sprint S2 / milestone M3 (backend and API).** E0 and E1 are done, E2 is done
> except the release gate Q-07 still owes, and E3 has reached the notification path — alerts
> are produced, deduplicated and grouped, carry an immutable analyst verdict, are pushed over
> a WebSocket with an SSE and REST fallback that resumes from a cursor, and can be delivered
> to registered webhooks as HMAC-signed events with bounded retries, with every mutating
> action recorded in an append-only audit trail and scoped API keys for machine-to-machine
> ingestion whose secret is stored only as a keyed digest; querying alerts still needs a
> database connection (T-319). The dashboard has the shell, the closed token layer,
> the UI primitives, a working overview that reads the alert API and the metrics scrape, and the
> triage screen with its keyboard loop, the live alert stream with its reconnect banner and REST
> fallback, and the traffic explorer with its brushable series and entity graph (T-401…T-406). See
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
prd.md architecture.md rules.md design.md task.md memory.md api-reference.md
backend/      FastAPI ingest, query, auth, messaging, correlation, verdicts, stream,
              webhooks, the audit trail, API keys, the golden
              pipeline, the API reference and threshold
              recalibration and the declared database
              driver                                   (T-301…T-323)
ml-service/   Data pipeline, FlowNet/LogNet, scoring and the training harness
dashboard/    React + TypeScript dashboard — the shell, routing, theming,
              design tokens, UI primitives, overview, triage,
              live stream, traffic explorer            (T-401…T-406)
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
python -m pytest -q                        # 1227 tests, 13 skipped (need a live PostgreSQL)
uvicorn app.main:app --host 0.0.0.0 --port 8000
#   GET /healthz                     liveness
#   GET /readyz                      readiness (503 when a dependency probe is not ok)
#   WS  /api/v1/alerts/ws            live alerts; ?after=<sequence> resumes, ?token via subprotocol
#   GET /api/v1/alerts/stream        SSE fallback (Last-Event-ID resumes)
#   GET /api/v1/alerts/notifications REST fallback; ?after=<sequence> for the cursor
#   POST /api/v1/webhooks            register an outbound webhook; the secret is returned once
#   GET  /api/v1/webhooks            list targets (never their secrets)
#   DELETE /api/v1/webhooks/{id}     remove a target
#   GET  /api/v1/audit               the append-only trail; ?start=&end= required
#   POST /api/v1/keys                issue a scoped API key; the secret is returned once (admin)
#   GET  /api/v1/keys                list keys, never their secrets (admin)
#   GET  /api/v1/keys/scopes         the scopes a key may hold, and what each grants (admin)
#   DELETE /api/v1/keys/{id}         revoke a key; the next request presenting it is refused
#   GET  /api/v1/models                 the version table: id, kind, status, who promoted it
#   GET  /api/v1/models/{id}/metrics     FR-31 metrics, each with the run it came from
#   POST /api/v1/models/{id}/promote     make a version active, retiring the incumbent (admin)
#   POST /api/v1/models/{kind}/rollback  reverse the last promotion of a kind (admin)
#   GET  /api/v1/retention           the retention policy and what a run would drop (admin)
#   POST /api/v1/retention/run       drop the months the plan names; the run is audited (admin)
#   POST /api/v1/privacy/erasure     erase one data subject across every store (admin)
#   GET  /api/v1/privacy/erasures    the erasure ledger: tombstones, counts, who asked (admin)

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
./scripts/check_all.sh              # 26 checks across 6 suites
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

The docs suite also re-renders the committed `api-reference.md` from the application's own
schemas with `scripts/generate_api_reference.py --check`, so the published reference cannot
drift from the code (T-320, D-054).

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
is in-memory. The audit trail is verified the same way: append-only, complete over every mutating
route on the built application, and bounded on read. API keys are verified more sharply than
webhooks: key material is stored as **HMAC-SHA256 over the whole presented key** under a key
derived from `AEGIS_SECRET_KEY` (D-042), because a 256-bit random secret has nothing to guess and
Argon2id's cost per verification would be a self-inflicted denial of service on the ingest path;
the secret appears in exactly one response and in no store, no listing, no error and no audit row.
Scopes are a default-deny table (D-043), and a key's authority is asserted to be a subset of what
the **least-privileged** role the matrix allows on each of its routes holds, so a machine credential
cannot outrank a human one. Limits are verified against the built application rather than by
inspection: every write and every unauthenticated route is asserted in scope, an authenticated read
is asserted out of scope, and the identity a request is bucketed by is asserted to come from the
credential or the peer address -- never from `X-Forwarded-For` (D-048). A declared oversize body is
refused without being read, a streamed or mis-declared one is counted as it arrives, and a batch
that does not fit the ingest buffer is refused **whole** with `Retry-After` (D-049). Observability is verified from the ids outwards: the four metric names are the ones architecture.md §13 specifies, their labels are a closed vocabulary asserted against the registry (a request that matched no route is one `unmatched` series, so a client cannot grow the process by choosing paths), and the scrape is asserted to carry no identifiers and no alert content (R-58, D-050). A trace id from the ingest response travels through the scoring worker and the correlator into the alert row and the stream notification, the response carries `traceparent` and `x-trace-id`, and a request produces exactly one server span because FastAPI's native telemetry is off (D-051). Nothing is exported here: with no collector configured the ids are generated and propagated but no span leaves the process, and the OTLP exporter is an opt-in extra that is not installed. Logs are verified the same way the metrics are -- against their mechanism rather than a reviewer's attention: the field allowlist, the salted hash on identifier fields and the free-text scrub are exercised with the username planted in a token subject, a query string, a header and an exception message, and the rendered output is asserted free of it (R-54, D-052). Every request logs one structured line with the route template, the status, the duration and both correlation ids, and a path or query string is never logged. Before a secret is configured an identifier is redacted rather than hashed with a constant key. A golden test drives that whole path in one process -- synthetic traffic through the real ingest route, producer, windower, correlator and query API -- with the broker and the alert store as in-process fakes, so CI needs no Docker-in-Docker (R-88, D-053). The published API reference is generated the same way: [api-reference.md](api-reference.md) is rendered from the application's own schemas by `scripts/generate_api_reference.py`, and the build re-renders it with `--check` and fails on any difference, so a route without a request or response schema — or one that serves a media type its document does not name — cannot ship (T-320, D-054). `audit_log` and `api_keys` are both in T-301's migration, and on 2026-10-05 that
**migration was applied to a real PostgreSQL 16** (a sandbox install, not CI) while verifying T-321's typed score
columns (D-055; the 13 live tests pass against a sandbox server, and skip in CI). No database session is
wired into the request path (D-030), so the alert, audit and API-key stores are in-memory and die with the
process; the admin screens and the audited export (FR-43) are later tasks. The rate limiter is
in-memory too: buckets do not survive a restart, and each worker process counts its own, so a
multi-worker deployment gets the configured rate per worker until a shared store exists (D-048). The
ingest buffer is the same shape of limitation -- it is held for the duration of a request, not
released on delivery to Kafka, because the producer does not exist yet (D-039).

Datasets (UNSW-NB15, CIC-IDS2017) are large and are **never committed** (R-40). The fetched
copies are hash-verified by `scripts/fetch_datasets.py` and recorded in
[memory.md](memory.md#data-sources).
