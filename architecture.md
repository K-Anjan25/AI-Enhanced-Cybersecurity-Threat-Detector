# Architecture — AI-Enhanced Cybersecurity Threat Detector (AEGIS)

| | |
|---|---|
| **Document** | System architecture and technical design |
| **Version** | 0.1 |
| **Last updated** | 2026-10-02 |
| **Status** | Approved for build |
| **Implements** | [prd.md](prd.md) FR-01…FR-54, NFR-01…NFR-12 |
| **Related** | [rules.md](rules.md) · [design.md](design.md) · [task.md](task.md) · [memory.md](memory.md) |

---

## 1. Architectural principles

1. **Telemetry never blocks.** Ingestion writes to the bus first. Scoring failure degrades detection latency, never data loss.
2. **Stateless compute, stateful stores.** API workers and scorers are disposable. All state lives in PostgreSQL, Elasticsearch, or Kafka.
3. **Deterministic inference.** Same input + same pinned model ID ⇒ identical output. No clocks, no randomness, no ambient config in the scoring path (NFR-10).
4. **Every alert is reproducible.** We keep the raw window that produced an alert, so a verdict can be re-explained months later.
5. **Two models, one score.** Flow and log models are trained, versioned, deployed, and rolled back independently, then fused late.
6. **Boring technology first.** Postgres, Kafka, FastAPI, React. Exotic components must earn their place with a decision record in [memory.md](memory.md).

## 2. High-level architecture

```
                              ┌────────────────────────────────────────────────┐
   Flow sources               │                  AEGIS platform                 │
  (Zeek/NetFlow) ─┐           │                                                │
                  ├──►┌───────────────┐    ┌─────────────┐   ┌──────────────┐  │
   Log sources    │   │   Ingest API  │───►│   Kafka     │──►│  Scoring     │  │
 (syslog/auditd) ─┘   │  (FastAPI)    │    │  flows.raw  │   │  Workers     │  │
                      │  validate +   │    │  logs.raw   │   │  window +    │  │
   CLI / generator ──►│  schema check │    └─────────────┘   │  infer       │  │
                      └───────┬───────┘                      └──────┬───────┘  │
                              │ raw records                         │ scores   │
                              ▼                                     ▼          │
                      ┌───────────────┐                     ┌──────────────┐   │
                      │ Elasticsearch │                     │  Correlator  │   │
                      │ (raw search)  │                     │ dedupe+group │   │
                      └───────┬───────┘                     └──────┬───────┘   │
                              │                                    │ alerts    │
                              │        ┌──────────────┐            ▼          │
                              └───────►│  PostgreSQL  │◄───────────┘          │
                                       │ alerts, users│                       │
                                       │ models, audit│                       │
                                       └──────┬───────┘                       │
                                              │                               │
                          ┌───────────────────┼───────────────────┐           │
                          ▼                   ▼                   ▼           │
                   ┌────────────┐      ┌────────────┐      ┌────────────┐     │
                   │  Query API │      │  WebSocket │      │  Webhooks  │     │
                   │  (FastAPI) │      │  /ws/alerts│      │  (signed)  │     │
                   └─────┬──────┘      └─────┬──────┘      └────────────┘     │
                         └─────────┬─────────┘                                │
                                   ▼                                          │
                          ┌─────────────────┐         ┌──────────────────┐    │
                          │  React dashboard │         │ Prometheus/Grafana│   │
                          └─────────────────┘         └──────────────────┘    │
                              └────────────────────────────────────────────────┘
```

## 3. Repository layout

Monorepo, three deployable units. Directory names below are the contract; do not invent siblings without updating this file.

