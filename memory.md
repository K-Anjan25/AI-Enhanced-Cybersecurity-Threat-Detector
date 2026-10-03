# Memory — AI-Enhanced Cybersecurity Threat Detector (AEGIS)

| | |
|---|---|
| **Document** | Persistent project context, decisions, and ledger |
| **Version** | 0.1 |
| **Last updated** | 2026-10-02 (Friday) |
| **Purpose** | The document a new engineer — or you in three months — reads first |
| **Related** | [prd.md](prd.md) · [architecture.md](architecture.md) · [rules.md](rules.md) · [design.md](design.md) · [task.md](task.md) |

---

## What this project is

AEGIS uses **transformer models** over **network flow records** and **system logs** to detect anomalies and predict cybersecurity threats before they become confirmed incidents. It is a detection and triage platform: telemetry in, ranked and explained alerts out, with an analyst loop that closes in under a minute.

- Scope, threat families, and requirements: [prd.md](prd.md)
- System and model design: [architecture.md](architecture.md)
- How we write code: [rules.md](rules.md)
- How it looks and behaves: [design.md](design.md)
- What we build and when: [task.md](task.md)

**One-line pitch.** Signature-based detection misses novel behaviour; AEGIS learns what "normal" looks like per entity and flags the deviation, with evidence attached.

## Current state (as of 2026-10-03)

| Aspect | State |
|---|---|
| Repository | Six planning documents plus the Sprint S0 scaffolding (commit `23b6a57` onward) |
| Source code | `backend/` FastAPI skeleton, `ml-service/` inference skeleton **plus the S1 data layer** (`aegis_ml/data/`: `flow@1` and `log@1` records, seven-scenario synthetic generator, `features@1` extraction, sliding windowing), `dashboard/` React shell — all tested. No model code |
| Tests | 142 passing — 20 backend, 88 ml-service, 34 dashboard. Coverage 90.3% on `app/` against the 80% gate (R-80) |
| Checks green | `./scripts/check_all.sh` — 19 checks: ruff, black, mypy strict, bandit, import-linter, pytest ×2, coverage, tsc, eslint, vitest, vite build, doc integrity, compose consistency. Five were proven to fail on an injected violation before being trusted |
| Dependencies | Python via `pip install -e "backend[dev]" -e "ml-service[dev]"` (both verified); npm `package-lock.json` committed for `npm ci` (R-08) |
| Datasets | **Public sets not downloaded** — their hosts are unreachable from this sandbox. Synthetic data generates on demand via `scripts/generate_synthetic.py` into the gitignored `data/` |
| Models | **None trained.** No baselines, no metrics |
| Branch | `arena/01a0fee2-ai-enhanced-cybersecurity-thre`, based on `60e9adf` |
| Next work | S0 is complete except T-005 execution (needs Docker) and `k8s/`. In S1, T-106, T-107 and T-108 are DONE; T-109 (temporal, entity-disjoint splits) is next |

Sprint S0 started early, on 2026-10-02. Per-task status lives under the E0 table in [task.md](task.md#3-epic-e0--foundations-m0); the rest of the plan is still `TODO`.

## Repository reset record

On 2026-10-02 the working tree was cleared at the request of the project owner, to restart the project from a documentation-first footing.

**What was removed** — 487 files tracked at commit `60e9adf` ("added changes"):

| Path | Files | What it was |
|---|---|---|
| `backend/` | 236 | FastAPI application: ~65 API endpoint modules, ORM models, services, tests |
| `dashboard/` | 197 | React + TypeScript + Vite dashboard with ~50 feature pages |
| `ml-service/` | 18 | Model serving stubs: network, log, DNS, and email models |
| `diagrams/` | 13 | UML and architecture diagrams in Markdown |
| `k8s/` | 10 | Kubernetes manifests |
| `loadtest/` | 4 | k6 and Locust load tests |
| `docs/` | 4 | Functional/non-functional requirements, terminology |
| `docker/` | 2 | compose file and README |
| root | 3 | `README.md`, `.gitignore`, `.github/workflows/ci.yml` |

**Why.** The previous tree had grown into a very broad security platform — endpoint modules included CSPM, ZTNA, ITDR, deception, SBOM, SCIM, SOC-TV, and digital-risk protection. That breadth had outrun the project's actual objective: transformer-based anomaly detection over network traffic and system logs. Restarting from the PRD keeps the scope honest and matches [prd.md](prd.md#3-scope).

**What is recoverable.** The removal is a working-tree change; commit `60e9adf` is intact and still lists all 487 files. Anything can be brought back:

```bash
git show 60e9adf --stat                      # inspect the previous tree
git checkout 60e9adf -- <path>               # restore a specific file or directory
```

Nothing has been rewritten, force-pushed, or garbage-collected. **Deliberately not carried forward:** the previous `docs/`, `diagrams/`, and endpoint modules. They describe a different product and would contradict the new PRD; salvaging them piecemeal is how scope creep returns.

**Deliberately carried forward as intent:** the previous tree validated the general shape of the stack — FastAPI backend, React/TypeScript dashboard, a separate ml-service, Docker plus Kubernetes, k6/Locust load tests. That shape is retained in [architecture.md](architecture.md#15-technology-decisions) because it was sound. The code was not reused.

## Decisions log

Format: **status** · context · decision · consequences. A decision is changed by adding a new entry that supersedes the old one — never by editing history.

### D-001 · Scope covers network traffic **and** system logs — ACCEPTED (2026-10-02)
**Context.** The brief left the choice open: traffic, logs, or both.
**Decision.** Both. Flow records cover network-layer attacks; logs cover identity and insider behaviour. The two are fused late.
**Consequences.** Two models to train, version, serve, and monitor. Higher build cost, but single-modality coverage would leave threat families T4–T6 ([prd.md](prd.md#31-in-scope-for-v10)) undetectable. Drives FR-11, FR-19, and the fusion design in [architecture.md](architecture.md#73-fusion-and-explanation).

### D-002 · Python + FastAPI for the API — ACCEPTED (2026-10-02)
**Context.** Brief allowed Node.js/Express or Python Flask/Django, and separately named FastAPI for model serving.
**Decision.** Python 3.11+ with FastAPI for both the ingest/query API and the model service. The floor is 3.11 because that is what the dev sandbox provides and therefore what CI can actually verify; nothing in the design needs 3.12.
**Consequences.** One language across API and ML; native Pydantic validation shared with the feature pipeline; async I/O for the ingest path. Rejected Node/Express because it would force a second language and a serialisation boundary between API and model. Django was rejected as too heavy for an API-only service.

### D-003 · PyTorch + Hugging Face Transformers — ACCEPTED (2026-10-02)
**Context.** Brief allowed PyTorch or TensorFlow.
**Decision.** PyTorch, with Hugging Face `transformers` used where a pretrained encoder helps (candidate for the log model — see Q-01).
**Consequences.** Custom sequence models are easier to express and iterate on in PyTorch; the HF ecosystem covers pretrained log encoders. Cost: fewer turnkey production serving tools than TF Serving — mitigated by our own FastAPI serving layer and the ONNX fallback (T-210).

### D-004 · PostgreSQL primary, Elasticsearch for raw search — ACCEPTED, UNDER REVIEW (2026-10-02)
**Context.** Brief allowed MongoDB, PostgreSQL, or Elasticsearch.
**Decision.** PostgreSQL for alerts, users, models, and audit (relational, partitioned, transactional). Elasticsearch for raw flow/log search in the hunt console.
**Consequences.** Two stores to operate. **Open question Q-02** asks whether partitioned Postgres with full-text search suffices at v1.0 volume; if it does, Elasticsearch is dropped before T-305 and the deployment gets materially simpler.

### D-005 · Kafka as the streaming bus — ACCEPTED (2026-10-02)
**Context.** The brief calls for real-time streaming analysis.
**Decision.** Kafka, partitioned by `src_ip` so one entity's flows keep their order.
**Consequences.** Durable replay, consumer groups, and lag as a first-class scaling signal. Cost: another stateful cluster to run, and it is the heaviest component in the local dev stack. Redis Streams was rejected — no durable replay, and losing telemetry during a scoring outage is unacceptable.

### D-006 · React 18 + TypeScript + Vite dashboard — ACCEPTED (2026-10-02)
**Context.** Brief allowed React or Angular.
**Decision.** React 18 + TypeScript + Vite, Tailwind, TanStack Query, Zustand.
**Consequences.** Feature-sliced structure enforced by import boundaries (R-22); D3 and Chart.js both integrate cleanly. Angular was not chosen — team velocity and ecosystem familiarity favour React.

### D-007 · D3 for custom visuals, Chart.js for standard charts — ACCEPTED (2026-10-02)
**Context.** Brief allowed D3 or Chart.js.
**Decision.** Both, with a hard split: D3 for the entity graph and brushable time-series, Chart.js for KPI, bar, and histogram charts.
**Consequences.** Two charting APIs to learn; the boundary is stated in [design.md](design.md#7-data-visualisation) so it does not become arbitrary. Both consume the same severity tokens.

### D-008 · Detection only — no inline blocking in v1.0 — ACCEPTED (2026-10-02)
**Context.** "Mitigating risks" in the brief could imply automated response.
**Decision.** v1.0 detects, explains, and notifies. Response is delegated to the customer's own controls via signed webhook.
**Consequences.** Removes an entire class of blast-radius risk from a v1.0 system and keeps the security review tractable (T-506). SOAR playbooks sit in the backlog as T-604.

### D-009 · Temporal, entity-disjoint evaluation only — ACCEPTED (2026-10-02)
**Context.** Random splits on intrusion-detection datasets routinely inflate scores through leakage.
**Decision.** Train/valid/test split by time; cross-validation folds entity-disjoint; scalers and vocabularies fit on train only.
**Consequences.** Reported metrics will look worse than published leaderboard numbers for the same datasets. That is the point — the numbers will be real. Enforced by R-60…R-62 and the leakage audits T-111 and T-203.

### D-010 · Documentation-first restart — ACCEPTED (2026-10-02)
**Context.** The repository reset recorded above left no code behind.
**Decision.** The six documents are the deliverable of this phase. No scaffolding, no `.gitignore`, no CI until S0 begins.
**Consequences.** Zero ambiguity about intent before code is written; the trade-off is that nothing is executable yet, so **no claim in these documents has been verified by running software**. Every performance, throughput, and metric figure in the PRD is a target, not a measurement — see the measurement ledger below.

### D-011 · Canonical telemetry schemas live in `ml-service`, mirrored by contract not by import — ACCEPTED (2026-10-03)
**Context.** T-106 needed machine-checked `flow@1` and `log@1` records, and the backend will later store and serve the same shapes (T-304). Python services cannot import across the `backend/` ↔ `ml-service/` boundary without breaking the deployment split.
**Decision.** The authoritative definitions are Pydantic models in `ml-service/aegis_ml/data/records.py`. Both are frozen with `extra="forbid"`, reject naive timestamps, and pin their version through a `Literal` field, so an unknown version fails at parse time rather than downstream. The backend will define its own equivalent models and the equivalence will be pinned by a shared JSON-schema fixture and a contract test — not by a cross-service import.
**Consequences.** Two definitions of the same shape exist, and drift between them is possible; the contract test at T-304 is what makes drift a build failure. Derived features (byte ratio, port entropy, destination counts) are deliberately *not* fields — they are computed at T-107 — so the stored record stays a faithful capture and a feature change never silently rewrites history.

### D-012 · `features@1` is pinned by a schema hash, and the flow vector has 23 features — ACCEPTED (2026-10-03)
**Context.** T-107 needed a feature contract that cannot drift silently. `architecture.md` §7.1 also claimed "24 features" while its table enumerates 23 across five groups (4 identity, 5 volume, 3 timing, 6 flags, 5 derived) — counted by script, not by eye.
**Decision.** The table is the specification, so the vector has **23** features and the prose was corrected. The contract is pinned by `schema_hash()`, a SHA-256 over the version string plus every feature name in order for both modalities; a golden copy of that digest lives in the test, so changing a feature without bumping `FEATURES_SCHEMA_VERSION` fails the build. Five features (`inter_arrival_mean`, `inter_arrival_std`, `port_entropy`, `dst_port_count`, `dst_ip_count`) are properties of the window and are broadcast onto every row.
**Consequences.** Any feature change is a deliberate, reviewed version bump — at the cost of touching two constants and a test whenever the model input evolves. Because window-level features are broadcast, the same flow extracted in two different windows legitimately yields two different rows; that is intended, not a bug. Ratios are Laplace-smoothed so zero-reply flows (port scans) stay finite.

### D-013 · The window key is a parameter, and inactivity is applied before count — ACCEPTED (2026-10-03)
**Context.** Q-06. `architecture.md` §7.1 keys a flow window on one source entity, but T-107 measured the consequence: the synthetic DDoS scenario spreads a single flood across ~40 sources, so each per-source window holds one flow and the attack is invisible at that granularity, while a destination-keyed window holds all 40.
**Decision.** `WindowKey.SOURCE` / `WindowKey.DESTINATION` is a parameter, not a constant. Source stays the default — reconnaissance, credential abuse and exfiltration are properties of a source — and volumetric families (T2) are detected on destination-keyed windows. `extract_flow_window` takes the same key, so a destination-keyed window (which legitimately contains many sources) is validated on the right dimension instead of rejected. Inactivity is applied *before* count: the per-key stream is cut into bursts and no window spans a burst boundary. Stride defaults to size (tumbling), because overlapping windows count one event several times and inflate any per-window metric (D-009).
**Consequences.** Covering both families means two windowing passes, which raises the window count for volumetric detection and must be priced into the throughput budget (NFR-03) at T-201. The feature set is still source-centric — `dst_port_count` and `dst_ip_count` mean something different on a destination-keyed window — so T-201 will likely need destination-specific features. That is a modelling change and does not alter the `features@1` hash.

## Data sources

Datasets are never committed to Git (R-40). Checksums below are recorded as *pending capture* — they must be filled in by T-102 before any dataset is used in a training run (R-41).

| Dataset | Purpose | Source | Licence | SHA-256 | Records |
|---|---|---|---|---|---|
| **UNSW-NB15** | Primary network training and evaluation | [research.unsw.edu.au/projects/unsw-nb15-dataset](https://research.unsw.edu.au/projects/unsw-nb15-dataset) | Research/academic use; verify terms at source before redistribution | *pending — T-102* | 2,540,044 records, 49 features (per the published dataset description) |
| **CIC-IDS2017** | DDoS/DoS, brute-force and web-attack coverage; cross-dataset transfer test | [unb.ca/cic/datasets/ids-2017.html](https://www.unb.ca/cic/datasets/ids-2017.html) | Free for research use; verify terms at source | *pending — T-102* | Multi-day PCAP plus labelled flows across five attack scenarios |
| **System-log corpora** (HDFS / BGL family) | Log-anomaly model training and evaluation | Public benchmark corpora; exact source and licence confirmed in T-104 | *pending — T-104* | *pending — T-104* | *pending — T-104* |
| **Synthetic generator** (ours) | Insider threat, beaconing, exfiltration scenarios; deterministic tests; demos | **Built** — `scripts/generate_synthetic.py`, T-106 DONE | Ours (project licence) | Deterministic by seed (R-42) | 7 scenarios × N; 1,400 records at N=200 |

**Notes that will bite us later, written down now:**

- Both network datasets are **2015 and 2017 vintage**. Protocols, encryption prevalence, and traffic mix have moved on. v1.0 is explicitly framed as architecture validation on public benchmarks; retraining on modern captures is backlog item T-612 and the first production task.
- Neither public dataset contains genuine insider-threat or long-period C2 beaconing behaviour. T-106 exists to fill that gap, and its scenarios must be described in the model card so nobody mistakes synthetic performance for field performance.
- Dataset sizes are large. They are fetched on demand, checksummed, and converted to Parquet (R-45). Never baked into a Docker image.

## Constraints and assumptions

**Hard constraints**

- Runs on a 16 GB developer laptop via `docker compose` (NFR-12). No paid external API is required for any core feature.
- No payload decryption, ever ([prd.md](prd.md#32-explicitly-out-of-scope-for-v10)).
- GDPR-aligned retention and erasure from the start, not retrofitted (NFR-05).
- Inference must be deterministic (NFR-10, R-67).

**Assumptions** — each one is a place the plan can break, so each is written down:

1. The deployment can supply NetFlow/Zeek-equivalent flow records. If it cannot, the synthetic generator stands in for demos only, and that limitation must be stated in the demo.
2. Log sources emit parseable timestamped lines. Unparseable lines are counted and surfaced, never silently dropped.
3. Class imbalance is handled in training by weighting and sampling, never by discarding benign data.
4. One shared model pair serves all tenants at v1.0; per-tenant fine-tuning is post-v1.
5. Deployment is on-premises or in a customer cloud account. AEGIS never sends telemetry to a third party.

## Ledger — measurements

**This section is intentionally empty.** No model has been trained and no benchmark has been run.

Rule R-74 forbids recording a number that was not measured, so no target values are pre-filled here. Targets live in [prd.md](prd.md#8-success-metrics); this ledger holds only results.

### Baseline results

| Feature set | Model | Split | Precision | Recall | F1 | ROC-AUC | PR-AUC | Run ref | Date |
|---|---|---|---|---|---|---|---|---|---|
| *none yet* | — | — | — | — | — | — | — | — | — |

*To be filled by T-110. These baselines are the bar every transformer result must clear (R-64).*

### Model results

| Model ID | Kind | Split | Precision | Recall | F1 | ROC-AUC | PR-AUC | Cross-dataset recall | p95 latency | Manifest | Date |
|---|---|---|---|---|---|---|---|---|---|---|---|
| *none yet* | — | — | — | — | — | — | — | — | — | — | — |

*To be filled by T-202 and T-208.*

### Performance verification

| NFR | Budget | Measured | Date | Evidence |
|---|---|---|---|---|
| NFR-01 ingest→alert p95 | ≤ 5 s | *not measured* | — | T-502 |
| NFR-01 window scoring p95 | ≤ 150 ms | *not measured* | — | T-209 |
| NFR-02 flow throughput | ≥ 5,000/s | *not measured* | — | T-501 |
| NFR-02 log throughput | ≥ 10,000/s | *not measured* | — | T-501 |

### Latency budget reference

The stage-by-stage budget in [architecture.md](architecture.md#5-data-flow-one-flow-record-end-to-end) sums to ≈ 315 ms at p95. **That figure is an engineering estimate derived from the NFR, not a measurement.** It has never been observed. T-502 exists to replace it with real numbers, and overruns become tasks rather than being absorbed into the table.

## Open questions

Tracked here; referenced from [prd.md](prd.md#12-open-questions). A question is closed by adding an entry to the decisions log, not by deleting the question.

| ID | Question | Owner | Blocks | Status |
|---|---|---|---|---|
| **Q-01** | Should `LogNet` use a frozen pretrained DistilBERT encoder over raw log messages, or a from-scratch transformer over Drain3-mined template IDs? | Model lead | **T-204** | OPEN — trade-off is transferable language knowledge vs. a far smaller model and no dependency on English-language pretraining for machine-generated text |
| **Q-02** | Is Elasticsearch justified at v1.0, or does partitioned PostgreSQL with full-text search cover the hunt console? | Backend lead | **T-305** | OPEN — depends on the target log volume, which is itself unknown until a reference deployment exists |
| **Q-03** | What absolute false-positive budget (alerts/day) will the reference customer tolerate? | Product | Threshold defaults, T-207 | OPEN — needed to set the shipped defaults rather than guessing |
| **Q-04** | Which reference deployment supplies real flow records, and in what format (NetFlow v5/v9, IPFIX, Zeek)? | Product | NFR-02 validation, T-612 | OPEN |
| **Q-05** | Do we need multi-tenancy at v1.0, or is single-tenant per deployment acceptable? | Product | Schema design, T-301 | OPEN — currently assumed single-tenant per deployment (D-001 context); the schema includes `tenant_id` on thresholds only |
| **Q-06** | For volumetric attacks, should a flow window be keyed on the source entity, the destination, or both? | Model lead | **T-108**, T-201 | **CLOSED by D-013 (2026-10-03)** — both, chosen per family. Raised by T-107. `architecture.md` §7.1 keys the window on one source entity, but the synthetic DDoS scenario spreads a single flood across ~40 sources, so each per-source window holds about one flow and the attack is invisible at that granularity. Either the window key changes, or volumetric detection needs a destination-side feature path |

## Glossary

Single source of truth; [design.md](design.md#10-content-and-copy-guidelines) links tooltips here.

| Term | Meaning |
|---|---|
| **Anomaly score** | Model output in `[0,1]` expressing how far a behavioural window deviates from learned normal for that entity |
| **Beaconing** | Periodic outbound contact at a regular interval, characteristic of C2 channels; detected via low inter-arrival jitter |
| **Composite score** | Late-fusion combination of the flow and log model scores ([architecture.md](architecture.md#73-fusion-and-explanation)) |
| **Cool-down** | Suppression window during which repeat alerts for the same (entity, family) increment a counter instead of creating a new alert |
| **Drain3** | Online log-template mining library that reduces log lines to a template ID plus parameters |
| **Entity** | The unit a behavioural window is built around: host, IP, user, or service |
| **Flow record** | One summarised network conversation: 5-tuple, protocol, packet/byte counts, duration, flags |
| **Late fusion** | Combining independently produced model scores, as opposed to a single jointly trained model |
| **PR-AUC** | Area under the precision-recall curve; the meaningful area metric under heavy class imbalance |
| **PSI** | Population Stability Index — a drift measure comparing feature distributions between training and live data; > 0.25 flags drift |
| **Shadow mode** | A promoted model scores live traffic without publishing alerts, so its distribution can be compared before it owns alerts |
| **Temporal split** | Train/valid/test split by timestamp, so the test period is strictly later than training |
| **Triage loop** | The analyst workflow: open alert → read evidence → set verdict → next alert |
| **Verdict** | An analyst's judgement on an alert: `true_positive`, `false_positive`, or `benign` |
| **Window** | A fixed-length sequence of flows (50) or log lines (200) for one entity, scored as a unit |

## Environment and setup

**Nothing to run yet.** When S0 lands, the intended shape is:

```bash
docker compose -f docker/docker-compose.yml up     # postgres, redis, kafka,
                                                   # elasticsearch, backend,
                                                   # ml-service, dashboard
python scripts/fetch_datasets.py --verify          # datasets → data/raw/ (gitignored)
```

Verified toolchain in the dev sandbox: **Python 3.11.2**, **Node v22.22.3 / npm 10.9.8**. **Docker is not installed here**, so T-005 (compose) can be written but not executed in this workspace. Remaining versions to be pinned in T-007.

**Sandbox note (corrected 2026-10-02).** Outbound network from this workspace is **allowlisted, not blocked**. Measured with `curl -o /dev/null -w %{http_code}`: `pypi.org/simple/` → 200, `registry.npmjs.org/` → 200, `github.com` → 200, but `research.unsw.edu.au` → 000, `www.unb.ca` → 000, `huggingface.co` → 000 and `raw.githubusercontent.com` → 000.

**Consequence:** Python and npm dependencies install normally here, so the backend, ml-service, and dashboard can be built and tested in the sandbox. **The datasets cannot be fetched here** — UNSW-NB15 and CIC-IDS2017 must be downloaded from a machine with general internet access, and their checksums recorded in the table above per R-41. An earlier note in this section claimed outbound network was unavailable entirely; that was wrong and is superseded by these measurements.

## Working norms

The rules are in [rules.md](rules.md). The three that get broken most often in projects like this, so they are written here too:

1. **Never fabricate a number.** Every metric traces to a recorded run (R-74). "Expected" and "approximately" are not measurements.
2. **Never hide a failure.** A component that cannot do its job says so in the response and the UI (R-06, R-70). A blank panel where data failed to arrive is a defect.
3. **Never leak the future into the past.** Temporal, entity-disjoint splits, scalers fit on train only (R-60…R-62). This is the single most common way an intrusion-detection project lies to itself.

## Next actions

| # | Action | Task | When |
|---|---|---|---|
| 1 | Confirm Q-01, Q-03, and Q-05 owners and dates | — | Before 2026-10-05 |
| 2 | ~~Commit the six documents as the baseline~~ — done, `3d74000` | — | Complete |
| 3 | ~~Begin S0: scaffolding, CI, compose, docs~~ — done except T-005 execution and `k8s/` | T-001…T-010 | Complete |
| 4 | Run the compose stack on a host with a Docker daemon and close T-005 | T-005 | When Docker is available |
| 5 | Fetch datasets and record real checksums — blocked, hosts unreachable here | T-101, T-102 | S1 |
| 6 | ~~Build `features@1` extraction against synthetic `flow@1` records~~ — done, 23 features, hash-pinned | T-107 | Complete |
| 7 | ~~Settle Q-06 and build windowing~~ — done, closed by D-013 | T-108 | Complete |
| 8 | Build the temporal + entity-disjoint split utility, then the leakage audit | T-109, T-111 | Next |
| 9 | Fill the measurement ledger with the first measured baselines | T-110 | End of S1 |

## Change log

| Date | Version | Change |
|---|---|---|
| 2026-10-02 | 0.1 | Created during the repository reset. Recorded the reset (487 files removed, recoverable from `60e9adf`), ten decisions, four data sources, five open questions, and an empty measurement ledger. |
| 2026-10-03 | 0.2 | Sprint S1 opened: T-106 shipped the canonical `flow@1` / `log@1` records and a seven-scenario synthetic generator. Added D-011 (where the telemetry schemas live), refreshed the current-state and data-source tables, and re-marked the completed next actions. |
| 2026-10-03 | 0.3 | T-107 shipped `features@1` (23 features, hash-pinned). Added D-012 and Q-06, and corrected `architecture.md` §7.1 from 24 to 23 features. Two defects found and fixed while building it: three scenario builders emitted out-of-order timelines, and `backend[dev]` never declared `import-linter` or `pytest-cov` even though CI runs both. |
| 2026-10-03 | 0.4 | T-108 shipped sliding windowing with count and inactivity triggers. D-013 closes Q-06: the window key is a parameter, source by default and destination for volumetric families. `extract_flow_window` now takes the same key so destination-keyed windows are scorable. |