```
AI-Enhanced-Cybersecurity-Threat-Detector/
├── prd.md  architecture.md  rules.md  design.md  task.md  memory.md
├── README.md  CONTRIBUTING.md  .editorconfig  .gitignore  ruff.toml
├── backend/                  # FastAPI: ingest + query API, auth, alerts
│   ├── app/
│   │   ├── api/v1/           # routers, one module per resource
│   │   ├── core/             # config, db, security, events
│   │   ├── models/           # SQLAlchemy ORM
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── services/         # business logic (no FastAPI imports)
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── ml-service/               # Model serving + training entrypoints
│   ├── aegis_ml/
│   │   ├── features/         # flow + log feature extraction, versioned
│   │   ├── models/           # flow_transformer.py, log_transformer.py
│   │   ├── scoring/          # windowing, fusion, explanation
│   │   └── serving/          # FastAPI inference app
│   ├── registry/             # immutable model version registry
│   ├── training/             # pipelines, configs, eval harness
│   ├── artifacts/            # gitignored; model weights + manifests
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── dashboard/                # React + TypeScript + Vite
│   ├── src/
│   │   ├── features/         # one folder per page domain
│   │   ├── components/ui/    # design-system primitives from design.md
│   │   ├── components/layout/  # AppShell: nav rail + top bar
│   │   ├── api/              # typed API clients
│   │   ├── theme/            # ThemeProvider + the WCAG contrast suite
│   │   ├── lib/              # shared utilities (contrast maths)
│   │   ├── hooks/  store/  types/
│   │   └── App.tsx           # route table
│   ├── tests/                # colocated as *.test.tsx
│   ├── Dockerfile  nginx.conf
│   └── package.json  package-lock.json
├── data/                     # gitignored: raw/, processed/, external/
├── docker/docker-compose.yml # local stack
├── k8s/                      # production manifests
├── .github/workflows/ci.yml  # docs, infra, backend, ml-service, dashboard jobs
└── scripts/                  # check_all.sh, check_docs.py, check_compose.py,
                              # plus dataset fetch and the synthetic generator
```

## 4. Component responsibilities

| Component | Tech | Responsibility | Explicitly not responsible for |
|---|---|---|---|
| **Ingest API** | FastAPI | Schema validation, batching, PII redaction, write to Kafka + ES, ack | Scoring, alerting, business rules |
| **Scoring worker** | Python + PyTorch | Window assembly, model inference, fusion, explanation | Auth, persistence of raw telemetry |
| **Correlator** | Python | Deduplication, cool-down suppression, flow↔log grouping, alert persistence | Model logic |
| **Query API** | FastAPI | Reads for the dashboard: alerts, entities, metrics, hunt search | Writes from telemetry |
| **Auth service** | FastAPI module | Users, roles, JWT issue/refresh, API keys, audit writes | Business logic |
| **Dashboard** | React 18 + TS | Presentation, local interaction state, optimistic verdicts | Detection logic, data transformation beyond formatting |
| **Model service** | FastAPI + PyTorch | Load pinned model versions, serve scores, expose metrics | Storage, auth (behind the internal network) |

## 5. Data flow: one flow record end to end

1. **Arrival.** `POST /api/v1/ingest/flows` with an NDJSON batch. The API authenticates (JWT or API key), rate-limits, and validates each record against `flow@1`.
2. **Redaction.** Configured PII fields (usernames, hostnames matching a redaction pattern) are replaced with salted hashes. The original is not stored.
3. **Fan-out.** Valid records are produced to Kafka `flows.raw` (partitioned by `src_ip` so one entity's flows stay ordered) and indexed into Elasticsearch for search.
4. **Windowing.** The scoring worker consumes `flows.raw`, maintaining a per-entity deque of the last 50 flows (FR-10). When a window closes — by count or by a 10 s inactivity timer — it is emitted for inference.
5. **Inference.** Feature extraction → flow transformer → per-flow reconstruction error and a sequence-level anomaly probability.
6. **Fusion.** If a log window for the same entity closed within the fusion window (±60 s), the composite score is computed. Otherwise the flow score alone is used with a documented confidence penalty.
7. **Correlation.** Score is banded to a severity, deduplicated against the cool-down key `(entity, family)`, and written to PostgreSQL `alerts` with a pointer to the raw window.
8. **Notification.** WebSocket push to subscribed dashboards; signed webhook for `high`/`critical`.
9. **Feedback.** An analyst verdict is written back and joins the weekly threshold-recalibration job.

**Latency budget** (NFR-01, p95):

| Stage | Budget |
|---|---|
| Ingest validate + Kafka produce | 40 ms |
| Kafka → worker consume | 100 ms |
| Window assembly | 20 ms |
| Feature extraction | 15 ms |
| Transformer inference (batch 1 window) | 90 ms |
| Fusion + correlate + persist | 30 ms |
| WebSocket delivery | 20 ms |
| **Total** | **≈ 315 ms** — comfortably inside the 5 s NFR with headroom for backpressure |

The window inactivity timer (up to 10 s) dominates real-world end-to-end time for low-rate entities. That is by design: it trades detection latency for statistical validity.

## 6. Data model (PostgreSQL)

```
users(id, email, argon2_hash, role, created_at, disabled_at)
roles: viewer | analyst | responder | admin
api_keys(id, owner_id, name, key_hash, scopes[], last_used_at, revoked_at)

alerts(id, entity_id, family, severity, score, model_flow_id, model_log_id,
       window_ref, explanation jsonb, status, first_seen, last_seen,
       occurrence_count, assigned_to, verdict, verdict_at, verdict_by, created_at)

alert_status: open | acknowledged | closed
verdict:      true_positive | false_positive | benign | null

entities(id, kind, value, first_seen, last_seen, meta jsonb)   -- kind: host|ip|user|service
entity_kind: host | ip | user | service

models(id, name, version, kind, artifact_uri, metrics jsonb, training_manifest jsonb,
       status, created_at)
model_status: staging | active | retired

model_versions_history(id, model_id, promoted_at, promoted_by, rolled_back_at)
audit_log(id, actor_id, action, target_type, target_id, detail jsonb, ip, at)   -- append only
thresholds(id, tenant_id, family, band, value, source, updated_at)
ingest_stats(id, source, accepted, rejected, rejected_reasons jsonb, window_start)
```

Design notes:

- `alerts` and `ingest_stats` are partitioned monthly by time; retention is enforced by dropping partitions (NFR-05, GDPR erasure).
- `audit_log` has no UPDATE/DELETE path in the ORM. Enforced by rule R-31.
- `window_ref` is an opaque pointer `{store: "es"|"pg", id: ...}` — the raw window must outlive the alert or the alert is marked `evidence_expired` rather than silently unexplainable.

## 7. Model architecture

### 7.1 Flow-sequence model (`FlowNet`)

Input: a window of **W = 50** consecutive flows from one source entity, ordered by arrival.

Per-flow feature vector (24 features):

| Group | Features |
|---|---|
| Identity (categorical, embedded) | protocol, service, state, direction |
| Volume (numeric, standardised) | src_bytes, dst_bytes, packets, src_packets, dst_packets |
| Timing (numeric) | duration, inter_arrival_mean, inter_arrival_std |
| Flags (binary) | syn, ack, rst, fin, psh, urg counts |
| Derived | byte_ratio, packet_ratio, port_entropy, dst_port_count, dst_ip_count |

```
per-flow features ──► categorical embeddings ⊕ numeric MLP ──► d_model = 128
                                    │
                                    ▼
                    + positional encoding (sinusoidal)
                                    │
                                    ▼
              Transformer encoder × 4  (heads = 8, FFN = 512, dropout 0.1)
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
            per-token decoder head          sequence pooling (attention)
            → reconstruct next flow's              │
              numeric features (MAE)               ▼
                     │                     binary anomaly head (sigmoid)
                     ▼                             │
              reconstruction error r               ▼
                     └──────────┬──────────────────┘
                                ▼
              score = σ(w₁·(1−p_normal) + w₂·z(r) + b)
```

Training objectives: weighted BCE on the anomaly head + λ·MAE on the reconstruction head (λ = 0.3). Parameter count target ≈ 1.2 M — deliberately small, so inference fits the latency budget on CPU. This is a design target to be confirmed by T-201, not a measured figure.

### 7.2 Log-sequence model (`LogNet`)

Input: **W = 200** consecutive log lines from one host+service.

1. **Template mining.** Drain3 extracts log templates online; each line becomes `(template_id, parameter_vector)`. This is what makes the model robust to log spam and vocabulary drift.
2. **Encoding.** Template IDs map to learned embeddings; parameters are embedded numerically. (Open question Q-01 in [prd.md](prd.md#12-open-questions): whether to replace this with a frozen DistilBERT encoder for unstructured messages.)
3. **Encoder.** Transformer encoder × 6, `d_model = 256`, heads = 8, FFN = 1024.
4. **Objectives** (LogBERT-style): masked-template prediction (predict held-out template IDs in the window) + hypersphere loss pulling normal windows toward a learned centre.
5. **Score.** Deviation = negative log-likelihood of masked templates + distance from the hypersphere centre, min-max calibrated on validation normal data.

### 7.3 Fusion and explanation

- **Late fusion.** `composite = 1 − (1 − s_flow)·(1 − s_log)` when both are present; single-modality scores are penalised by ×0.9 and flagged `partial_evidence` in the UI. Rationale: independence of errors, and it lets each model be shipped alone.
- **Explanation.** Attention rollout over the encoder gives per-position importance; for flow features, per-feature SHAP values are computed on the window. The top 3 items are rendered as plain language ("`dst_port_count` 1,204 vs. baseline 12 — port sweep"). FR-14 requires this on every alert; an alert without an explanation is a bug, not a degraded mode.

### 7.4 Thresholding and calibration

Thresholds are **not** global constants. Per-tenant, per-family quantiles are fit on a rolling 14-day window of scores that analysts labelled `benign`/`false_positive`. The default band edges from FR-13 are the initial values before enough feedback exists. Recalibration is a weekly job with a guardrail: a single run may not move a threshold by more than 0.10, and any change is written to `audit_log`.

## 8. Training pipeline

```
fetch datasets ──► verify checksums ──► parse to parquet ──► feature build (versioned)
        │                                                           │
        │                                     ┌─────────────────────┴──────────────┐
        ▼                                     ▼                                    ▼
  data/raw/ (gitignored)          TEMPORAL split by timestamp          leak audit (entities
                                  train / valid / test                 disjoint across folds)
                                        │
                                        ▼
                          train (PyTorch, seeded, config-driven)
                                        │
                                        ▼
                     evaluate: precision, recall, F1, ROC-AUC, PR-AUC
                               + cross-dataset transfer test
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                     artifacts/<model_id>/   training_manifest.json
                     (weights, config,       (dataset hashes, git SHA,
                      scaler, vocab)          config, metrics, seeds)
                              │
                              ▼
                     promote to `staging` → shadow-score → `active`
```

Non-negotiable training rules (enforced in CI where possible, see [rules.md](rules.md#7-machine-learning-rules)):

- **Temporal splits only.** Never shuffle across time. Test set is strictly later than train.
- **Entity-disjoint folds.** Cross-validation folds must not share source entities, or the model memorises hosts rather than behaviour.
- **Class imbalance** handled with class-weighted loss and/or stratified sampling; never by deleting benign data.
- **Baselines first.** A gradient-boosting baseline on the same features is computed and recorded before any transformer result is accepted.
- **Reproducibility.** Fixed seeds, pinned dependency lockfile, config-as-code. Two runs of the same config must agree within ±0.005 AUC.

## 9. Model serving

- Model artifacts are content-addressed; the API references an immutable `model_id`. No "latest".
- The serving process loads the requested versions at boot, keeps them resident, and exposes `/internal/score/flow` and `/internal/score/log`.
- **Shadow mode.** A newly promoted model can score live traffic without publishing alerts, so its score distribution is compared against the active model before it owns alerts.
- **Rollback** is a single `POST /api/v1/models/{id}/promote` with the previous version — no redeploy.
- CPU-first inference. GPU is optional and only used for training and for throughput beyond the CPU budget. ONNX export is the documented latency fallback (risk in [prd.md](prd.md#10-risks-and-mitigations)).

## 10. Frontend architecture

- **React 18 + TypeScript + Vite**, routing via React Router, server state via TanStack Query, minimal client state via Zustand.
- **Feature-sliced:** `src/features/<domain>/pages` and `/components`. No cross-feature imports; shared code lives in `components/ui` or `lib`.
- **API layer:** one typed client module per backend resource, generated types preferred. Components never call `fetch` directly.
- **Realtime:** a single WebSocket connection at the app shell, fanned out through a pub/sub hook. Auto-reconnect with exponential backoff and a visible `disconnected` banner.
- **Visualisation:** D3 for the entity graph and time-series brushing; Chart.js for standard KPI and bar charts. Both share the severity palette in [design.md](design.md#5-design-tokens).
- **No detection logic in the browser.** The UI displays and filters; it never computes scores or re-derives severity.

## 11. Deployment

### 11.1 Local development (primary target)

`docker compose up` starts: postgres, redis, kafka + zookeeper, elasticsearch, backend, ml-service, dashboard. Everything binds inside the compose network; only the dashboard and backend publish ports. Datasets are fetched on demand into `data/raw/` — never baked into images.

### 11.2 Production (Kubernetes)

| Workload | Replicas | Scaling |
|---|---|---|
| backend (ingest + query) | 2+ | HPA on CPU and request latency |
| scoring workers | 2+ | HPA on Kafka consumer lag |
| ml-service | 2+ | HPA on inference queue depth |
| dashboard (nginx static) | 2+ | HPA on request rate |
| postgres | 1 primary + replica | Vertical, plus partition management job |
| kafka | 3 brokers | Partition count is the scale unit |
| elasticsearch | 3 nodes | ILM policy rolls indices daily |

Ingress terminates TLS. Secrets come from the cluster secret store, never from images or manifests.

### 11.3 CI/CD

GitHub Actions on every push and PR:

1. **lint** — ruff + black (Python), eslint + prettier (TS), both must pass.
2. **typecheck** — mypy strict on backend services, `tsc --noEmit` on the dashboard.
3. **test** — pytest (backend, ml-service), vitest (dashboard). Coverage gate ≥ 80% backend.
4. **build** — Docker images built and scanned (Trivy); failures block merge.
5. **model eval** — on changes under `ml-service/`, run the eval harness against a small fixed fixture and post metrics to the PR.

Merges to `main` build and push tagged images. Promotion to an environment is a manual approval step.

## 12. Security of the system itself

AEGIS holds attacker-relevant intelligence: internal hostnames, IP topology, successful and failed auth patterns. Its compromise is a high-value event. The threat model, therefore:

| Threat | Control |
|---|---|
| Unauthenticated ingest flooding | API keys with scopes, per-key rate limiting, request size caps, backpressure to Kafka |
| Alert-store exfiltration | Encryption at rest, row-level access by role, no bulk export above `responder`, export events audited |
| Prompt/injection via log content into explanations | Log strings are rendered as inert text, never as markup or code; escaping enforced in the UI layer |
| Privilege escalation in the app | RBAC checked server-side on every route; frontend gating is cosmetic only |
| Credential theft | Argon2id hashing, short-lived JWTs (15 min), refresh rotation, secrets from env/secret manager |
| Supply-chain | Pinned lockfiles, image scanning in CI, no `latest` tags, model artifacts checksummed |
| Tampering with audit trail | Append-only table, no ORM update/delete path, periodic hash-chaining of audit rows (post-v1) |
| SSRF via outbound webhooks | Webhook URLs validated against an allowlist; private IP ranges blocked |

## 13. Observability

| Signal | Implementation |
|---|---|
| Metrics | Prometheus client in backend, ml-service, scoring workers. Golden signals per service plus domain metrics: `aegis_flows_ingested_total`, `aegis_score_latency_seconds`, `aegis_alerts_created_total{severity}`, `aegis_consumer_lag`, `aegis_drift_psi{feature}` |
| Logs | Structured JSON via structlog, request-scoped correlation ID propagated to Kafka headers |
| Traces | OpenTelemetry spans across ingest → score → correlate → notify |
| Dashboards | Grafana: detection health, model drift, API SLOs, Kafka lag |
| Alerts (about AEGIS) | Consumer lag > 10k, scoring p95 > 1 s, drift PSI > 0.25, error rate > 1%, model score distribution shift |

Every AEGIS alert row is itself a business event and is queryable for MTTR reporting — the system must be able to report on its own performance (NFR-07).

## 14. Scalability and failure modes

| Failure | Behaviour | Recovery |
|---|---|---|
| Scoring worker down | Kafka buffers; consumer lag rises; alerts delayed | Worker restart resumes from committed offset; no data loss |
| Model service OOM | Scores fail; ingest continues | Worker falls back to last-known-good model version, then to rule-based safety net; alert marked `degraded_scoring` |
| Elasticsearch down | Ingest continues to Kafka; hunt search unavailable | Reindex from Kafka on recovery; UI shows a search-unavailable state, not a blank page |
| PostgreSQL down | Reads fail; API returns 503 with `Retry-After` | Scoring continues writing to Kafka; catch-up job replays |
| Kafka down | Ingest API returns 503 and clients retry | Bounded in-memory buffer for a short outage; explicit back-pressure, never silent drops |
| Dashboard WebSocket drops | UI falls back to REST polling at 15 s; banner shown | Auto-reconnect with backoff |

Scaling unit is the Kafka partition. Adding partitions and worker replicas scales throughput linearly until PostgreSQL write contention appears, at which point alert writes are batched.

## 15. Technology decisions

Full rationale in [memory.md](memory.md#decisions-log).

| Area | Choice | Rejected alternative | Why |
|---|---|---|---|
| API framework | Python + FastAPI | Node/Express | Model and API share one language; async; native Pydantic schemas |
| Model framework | PyTorch + HF Transformers | TensorFlow | Ecosystem for custom sequence models, cleaner research iteration |
| Primary DB | PostgreSQL | MongoDB | Alerts/users/audit are relational; partitioning gives retention for free |
| Log search | Elasticsearch | Postgres FTS | Volume + aggregation for the hunt console (pending Q-02) |
| Streaming | Kafka | Redis Streams | Durable replay, partition ordering per entity, consumer groups |
| Frontend | React 18 + TS + Vite | Angular | Team velocity, ecosystem for D3/Chart.js integration |
| Visualisation | D3 + Chart.js | Single library | D3 for custom graph/brush interactions, Chart.js for standard charts |
| Packaging | Docker + compose, k8s manifests | Bare metal | NFR-08 portability |

## 16. Architectural decision records

Significant decisions are recorded as short ADRs inside [memory.md](memory.md#decisions-log) with status, context, decision, and consequences. An architecture change that contradicts this document requires: (1) an ADR entry, (2) an edit to this file, (3) a note in the PR description referencing both.
