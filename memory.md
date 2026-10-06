# Memory — AI-Enhanced Cybersecurity Threat Detector (AEGIS)

| | |
|---|---|
| **Document** | Persistent project context, decisions, and ledger |
| **Version** | 0.1 |
| **Last updated** | 2026-10-05 (Sunday) |
| **Purpose** | The document a new engineer — or you in three months — reads first |
| **Related** | [prd.md](prd.md) · [architecture.md](architecture.md) · [rules.md](rules.md) · [design.md](design.md) · [task.md](task.md) · [api-reference.md](api-reference.md) |

---

## What this project is

AEGIS uses **transformer models** over **network flow records** and **system logs** to detect anomalies and predict cybersecurity threats before they become confirmed incidents. It is a detection and triage platform: telemetry in, ranked and explained alerts out, with an analyst loop that closes in under a minute.

- Scope, threat families, and requirements: [prd.md](prd.md)
- System and model design: [architecture.md](architecture.md)
- How we write code: [rules.md](rules.md)
- How it looks and behaves: [design.md](design.md)
- What we build and when: [task.md](task.md)

**One-line pitch.** Signature-based detection misses novel behaviour; AEGIS learns what "normal" looks like per entity and flags the deviation, with evidence attached.

## Current state (as of 2026-10-05)

| Aspect | State |
|---|---|
| Repository | Six planning documents plus the S0–S2 and E3 code (base `04aeb71`; `415a5b1` re-established the E3 work after the 2026-10-05 environment reset, with T-312 at `87beed9`, T-313 at `69b6b5e` and T-314 at `0814cc7` — see below) |
| Source code | `backend/` — the T-301 schema and migration, auth (T-302/T-303), ingest (T-304), alert query (T-305), Kafka producer and lag (T-306), scoring worker (T-307), the correlator (T-308), analyst verdicts (T-309), the alert stream (T-310), outbound webhooks (T-311), the append-only audit trail (T-312), scoped API keys (T-313), retention with GDPR erasure (T-314), the model ops endpoints (T-315), the request limits (T-316), the metrics and traces (T-317), the structured logging (T-318), the in-process golden pipeline (T-319), the generated API reference (T-320), the typed score columns with the checked severity (T-321), the weekly threshold recalibration (T-322), the declared PostgreSQL driver (T-323), and the closed design-token layer (T-401, the first E4 task). `ml-service/` — the data layer, `FlowNet`/`LogNet`, late fusion, occlusion explanations, thresholds, drift, shadow harness, registry, training pipeline. `dashboard/` — React shell only; E4 has not started |
| Tests | **1825 passing, 29 skipped** — 1227 backend (13 need a live PostgreSQL), 531 ml-service (16 need torch), 67 dashboard. Coverage is above the R-80 gate; the exact figure moves every task and is whatever the last `check_all.sh` printed |
| Checks green | `./scripts/check_all.sh` — **26 checks, 0 failed** (measured 2026-10-05): ruff, black, mypy strict, bandit, import-linter, pytest ×2, coverage, tsc, eslint, stylelint, vitest, vite build, doc integrity, the API reference drift check, compose and k8s consistency, and the 14 pre-commit hooks. Checks that exist to catch a class of defect were injection-proved before being trusted |
| Dependencies | Python: `pip install -e "backend[dev]" -e "ml-service[dev]" -r requirements-dev.txt`, then `(cd dashboard && npm ci)`. `torch` is the `ml-service[training]` extra and the ONNX stack is `[onnx]`; both are optional and neither is installed here |
| Datasets | CIC-IDS2017 (225,745 rows) and a 49-column UNSW-NB15 sample (10,000 rows) are on disk, hash-verified by `scripts/fetch_datasets.py`. Synthetic data still generates on demand into the gitignored `data/` |
| Models | **`FlowNet` trained** (1,163,076 parameters); `LogNet` built and tested but has no held-out metric of its own yet (Q-07). The only defensible FlowNet numbers so far are benign-only training at ROC-AUC 0.8053 / PR-AUC 0.7772; the 1.0000 figure comes from a leaky split (D-015, D-016). R-66 transfer recall **0.7955** at a target-blind threshold (D-022) |
| Branch | `arena/01a10bf7-ai-enhanced-cybersecurity-thre`, based on `04aeb71` |
| Next work | E3 is closed and **E4 has started**: T-401 (the design tokens) is done and **T-402** (the UI primitives) is next, which needs nothing new. **T-409/T-410** were unblocked by T-315 and **T-506** follows T-311; E5 is untouched. One follow-on was filed by T-323 rather than fixed: the database session D-030 is missing will need `sqlalchemy[asyncio]` when it is wired, because R-18's request path may not use the synchronous engine Alembic uses — the driver itself is declared and the sync half is proven. Docker remains unavailable here, so T-005 and the k8s apply are still unverified, and T-301's migration half was verified once against a sandbox PostgreSQL rather than in CI (D-055) — each says so in [task.md](task.md) |

**E0 and E1 are DONE** except T-005, which is written and has never been executed. **E2 is DONE** except the release gate Q-07 still owes. **E3 is DONE through T-323**; every E3 task is closed. **E4 is started** — T-401 is done, T-402 onwards are `TODO` — and **E5 is untouched** — everything past E3 is `TODO` in [task.md](task.md), which holds per-task status.

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

**Second reset, 2026-10-05 — the environment, not the tree.** Between sessions the
sandbox was recreated: `.venv` and `dashboard/node_modules` were gone, and `.git`
was the original shallow clone at `04aeb71` again. **The working tree came back
intact** — every E3 file, test and documentation edit present and unchanged — but
the local commits were not: `a2c29e1` (T-308), `b6975f4` (T-309), `c6eacd4` (T-310)
and `34dc7ff` (T-311) do not exist in this clone and never reached the remote, which
the branch has no upstream for. One recovery commit, **`415a5b1`**, re-establishes
their content in history. **What that costs, stated rather than glossed:** the
per-task commit boundaries for T-308…T-311 are gone — one commit now stands in for
four — and the hashes named in the change-log entries below no longer name anything
in this clone. Individual file contents are unaffected, and every recorded
measurement is a measurement of file contents, so the measurements stand. The tree
was **re-verified rather than assumed green** after the reset: the Python
environment was rebuilt from `backend/pyproject.toml` — which incidentally proves
`cryptography>=44` is declared rather than hand-installed — the dashboard
dependencies from `package.json`, and `./scripts/check_all.sh` re-run to 25/0 before
T-312 started.

**Why (first reset).** The previous tree had grown into a very broad security platform — endpoint modules included CSPM, ZTNA, ITDR, deception, SBOM, SCIM, SOC-TV, and digital-risk protection. That breadth had outrun the project's actual objective: transformer-based anomaly detection over network traffic and system logs. Restarting from the PRD keeps the scope honest and matches [prd.md](prd.md#3-scope).

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

### D-009 · Temporal, entity-disjoint evaluation only — ACCEPTED (2026-10-02), amended by D-015 (2026-10-04)
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

### D-014 · When both leakage invariants cannot hold, the split refuses rather than leaking — ACCEPTED (2026-10-03)
**Context.** T-109 must satisfy R-60 (test strictly later than train) and R-61 (no entity in two folds) at once. They conflict: a host active on both sides of the time cut cannot stay whole in either fold without breaking one of them. Building the fixture showed the conflict is not academic — on a stream where every host is active end to end, *every* host spans the cut.
**Decision.** Windows whose entity appears on both sides of a cut stay in the early fold, and their late windows are **dropped and counted**. If a cut leaves either side empty, `split_windows` raises instead of returning a fold that would score as zero or leak. The test cut is made first, then the validation cut is made within what remains, so all three folds are pairwise entity-disjoint and strictly ordered in time.
**Consequences.** Evaluation is only possible on data with **entity churn** — hosts appearing and disappearing over time. Where a capture has none, the honest options are to relax R-61 for that experiment and say so, or to synthesise churn. The utility cannot decide that trade-off, so it surfaces the dropped count and fails loudly rather than picking silently. This will constrain T-110 baselines on real captures and is the reason `Split.audit()` exists.

### D-015 · R-61 is a policy that is measured, not an axiom; R-60 stays unconditional — ACCEPTED (2026-10-04)
**Context.** D-014 assumed a capture lacking entity *churn* would be the problem. Two capture days of CIC-IDS2017 disproved it: 4,600 entities in train, ample churn, yet every entity-disjoint temporal cut from 0.5 to 0.9 produced a late fold that was 100% normal. The cause is that the **attack sources are persistent** — a reflected DDoS from internet-wide servers that also carry benign traffic all capture, plus a web-attack host present throughout. A persistent entity always appears before the cut, so entity-disjointness assigns it to the earlier fold by construction. No entity-disjoint temporal split can hold out attack traffic on this dataset.
**Decision.** R-60 (test strictly later than train) has **no off switch**. R-61 becomes a split policy: `split_windows(..., entity_disjoint=)` defaults to `True`, and `run_baselines.py --split-policy` exposes `entity-disjoint` (default, the only policy a released model may be gated on) and `temporal-only` (benchmark comparability). Relaxing R-61 never silences the audit — `Split.audit()` now reports `shared_train_test_entities` and its valid-fold counterparts as **counts**, so the leakage is measured and carried in the run log alongside the metric it inflates.
**Consequences.** Numbers from a `temporal-only` run are labelled benchmark-comparable in the run log and on stdout, and are not release-gate evidence; T-203 and T-208 inherit this. Two costs follow from measuring rather than assuming: a headline metric must always be read with its fold's base rate, and `best_f1` is now part of every baseline report, because the fixed 0.5 operating point is meaningless on a fold whose positive rate differs from training's by an order of magnitude. The honest remaining gap — that no reachable corpus has ephemeral attack sources, so no released model here has yet been gated on a genuinely entity-disjoint holdout — is recorded as **Q-07** rather than papered over by these numbers.

### D-016 · Entity-disjoint evaluation is impossible on CIC-IDS2017 at any window key; the gate must move to attack-family holdout — ACCEPTED (2026-10-04)
**Context.** D-015 left Q-07 open: where do release-gate numbers come from, if no entity-disjoint temporal split can hold out attack traffic? The obvious candidate is to keep R-61 and relax R-60 — partition whole entities by a stable hash, so the model is scored on entities it has never seen. That is implemented (`group_split`, `--split-policy entity-only`) and tested. **It does not work on this corpus, and the measurement says why.**

On the Friday capture, of 6,415 source-keyed windows and 2,066 entities, there are 2,562 attack windows — and they belong to **2 entities**. `172.16.0.1` alone accounts for **2,561** of them. Keying on destination instead does not diversify anything; it mirrors the concentration onto the victim, `192.168.10.50` with 2,566 of 2,567. The DDoS is a single source→destination pair.

**Decision.** With one attack entity, entity disjointness is not a holdout — it is a coin flip. Whichever fold that entity hashes into holds 100 % of the attack traffic, so an entity-disjoint test fold is either all-attack or all-normal. Measured: the `entity-only` split put `172.16.0.1` in train and produced a test fold of **44,595 rows with 0 positives**. `run_baselines.py` refused it, correctly. So R-61 cannot be satisfied usefully on this capture at either window key, and `temporal-only` remains the only policy that produces a two-class fold here.

**This retracts part of D-015.** D-015 explained the failure as *persistent attack sources* — a reflected DDoS from internet-wide servers that also carry benign traffic. That was an inference from the entity count, not a measurement, and it is wrong: the cause is attack-entity **concentration**, not persistence. The 4,600 entities in train are benign; the attack was never spread across them.

**Consequences.** `group_split` stays: it is the correct primitive for a corpus whose attacks span many entities, it is deterministic by SHA-256 rather than a salted hash, and its six tests pin that it keeps every entity whole. What changes is the release gate. For this corpus the only defensible generalisation test is a **family-level holdout** — hold out an entire attack class and test detection of a family the model never trained on. The two-day capture supports exactly one such split (Thursday web attacks against Friday DDoS), which is thin but real, and it answers a more useful question than either leakage invariant does. Until that exists, every number in the ledger stays benchmark-comparable rather than release-gate evidence.

### D-017 · Synthetic data cannot produce a two-class held-out fold, so it is not a valid substrate for any metric — ACCEPTED (2026-10-04)

**Context.** T-201's acceptance criterion needs an end-to-end training run. The obvious substrate is the synthetic generator, which needs no download. Every attempt to evaluate on it aborted with `ROC-AUC needs both classes`.

**Measurement.** `generate_dataset(per_scenario=1500, seed=20260114)` yields 10,500 flows whose per-scenario time spans differ by four orders of magnitude — DoS 0–7 s, Reconnaissance 0–30 s, normal 0–2,173 s, BruteForce 0–2,248 s, Exfiltration to 48,937 s, Beaconing to 89,940 s, InsiderThreat 64,828–147,042 s — and whose per-scenario source counts differ by three: DoS uses 1,476 distinct sources, normal uses 4, and five scenarios use 1 each. Windowed by source that is **1,643 attack windows against 15 benign**, 1% benign. Both split policies therefore degenerate: a temporal split puts every benign class inside the first 1.5% of the timeline, and an entity-only split has only four benign entities to place. Neither splitter is at fault.

**Two earlier explanations of this failure are retracted here.** That "each scenario is a contiguous time block" — they all start at the same epoch and overlap heavily. And that "a temporal split makes the test fold single-class" — it is single-class at *every* policy, including entity-only, which was measured returning 302 positives and 0 negatives.

**Decision.** The generator stays as it is. Per-scenario cadence is the point of it: a DDoS from 1,476 sources against benign traffic from 4 hosts is exactly the shape the features exist to catch, and compressing every scenario into one window would destroy the inter-arrival signal. What changes is the claim made about it. Synthetic data exercises pipelines; it does not measure generalisation. `scripts/train_flownet.py` takes the same `--file` / `--dataset` / `--format` interface as `run_baselines.py` so the acceptance run uses the fetched benchmark, and `--split-policy` mirrors that script's three policies rather than inventing a fourth.

**Consequence.** Any future task proposing to validate on synthetic data must first show the target fold contains both classes. That check belongs in the task, not in a reviewer's head.

### D-018 · A family holdout is built, but UNSW-NB15 windows mix families too heavily for a clean one; the defensible setting is benign-only training — ACCEPTED (2026-10-04)

**Context.** D-016 moved the release gate to an attack-family holdout and left it unbuilt. `family_split` now exists in `aegis_ml/data/splits.py`, with nine tests: every window containing a held-out family goes to test whatever entity it belongs to, benign negatives are drawn from entities training never saw, and nothing held out can reach training.

**Measurement on the UNSW-NB15 official sample** (9,756 parsed rows, 212 windows, all nine families present with source IPs — the full 175,341-row CSV is the 45-column variant with no `srcip`/`dstip` at all, so it cannot support any entity-keyed split):

| holdout | train | test | families still in TRAIN that also appear in TEST |
|---|---|---|---|
| Exploits | 103 | 55 | Backdoor, Fuzzers, Generic, Reconnaissance, Shellcode |
| Fuzzers | 103 | 55 | Backdoor, Exploits, Generic, Reconnaissance |
| Generic | 95 | 63 | **none** |

**So no single-family holdout on this corpus is clean.** UNSW windows mix up to seven families, so withholding Exploits still trains on five of the eight families present in the test fold, and the 0.9748 ROC-AUC measured that way is optimistic rather than a generalisation claim. Withholding Generic does the opposite: Generic appears in nearly every attack window, so training is left with **no attack traffic at all**.

**Decision.** That second configuration is adopted as the defensible setting, reframed honestly: it is not a family holdout but **train on benign traffic, score attacks never seen** — which is exactly what the reconstruction head is for, and the only evaluation this corpus supports without leakage. Its measured result is **ROC-AUC 0.8053, PR-AUC 0.7772, best F1 0.6304 at threshold 0.00** (`data/runs/flownet_unsw_benign_only.json`). The threshold sitting at the floor of the sweep is itself evidence: the scores barely separate, which is what 0.80 looks like from the inside.

**A defect found while building this, and fixed.** `_window_label` returns `None` whenever a window's member flows disagree, which is correct for multi-class training and wrong for a binary detector: a window holding Fuzzers and Generic traffic is ambiguous as a *family* and unambiguous as an *attack*. `design_matrix` is already binary, so those rows were dropped as unlabelled. On the UNSW sample that silently discarded **all 21 attack windows** in the test fold and kept 34 benign ones — and it is invisible on a single-family capture like CIC-IDS2017 Friday, which is why it survived until now. `train_flownet.py` now relabels rows to the binary target; `features@1` and T-111's mixed-window count are untouched, because that signal is still worth having.

**Consequence.** The D-016 gate is narrowed, not closed. 0.8053 is the first number in the ledger that is not inflated by seeing the test family, and it is roughly 0.19 below the leaky temporal figure. A clean single-family holdout needs a corpus whose attacks do not co-occur in the same windows, which none of the reachable datasets provide.

### D-019 · `LogNet` uses a from-scratch transformer over mined template IDs, not a pretrained DistilBERT — ACCEPTED (2026-10-04), closes Q-01

**Context.** Q-01 blocked T-204: should `LogNet` run a frozen pretrained DistilBERT over raw log messages, or a from-scratch transformer over Drain-mined template IDs?

**Decision: from-scratch over template IDs.** Four reasons, in the order they decided it.

1. **The input barely contains language.** T-104 measured **103 templates over 2,000 BGL lines at 0.9530 purity**. A window of log lines reduces to a sequence drawn from roughly a hundred discrete tokens. English-language pretraining is knowledge about natural text; machine-generated telemetry has already been collapsed into IDs, so there is almost nothing for it to transfer.
2. **The miner already exists.** `aegis_ml/data/log_parsers.py` ships a tested `TemplateMiner`. The template path is most of the way built; the DistilBERT path would add a multi-gigabyte `transformers` dependency and a model download at inference to reach the same token sequence.
3. **NFR-05 caps window scoring at p95 150 ms on 4 vCPU.** A DistilBERT pass over a 200-line log window cannot meet that on CPU. A six-layer encoder over 200 integer tokens can.
4. **A self-contained model is easier to keep deterministic (R-67) and easier to reason about under the data-privacy constraint** — nothing is fetched at inference, and the container does not grow by a pretrained checkpoint.

**What this gives up, stated plainly.** Novel *wording* is invisible to this model: a message that has never been seen becomes an unknown-template token rather than something the encoder can interpret from its words. That is a real loss of coverage for zero-day log formats, and it is the reason `template_known` is a feature at all — so an unseen template is at least visible as unseen. If a future corpus has genuinely diverse free-text logs, this decision should be revisited; on LogHub-style corpora it is the right trade.

**Consequence for T-204.** The acceptance criterion becomes mining stability across re-runs on the same corpus, which the existing miner can be tested for directly, plus a model whose losses need no labels: masked-template prediction and a hypersphere objective. Both are self-supervised, which matters because unlabelled logs are the common case in production.

### D-020 · `explain()` uses occlusion attribution, not attention rollout and not the `shap` package — ACCEPTED (2026-10-04)

**Context.** T-206 asks for attention rollout plus SHAP on flow features. Neither is used. This is a deviation from the task text, so it is recorded as a decision rather than left in a code comment.

**Why not attention rollout.** It needs the per-layer attention matrices. Measured, not assumed: `nn.TransformerEncoderLayer.forward` does not accept or forward `need_weights`, and `nn.TransformerEncoder.forward` exposes no parameter that would request them. Reaching the weights means re-implementing the encoder block, which puts a second copy of the model's arithmetic beside the first — and the two will drift, at which point the explanation describes a model nobody is running.

**Why not the `shap` package.** It brings numpy, scipy and scikit-learn to compute, for a 35-column input, what occlusion computes directly. The dependency cost is real and the marginal method is not.

**Decision.** Attribution is **occlusion**: replace one feature with its baseline value, re-score, and read the difference as that feature's contribution. This is an interventional attribution over a single-feature coalition, in the same family as SHAP, and it measures the quantity the alert is actually about — the score — rather than a proxy for it.

**What this gives up.** Occlusion misses interaction effects that a full Shapley estimate would split between two features, and it costs one forward pass per feature per window. On 35 columns and a model this size that is affordable at scoring time; if the feature count grows by an order of magnitude it will not be, and grouped or gradient-based attribution should replace it then.

**What did not change.** R-70's contract is enforced exactly as written: at least three reasons naming feature, value and baseline, or an explicit `explanation_unavailable`. A malformed window returns the marker rather than raising, because an alert that crashes its own explanation is an alert that disappears.

### D-021 · SUPERSEDED by D-022 · Transfer from UNSW-NB15 to CIC-IDS2017 fails R-66 — the numbers here are real, **the diagnosis is wrong**

> **Correction.** Everything measured below is accurate. The *explanation* I gave for
> it is not, and D-022 replaces it. I attributed the zero recall to categorical
> vocabulary collapse and to numeric standardisation across captures, and I wrote
> that down without measuring the thing that actually caused it: the training fold
> had **zero positive examples**, so the supervised head being scored could only
> learn to emit a constant. Both causes I named are real and both do hurt transfer,
> but neither explains a score distribution that sits entirely below 0.10. Read the
> measurements below as what happened, and read D-022 for why.

**What was run.** `scripts/transfer_eval.py`: FlowNet trained on the UNSW-NB15 official sample (95 training windows, family-holdout split, leakage audit clean), then scored against the whole of CIC-IDS2017 Friday (6,415 windows, 2,562 attack) **with the source preprocessor and no refit**. Refitting on the target would leak (R-62) and would also hide the very shift this task measures.

**Result.**

| threshold | recall | precision | F1 |
|---|---|---|---|
| 0.00 | 1.0000 | 0.3994 | 0.5708 (fpr 1.0) |
| 0.05 | 0.0679 | 0.9355 | 0.1266 |
| 0.50 (source operating point) | **0.0000** | 0.0000 | 0.0000 |
| ≥ 0.10 | 0.0000 | — | — |

**ROC-AUC 0.9048.** So the model *ranks* CIC attacks above CIC benign traffic — the representation transfers. What does not transfer is the **scale**: the entire target score distribution sits below 0.10, so the threshold fitted on the source catches nothing at all.

**Diagnosis — WRONG, see D-022.** I wrote that a threshold at 0.05 recovering only 6.8% recall showed the model "genuinely fails to flag most CIC DDoS windows", and attributed it to CIC's `state` and `service` categoricals collapsing into the reserved unknown column and to numerics being standardised with UNSW statistics. The mechanism was simpler: the scoring head had been trained on a fold containing no positives at all.

**Decision.** The R-66 gate stands and fires: `transfer_eval.py` exits non-zero and the release is blocked. This is recorded as a measured negative result rather than tuned away, because a transfer number that reaches 0.70 by moving the threshold is not a transfer result.

**What would have to change — also superseded.** I proposed per-target threshold calibration and a capture-stable feature layer. Neither was necessary; see D-022.

### D-022 · Transfer is a property of which head is scored, not of the threshold — R-66 now passes at recall 0.7955 (2026-10-05)

**The actual cause, measured.** `family_split(holdout=["Generic"])` puts every attack family in the held-out fold by construction, so the training fold is benign-only — measured directly as `train: n=95, record families={'normal': 4303}, POSITIVES=0`. FlowNet carries two heads, and the first version of `transfer_eval.py` scored the wrong one. The supervised `anomaly_head` is trained by binary cross-entropy; with no positive examples it can only converge to a constant near zero, which is precisely why every CIC score fell below 0.10. The zero recall was a property of the scoring head, not of the model's ability to transfer.

**The fix.** Score the **reconstruction** head instead: `per_window_reconstruction_error`, added next to the existing `reconstruction_error` in `flownet.py`. It is trained unsupervised to reproduce benign traffic, needs no labels, and is what makes FlowNet an anomaly detector rather than a classifier — so it is the signal that can cross a capture boundary. Both functions are asserted to agree in `test_reconstruction_error.py`; a scoring function that disagrees with the loss would train on one notion of anomalous and report another.

**The operating point stays target-blind.** A threshold chosen by watching target recall is not evidence about the target, so the cut comes from T-207's `fit_threshold` over the **source's** benign validation scores at the default 0.99 quantile, then applies unchanged. Fitted value **0.3622** from 54 source windows; the target contributes nothing to it.

**Result, same split and same training run as D-021.**

| signal | threshold (target-blind) | recall | precision | ROC-AUC | R-66 |
|---|---|---|---|---|---|
| supervised (D-021) | — | 0.1725 | 0.9546 | 0.9048 | BLOCKS |
| **reconstruction** | 0.3622 | **0.7955** | 0.5904 | 0.7464 | **PASSES** |

**The lesson that generalises, and it cost me a wrong write-up.** The supervised head had the *higher* AUC — 0.9048 against 0.7464 — and the far worse recall. A near-constant head still ranks slightly, so AUC rewarded the broken signal while recall exposed it. **ROC-AUC alone cannot detect a degenerate detector.** Any acceptance criterion that leans on AUC should also report recall at the actual operating point, which is what R-66 does and why R-66 caught this when AUC did not.

**What still does not transfer.** Precision is 0.5904 against a 40% attack base rate, so the detector is barely better than chance at saying which flagged window is really an attack. Recall — the property R-66 gates on — clears the floor comfortably; precision is the open problem, and the collapsing categoricals and cross-capture numeric scale from D-021 remain real contributors to it.

### D-023 · Inference is byte-deterministic and 6.6x inside the latency budget; the 4 vCPU half of NFR-01 is **not** verified here (2026-10-05)

`scripts/inference_benchmark.py` checks both halves of T-209.

**Determinism (R-67) passes on all four checks**, and the four are not redundant. Repeated passes byte-identical; a *second model instance* built from the same seed produces the same bytes, which is what separates "the seed determines the weights" from "the weights happened to stay in memory"; the torch RNG state is **unchanged** by a forward pass, so the scoring path consumes no randomness; and the weights are unmodified. Comparison is over the raw storage bytes of both heads — byte equality, not approximate equality, because a 1e-8 drift is invisible in a metric and still means the score cannot be reproduced in an audit.

**Latency.** p95 **22.590 ms** per window (1×50×23) over 300 passes with 20 warmups discarded, against NFR-01's 150 ms budget. p50 19.104, p99 27.548, slowest 36.849.

**The honest gap.** NFR-01 specifies 4 vCPU and this sandbox has **2**. The script reports the vCPU count it ran on and refuses to label the number a 4 vCPU result when it is not, writing `matches_nfr01_reference: false` into the artifact. What can be said: the measurement was taken with **one** torch thread, which is a stricter configuration than 4 vCPU would give, so the budget is met with room to spare on any machine that has at least as much single-core performance — but that is an argument, not a measurement on the specified machine.

**One measured oddity worth keeping.** Two torch threads are *slower* than one on a window this small: p95 28.611 ms at 2 threads against 26.609 ms at 1, with the slowest pass jumping to 78.375 ms. Thread pool coordination costs more than the matrix multiplies save, so the scoring path should pin a single thread rather than inherit a parallel default.

### D-024 · The ONNX fallback is real but buys 0.088 ms — recorded as preparedness, not as a win (2026-10-05)

`ml-service/aegis_ml/serving/onnx_export.py` plus `scripts/onnx_export.py`.

**Agreement.** On a fixed 8×50×23 batch from a seeded generator, the exported graph matches the PyTorch model to max abs Δ **9.537e-07** on `reconstruction` and **1.341e-07** on `anomaly_logits`, against T-210's 1e-4 tolerance — roughly 100× inside it. Artifact 1,387,045 bytes. Unlike the latency figure this one is reproducible run to run, which is exactly why it is the criterion that gates the build while the latency figure is only recorded.

**Latency delta — and a correction to the first number written here.** The first run reported −0.088 ms and I described it as "faster in the fourth significant figure". That was single-round noise, not a measurement. Three further single-round runs of the same binary on the same input gave **−1.123, +2.311 and −2.257 ms** — the sign flips. A single-round p95 delta on a shared 2 vCPU box mostly measures the machine, so the script now re-benchmarks both backends over `--rounds` (default 5), interleaving them so they see the same conditions, and reports the spread.

Over 5 rounds × 200 passes: torch p95 median **19.120 ms** (range 18.254–19.493), ONNX p95 median **19.425 ms** (range 18.025–21.671). Delta median **+1.172 ms**, range −0.975 to +2.224, **ONNX faster in 2 of 5 rounds**. The script reports the sign as inconsistent and states the two backends are the same speed at this resolution.

That is the answer to prd.md's "is the latency fallback worth landing early?": there is no speedup to land, and with T-209 at p95 22.590 ms against a 150 ms budget there is no latency problem for this path to solve. The value of T-210 is having a verified graph ready, not a faster one.

**Two exporter facts found by measurement, not chosen by taste.**
* `OPSET_VERSION = 18`, because torch 2.14 refuses to emit 17 and then fails its own automatic downgrade conversion (`Assertion node->hasAttribute(kaxes) failed`), leaving a graph that will not load.
* `dynamo=False` is **required**. The default exporter routes through `torch.export`, which specialises the batch dimension: the graph loads and scores a batch of one, then fails at any other size on a Reshape node with the batch count baked in as a constant (`input_shape:{50,8,176}, requested shape:{50,176}`). The TorchScript exporter keeps the axis dynamic. A graph that only runs at one batch size is not a serving path.

**Why the fallback is an extra and never a dependency.** The module imports cleanly with neither torch nor ONNX installed and `onnx_available()` probes with `importlib.util.find_spec` rather than importing. `load_scorer` returns `(scorer, backend)` and the label is part of the contract, because "which backend scored this alert" is an audit question — a silent fallback would answer it wrongly. 13 of the 16 tests pass in a torch-free, ONNX-free interpreter, which is the environment the fallback exists for.

### D-025 · Per-feature PSI works, and it independently confirms D-022: 20 of 23 features drift between UNSW-NB15 and CIC-IDS2017 (2026-10-05)

`ml-service/aegis_ml/scoring/drift.py` (the computation) and `scripts/drift_report.py` (the measurement). FR-32's criterion — PSI matching a hand-computed reference case — is tested by doing the arithmetic in the test itself: reference proportions (0.5, 0.3, 0.2) against actual (0.4, 0.4, 0.2) gives `−0.1·ln(0.8) + 0.1·ln(4/3) = 0.051082562`, asserted to `rel=1e-12`. A test that built its own expected value from the function under test would pass against any consistent implementation, including a wrong one.

**Three design points, each of which changes the number.**
* **Bin edges come from the reference distribution alone.** Using incoming data to place bins would make PSI incomparable between two windows — the metric would move because the partition moved, not because the traffic did. This is R-62 applied to a different artifact.
* **Empty bins are floored at `EPSILON = 1e-6`, not skipped.** Skipping hides exactly the "this traffic appeared from nowhere" case drift monitoring exists to catch. The cost is that PSI is bounded above instead of able to reach infinity, and a test pins that bound rather than leaving it implicit.
* **Categorical features are never binned.** A category is already a partition; re-binning an encoded id would invent an ordering that was never there.

**The measurement, and why it matters beyond this task.** UNSW-NB15 as reference, CIC-IDS2017 as incoming, 20,000 rows each:

| feature | PSI | band |
|---|---|---|
| `state` | **26.6670** | significant |
| `direction` | 9.0923 | significant |
| `dst_ip_count` | 6.7233 | significant |
| `inter_arrival_std` | 5.6420 | significant |
| `service` | 3.9367 | significant |
| … 15 more over threshold | 0.53–5.26 | significant |
| `fin` | 0.0866 | stable |
| `protocol` | 0.0143 | stable |
| `rst` | 0.0011 | stable |

**20 of 23 features exceed 0.25.** The three that do not drift are the three whose meaning is identical in both captures.

The top three drifters are `state`, `direction` and `service` — and `state` and `service` are precisely the two categoricals that D-022 identified as collapsing into the reserved unknown column and carrying no information across the capture boundary. **A drift monitor written after the fact, from a different measurement, names the same features.** That is independent corroboration of D-022 rather than a restatement of it, and it is the strongest evidence yet that the transfer problem is a feature-representation problem rather than a modelling one.

**Drift is a signal, not a failure**, so the CLI exits 0 when drift is found. A monitor that fails the build every time traffic legitimately changes gets switched off. `--fail-on-drift` turns it into a gate for releases that must not ship against a shifted distribution. Every feature is published, drifted or not: a gauge that only appears on failure cannot show that a feature has been stable for weeks, and "no news" would be indistinguishable from "not measured". The metric name `aegis_drift_psi{feature}` is fixed by architecture.md §12, not chosen here.

### D-026 · The registry refuses `latest` and refuses to resurrect a retired model — both as distinct errors, not as "not found" (2026-10-05)

T-212's two acceptance clauses, enforced in `registry/model_registry.py`. R-68 states three prohibitions and the module enforces each rather than assuming it.

**`latest` is actively refused, not merely absent.** `get("latest")` raises `ForbiddenModelId`, not `ModelNotLoaded`. The distinction is the point: a missing id is a typo to correct, while a floating reference is a pattern the caller must stop using, and collapsing the two would tell an operator to check their spelling when they should be changing their code. `FORBIDDEN_MODEL_IDS` also covers `stable`, `current` and `newest`, matched case-insensitively after stripping, and the id is rejected at `ModelInfo` construction so it can never enter the registry in the first place.

**Retirement is terminal.** `promote()` on a retired model raises `InvalidTransition` naming the remedy — register the retrained artifact under a new id — not just the rule. The reason is structural: if a retired version could serve again, the set of versions that have ever taken traffic would not be append-only, and the history would stop being a history. `ALLOWED_TRANSITIONS` also has no path from `active` back to `staging`, so a version cannot be quietly re-qualified.

**Content addressing is required, not defaulted.** `ModelInfo.sha256` has no default and is validated as 64 lowercase hex characters. A model that cannot be identified cannot be rolled back to, so an absent address is refused at construction. This added a required field and broke six existing `ModelInfo(...)` call sites in `test_registry.py` and `test_health.py`; they were updated rather than the field being given a default, because a default would have satisfied the type checker while silently defeating R-68.

**Overwriting is refused, but redeploying is not.** Re-registering an id with different bytes raises `ImmutableArtifact` naming both content addresses; re-registering it with identical bytes is a no-op. A silent content change under a stable name is how a supply-chain substitution would hide, while an unchanged redeploy is ordinary. `verify(model_id, artifact)` is what makes storing the address useful at runtime: it reports whether the bytes on disk still match what was registered.

**One deliberate asymmetry.** Retiring an already-retired model is idempotent, while promoting a retired model raises. A cleanup pass that retires what is already retired is harmless; promoting a retired version is an attempt to reuse it, which is the thing R-68 forbids. My first test asserted the strict behaviour for both and was wrong — the code was right and the test was changed.

**Promotion and retirement happen in one call**, returning `PromotionResult{promoted, retired}`. Two calls would leave a window where either two models of a kind are active or none is, and T-315 requires rollback to be one call.

### D-027 · The shadow harness has no alert sink at all, because a flag would eventually be forgotten (2026-10-05)

T-213's criterion is that shadow scores are recorded *without producing alerts*. `aegis_ml/scoring/shadow.py` enforces that structurally: `ShadowHarness` takes no alert sink parameter and exposes no publishing method, so there is no route to an alert to guard.

The alternative is a `if shadow_mode: return` check. That has to be remembered at every call site, and it fails open the moment someone adds a new one — which is the realistic failure mode, not a hypothetical one. Two tests pin the structure itself: `inspect.signature(ShadowHarness.__init__)` contains no sink-like parameter, and no public method name contains `publish`/`alert`/`notify`/`emit`. A third puts a spy on a real alert sink in the same process and asserts it sees nothing after scoring three windows all above threshold.

**"Comparable" is measured with T-211's PSI**, active scores as the reference — the question is whether the new model looks like the incumbent, not whether it looks uniform. The threshold is the same 0.25, so a shadow model and a drifting feature are judged on one scale.

**What a low PSI does not establish, and the module says so.** Two models can agree on distribution while flagging entirely different windows. `ShadowComparison` therefore reports `disagreement_rate`, `shadow_alerts` and `active_alerts` alongside `psi`, and a test constructs the pathological case directly: every active score 0.9, every shadow score 0.1, giving a disagreement rate of 1.0 on distributions that are each internally consistent. A shadow model judged on PSI alone could swap one set of false positives for a different set of equal size and pass.

**`compare()` refuses rather than guessing.** With no active model it raises instead of calling the distribution comparable; with fewer than two paired scores it raises for the same reason. A comparison against nothing reported as "comparable" would be worse than no answer, because it would be believed.

### D-028 · A model card cannot be written with a typed-in number (T-214, R-74) (2026-10-05)

`aegis_ml/registry/model_card.py` plus `scripts/model_card.py`. R-74 treats a fabricated metric as an honesty defect, so the module makes the mistake unrepresentable rather than discouraged.

**`SourcedMetric` has no constructor that takes a number alone.** It requires `artifact` and `field` alongside the value, and `load_metric(artifact, name, *field_path)` opens the file and reads the value itself. The command-line interface follows: `--metric` takes `NAME=ARTIFACT:FIELD.PATH` and there is no way to pass a value. A plausible number typed from memory, copied from an earlier release, or rounded up — the three realistic ways R-74 gets broken — cannot be expressed.

**Citing something absent is a hard failure, in two distinguishable ways.** A field that is not in the artifact raises `MetricNotFound` naming both the citation and the file; a missing run raises `FileNotFoundError`. Verified end to end: `--metric "Fabricated F1=transfer.json:f1_score"` exits 1, as does citing a run that was never recorded. A non-numeric field is refused too, and `bool` is refused explicitly because `isinstance(True, int)` is `True` in Python and would otherwise slip through as a metric of value 1.

**A card with no limitations or no adversarial caveat is refused.** The caveat is mandatory because a detector card without one implies a robustness no trained classifier has. The default text is concrete — padding, rate-limiting below the detection window, splitting an attack across hosts — because "adversarial attacks may evade the model" tells an operator nothing they can act on.

**The card itself is generated at release, not committed.** It cites run artifacts under `data/runs/`, which are gitignored, so a committed card would eventually cite numbers no longer reproducible from anything in the repository — a slower version of the same defect R-74 targets. The generator and its tests are the committed artifact.

A real card was built from regenerated runs to check the path end to end: cross-dataset recall 0.795472, precision 0.590382, ROC-AUC 0.746354 (reproducing D-022 exactly), scoring p95 20.9889 ms, target attack windows 2562 — five metrics, all cited, four limitations.

### D-029 · The search has no test-split parameter, because a discipline note holds only until someone is in a hurry (T-215, R-71) (2026-10-05)

`aegis_ml/training/search.py`. R-71 forbids tuning on the test set, and the reason is arithmetic: searching ``k`` configurations and taking the best test score is the maximum of ``k`` noisy estimates, which is biased upward by construction with the bias growing in ``k``. Tuning on test does not just overfit the model, it overfits the *number* that goes in the release note.

**`search()` accepts a training fold and a validation fold and nothing else.** There is no parameter through which test data could be passed, and the omission is pinned by a test on `inspect.signature` rather than left to review. R-71's second half — the test split is touched once per release and recorded — is a separately named function, `final_test_evaluation`, so the one permitted look cannot be reached by accident while tuning.

**Selection defaults to ROC-AUC** because it is threshold-independent: selecting on F1 at a fixed cut would reward a configuration for landing on a fortunate threshold rather than for ranking better.

**Every trial logs the complete `TrainingConfig`**, not just the varied knobs. Two configurations differing only in a field nobody thought to record are indistinguishable afterwards, and a test asserts the logged config's key set equals `TrainingConfig.model_fields` so a new knob cannot go unlogged by default. Grid expansion is deterministic in key order, because an unreproducible search cannot be audited.

**A gap found and recorded rather than papered over.** `TrainingConfig` does not validate that `d_model` is divisible by `nhead`, so an incompatible pair passes grid expansion and fails later when the torch model is built. The test that was going to cover it now asserts the case that *is* caught (`dropout` ≥ 1.0) and documents the one that is not, since fixing it belongs to the config model rather than to the search.

**A bug mypy caught that my own tests had too.** Both `search` and `final_test_evaluation` were annotated `Sequence[Sequence[float]]` — flat rows — where `train` requires `Sequence[Sequence[Sequence[float]]]`, a sequence of windows. My first test folds made the identical mistake and failed with `TypeError: object of type 'float' has no len()` deep inside `train`. The signatures now use a named `Windows` alias, since mis-nesting three levels of `Sequence` produces an API that fails far from the call site.

### D-030 · R-34 is enforced by two layers, and the migration half of T-301 is **not** verified against a live PostgreSQL (2026-10-05)

`backend/app/db/{models,partitions,repository}.py` plus `backend/alembic/`.

**R-34 enforcement has two layers, because either alone has a hole.** `query_partitioned(table, time_range)` takes the range positionally so no call shape omits it, and `TimeRange` validates on construction — an inverted, empty, naive-timestamped, or >92-day range cannot exist. But a constructor cannot stop a caller assembling a `select()` by hand, so `assert_time_bounded` also walks the statement's FROM clause and WHERE predicates and refuses any partitioned table whose partition column is unconstrained. That second layer is the one that catches the case R-34 actually worries about: someone who knows the API and goes around it. A `select(func.count()).select_from(Alert)` is caught, which is the most likely unbounded scan in practice — and the reason the inspector uses `get_final_froms()` rather than `column_descriptions`, since the latter reports `None` for an aggregate.

**Two partitioning consequences shape the models.** A partitioned table's primary key must include the partition key, because Postgres enforces uniqueness per partition; `alerts` is `(id, created_at)` and `ingest_stats` `(id, window_start)`, so `id` is *not* globally unique on those two. And there is no default partition: a row outside every partition is rejected, which is loud, whereas a default partition accepts it silently until it is the largest table in the database and the retention model is gone.

**The partition DDL is pure functions, deliberately.** `app.db.partitions` builds the `CREATE/DROP` statements as strings, so they can be asserted against exactly even though they cannot be executed here. Partition names derive from the month covered, not from when they were created, so two runs of the same migration agree.

**What is not verified, stated plainly.** The acceptance clause "migration up and down both apply cleanly" **cannot be checked in this environment**: there is no PostgreSQL reachable (no `psql`, 5432 refused) and no container runtime, and declarative partitioning is PostgreSQL-only so SQLite cannot stand in. What *is* verified: every table compiles to `CREATE TABLE` for the postgres dialect, both partitioned tables emit `PARTITION BY RANGE`, the migration module imports with `upgrade`/`downgrade` present and `down_revision = None`, and the partition builders are unit-tested including December rollover and the half-open bound continuity. Applying it to a real server remains outstanding and should be the first thing done against the Compose stack.

`audit_log` has no foreign key on `actor_id`, on purpose: a cascade from `users` would give an append-only table a delete path through the relationship. R-31 is asserted by testing that the mapper exposes no relationships and no mutable collections.

## Data sources

Datasets are never committed to Git (R-40). The checksums below are **measured**, not transcribed: each was computed over the bytes actually fetched, and `aegis_ml/data/datasets.py` is the single copy. `test_datasets.py` fails if this table and that module disagree.

### What is reachable, and how it was obtained

The sandbox's outbound network is allowlisted. `research.unsw.edu.au`, `unb.ca`, `huggingface.co`, `zenodo.org`, `kaggle.com` and `raw.githubusercontent.com` all fail to connect. Three things do work, and the whole inventory rests on them:

- **`api.github.com`**, unauthenticated, serves file bytes through the contents endpoint when `Accept: application/vnd.github.raw` is set. This is what `scripts/fetch_datasets.py` uses — not `raw.githubusercontent.com`, which cannot be reached. Unauthenticated callers are rate limited to 60 requests/hour.
- **The publisher pages are still readable** through a fetching tool that is not subject to the sandbox allowlist, which is where the official record counts and feature list came from.
- **`codeload.github.com`** serves repository tarballs.

The publisher's own artifacts are *not* reachable: UNSW distributes the source files from a SharePoint share, and UNB's day files are 11 GB PCAPs. Everything below is therefore a third-party mirror, recorded as such.

### Inventory

| Dataset | File | Mirror | SHA-256 | Bytes | Rows × cols | Usable for R-60/R-61 |
|---|---|---|---|---|---|---|
| UNSW-NB15 | `UNSW_NB15_training-set.csv` | `shailjaroy/NIDS-UNSW_NB15` | `bec7dd5ec88dc2a0ccc7a07879d338395ed7421750f675fd0339e07dfe0648fa` | 32,293,018 | 175,341 × 45 | **No** — no addresses, no timestamps |
| UNSW-NB15 | `UNSW_NB15_testing-set.csv` | `shailjaroy/NIDS-UNSW_NB15` | `734fe6642edf758f7c94d7d9149426b49d202fe8e7bf0bef47392489c3c0a559` | 15,380,800 | 82,332 × 45 | **No** — no addresses, no timestamps |
| UNSW-NB15 | `unsw_nb15_official_schema_sample.csv` | `luna866/UNSW-NB15` | `13be3cddc8c8c2e0fe874d68841e7f0b007eaa13cf9a194a20991e0d6f41da74` | 2,386,163 | 10,000 × 49 | Yes |
| CIC-IDS2017 | `Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv` | `StarterArcher/CICIDS2017` | `306294008927756094b069d24764bfa6519fe267a8104903c056fc9c3cf38636` | 36,010,816 | 225,745 × 32 | Yes |
| CIC-IDS2017 | `Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv` | `jasonwvh/tda-cicids2017` | `7a05a252c5189e5c2e2c478afa3d48f80e599b5e03aeab37b2635d92eaa028fd` | 67,044,444 | 170,366 × 85 | Yes |
| BGL (system logs) | `BGL_2k.log` | `logpai/loghub` | `2a819ea540909db682005c9cf948387a40729b5c2e9f19d430e29ce704825496` | 317,150 | 2,000 × 1 | Yes |
| BGL ground truth | `BGL_2k.log_structured.csv` | `logpai/loghub` | `3fe74103c0b02a28514534e2a47257a3f770135ca61afd425bbd3b9d6a31fe26` | 425,129 | 2,000 × 13 | Verification only |
| **Synthetic** (ours) | `data/synthetic/*.ndjson` | Built — `scripts/generate_synthetic.py` (T-106) | Deterministic by seed (R-42) | — | 7 scenarios × N | Yes |

Publisher pages, for anyone who needs the authoritative artifact: [UNSW-NB15](https://research.unsw.edu.au/projects/unsw-nb15-dataset) and [CIC-IDS2017](https://www.unb.ca/cic/datasets/ids-2017.html). Licences: UNSW-NB15 is free for academic research in perpetuity with commercial use by agreement, citing Moustafa & Slay (MilCIS 2015); CIC-IDS2017 is free for research and educational use, citing Sharafaldin, Lashkari & Ghorbani (ICISSP 2018).

### Integrity findings, all of which would have been silent

- **Two mirrors have the training and test file names transposed.** `2hyes/security_ml` serves a file named `UNSW_NB15_training-set.csv` whose SHA-256 is `734fe664…` — byte-identical to the official *test* split. `SVKBlackDeath/UNSW-NB15` does the reverse. Row counts prove it: the file named "training" in one holds 82,332 rows, which the publisher documents as the test count. **Verify by hash, never by name.** Training on the published test split and reporting metrics on the published training split is the failure this would have caused.
- **The widely mirrored `UNSW_NB15_training-set.csv` is a 45-column derivative, not the publisher's 49-feature CSV.** It drops `srcip`, `sport`, `dstip`, `dsport`, `stime` and `ltime`, and adds a `rate` column that the official feature list does not enumerate. Without addresses there is no entity-disjoint split (R-61) and without timestamps no temporal split (R-60) — so the file most benchmark papers actually use cannot support this project's leakage invariants at all.
- **The official feature-description file enumerates 49 entries but omits `rate`**, which the data CSVs do contain. It is also **CP1252-encoded, not UTF-8** (byte `0x92`); reading it as UTF-8 raises.
- **The 49-column sample recodes `attack_cat` as an integer.** The code table (`0=normal, 1=Exploits, 2=Reconnaissance, 3=DoS, 4=Generic, 5=Shellcode, 6=Fuzzers, 7=Worms, 8=Backdoor, 9=Analysis`) was read from the mirror's own `mapping.pkl` by disassembling it — never by unpickling it — and cross-checked against the binary `label` column: code 0 corresponds exactly to `label=0` and every other code to `label=1`.
- **That same sample stores `stime` as Unix epoch seconds**, where the published CSV uses `17/02/2015 08:40:10 PM`. Reading one as the other would place every record in 1970 or reject it. Decoding yields 2015-01-22 → 2015-02-18.
- **CIC-IDS2017's header carries a leading space on most columns** (`" Source IP"`), and its timestamps are truncated to minute precision (`07/07/2017 03:30`), so flows inside one minute have no reliable ordering. Temporal splits remain valid at minute granularity.
- **Neither dataset states a timezone.** Records are stamped UTC, so every timestamp carries one constant unknown offset. A temporal split is unaffected — all rows shift together — but absolute times in `flow@1` are not wall-clock truth.
- **`direction` is a property of the capture, not of the record.** Deriving it from RFC 1918 addresses classifies 99.16% of UNSW-NB15 as external-to-external, which is not a direction. Each dataset therefore declares its monitored network: `149.171.0.0/16` for the ADFA capture, and UNB's published victim/attacker ranges for CIC-IDS2017. Measured against those, only 0.84% and 0.02% of rows respectively fall outside a boundary at all.

### Measured parse results

| Source file | Rows read | Parsed | Rejected | Unmapped columns |
|---|---|---|---|---|
| `Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv` | 225,745 | 225,689 | 56 (54 protocol 0/HOPOPT, 2 negative duration) | 14 |
| `unsw_nb15_official_schema_sample.csv` | 10,000 | 9,756 | 244 (228 unsupported protocol across 57 names, 16 outside boundary) | 34 |

Row counts read match the inventory exactly, which is T-103's acceptance criterion. For the log corpus (T-104) the parser reads **2,000 of 2,000 lines with zero unparseable**, across 1,778 distinct hosts and 5 components; its severity counts (critical 347, error 48, info 1,597, warning 8) match LogHub's published labels exactly, with SEVERE folded into `error` and FATAL into `critical`. CIC-IDS2017's Friday file holds 97,718 BENIGN and 128,027 DDoS flows, with 2,066 distinct source and 2,553 distinct destination addresses — real entity churn, which D-014 worried captures might lack.

### How the baselines were finally scored (T-110)

Not a tooling problem, and not a shortage of data either — two capture days and 395,903 records were fetched and parsed for this. It was a property of the data interacting with R-61, resolved by **D-015**.

Combining Thursday (Web Attacks) and Friday (DDoS) gives 12,645 source-keyed windows spanning 2017-06-07 11:37 to 2017-07-07 05:02. At the 80% cutoff (2017-07-07 04:08):

| Split rule | Windows at/after the cutoff | Labels |
|---|---|---|
| Temporal only (R-60) | 2,606 | 1,559 normal, **1,045 DDoS**, 2 mixed |
| Temporal + entity-disjoint (R-60 + R-61) | 598 | **598 normal, 0 attack** |

**R-61 was the binding constraint, not R-60.** The temporal split alone holds out plenty of attack traffic; requiring that no entity appear in two folds removes all of it, at every cutoff from 0.5 to 0.9 (1,505 / 860 / 624 / 598 / 510 windows, all normal). The mechanism is the opposite of what D-014 anticipated — abundant entity churn (4,600 entities in train), but **persistent attack sources** that entity-disjointness necessarily assigns to the earlier fold.

Under D-015 both runs below are `temporal-only`, so the leakage is measured rather than assumed: the two-day run shares **43 entities** between train and test, the single-day run **20**. Those counts are in the run logs next to the metrics.

**The two runs disagree, and the disagreement is the finding.** The two-day run scores near-perfect because its folds are *different capture days* — train 8.9% positive, test 51.9% positive — so the model separates days as much as attacks. The Friday-only run is within a single capture day, where train is 63.3% positive and test 4.7%. That is the run to read.

**A fixed 0.5 threshold is not a result.** On Friday's 4.7%-positive test fold, gradient boosting at 0.5 reports precision 0.0872 with recall 1.0 — it raises 13,601 false positives. At its own best-F1 threshold of 0.65 the same model reaches precision 0.9954. Both are true; quoting only the first misrepresents the model, and quoting only the second hides that no threshold was calibrated on validation. Every baseline report now carries both, plus the fold's base rate.

**A data-quality anomaly worth knowing about.** The Thursday file's earliest window starts **2017-06-07 11:37, a month before the documented capture window of 3–7 July 2017**. Some CIC-IDS2017 rows carry timestamps outside the stated period, so the timeline of a combined capture is not as clean as the dataset page implies.

**Reproducing them.** Run logs live under `data/`, which R-40 keeps out of Git, so the command is the reference rather than the file. Both were run twice and agree to the digit; neither model uses an RNG.

```console
$ python scripts/fetch_datasets.py --only cic-ids2017
$ python scripts/run_baselines.py --dataset cic-ids2017 --split-policy temporal-only \
      --file data/raw/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv
$ python scripts/run_baselines.py --dataset cic-ids2017 --split-policy temporal-only \
      --file data/raw/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv \
      --file data/raw/Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv
```

**What this does not establish.** ROC-AUC of 0.999+ on CIC-IDS2017 is close to what published flow-feature results report, and it should not be read as production capability: CICFlowMeter features on this capture are near-linearly separable, and no released model here has yet been gated on an entity-disjoint holdout. That gap is **Q-07**.

### T-104 — log corpus, and a retraction

The corpus is **BGL** from LogHub, 2,000 lines of real BlueGene/L system logs, plus LogHub's own `*_structured.csv` for the same lines as ground truth. Both are in the manifest with measured hashes.

- **2,000 of 2,000 lines parse, zero unparseable**, across 1,778 distinct hosts and 5 components. Severity counts (critical 347, error 48, info 1,597, warning 8) match LogHub's published labels exactly, with SEVERE folded into `error` and FATAL into `critical`.
- **Thunderbird was rejected, not overlooked.** It is the other syslog-shaped corpus available, but it has no severity column at all and `log@1` requires one. Deriving a level from keywords in the message would have put fabricated data into the training set.
- Template mining runs in two passes. A lexical pass alone produced 1,198 templates where LogHub's labels have 120 — it cannot see that two messages are the same event when a varying token carries punctuation (`2,`, `0x0b85eee0,`), which is common because prose is punctuated. The merge pass, which repeatedly unifies templates differing in exactly one position, takes that to **103 templates, 0.9935 agreement against LogHub's grouping and 0.9530 the other way** (the lexical pass alone: 0.4185).
- **Retracted claim.** An earlier figure of "121 templates, 0.98 agreement" was wrong. It came from iterating a Python `set` while assigning messages to templates, so the count depended on incidental ordering rather than on the miner. Re-running that same code in the module gave 284. The deterministic figure is 103, and assignment order is now stored in the artifact (least-specific-first) instead of being left to Python. Recorded here so the 121 is not reused.
- **Known gap, pinned by a test.** Messages that vary in *two* positions at once are not merged, because the merge only unifies single-position differences. LogHub treats those as one event. The cost is small in the measured direction, but it is the first thing to revisit if template quality starts to matter.

### Notes that will still bite us later

- Both network datasets are **2015 and 2017 vintage**. Protocols, encryption prevalence and traffic mix have moved on. v1.0 is framed as architecture validation on public benchmarks; retraining on modern captures is backlog item T-612.
- Neither public dataset contains genuine insider-threat or long-period C2 beaconing behaviour. T-106 fills that gap, and its scenarios must be described in the model card so nobody mistakes synthetic performance for field performance (R-42).
- Datasets are fetched on demand, checksummed, and stored under `data/raw/` (gitignored). Never baked into a Docker image. They are written as **NDJSON, not the Parquet T-103 names** — the project has no columnar dependency yet, NDJSON is already the pipeline's storage format, and one record per line streams, which 2.5 M rows require.

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
| `features@1` | logistic regression | CIC-IDS2017 Friday, temporal-only, best-F1 @0.95 | 0.9868 | 0.9792 | 0.9830 | 0.9990 | 0.9398 | `data/runs/baselines_cic_friday.json` | 2026-10-04 |
| `features@1` | gradient boosting (60 stumps) | CIC-IDS2017 Friday, temporal-only, best-F1 @0.65 | 0.9954 | 1.0000 | 0.9977 | 1.0000 | 1.0000 | `data/runs/baselines_cic_friday.json` | 2026-10-04 |
| `features@1` | logistic regression | CIC-IDS2017 Thu+Fri, temporal-only, best-F1 @0.60 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | `data/runs/baselines_cic_ids2017.json` | 2026-10-04 |
| `features@1` | gradient boosting (60 stumps) | CIC-IDS2017 Thu+Fri, temporal-only, best-F1 @0.65 | 0.9993 | 0.9973 | 0.9983 | 1.0000 | 1.0000 | `data/runs/baselines_cic_ids2017.json` | 2026-10-04 |

*Recorded by T-110. These are the bar every transformer result must clear (R-64). Read them with their caveats, all measured: the table shows the **best-F1 operating point**, because at the fixed 0.5 threshold the same models score F1 0.6207 and 0.1605 on the Friday fold; the test folds are 4.7% (Friday) and 51.9% (Thu+Fri) positive; and both runs are `temporal-only` under D-015, sharing 20 and 43 entities respectively between train and test. The Friday row is the one to compare against — the Thu+Fri rows separate capture days as much as attacks. These are benchmark-comparable numbers, not release-gate evidence.*

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
| **Q-01** | Should `LogNet` use a frozen pretrained DistilBERT encoder over raw log messages, or a from-scratch transformer over Drain3-mined template IDs? | Model lead | **T-204** | **CLOSED by D-019 (2026-10-04)** — from-scratch over mined template IDs. 103 templates at 0.9530 purity means the input barely contains language, the miner already exists, and NFR-05's 150 ms cap rules out DistilBERT on CPU. |

| **Q-02** | Is Elasticsearch justified at v1.0, or does partitioned PostgreSQL with full-text search cover the hunt console? | Backend lead | **T-305** | **CLOSED 2026-10-05 — partitioned PostgreSQL (D-034)**; Elasticsearch deferred to T-6xx, with measured re-open triggers |
| **Q-03** | What absolute false-positive budget (alerts/day) will the reference customer tolerate? | Product | Threshold defaults, T-207 | OPEN — needed to set the shipped defaults rather than guessing |
| **Q-04** | Which reference deployment supplies real flow records, and in what format (NetFlow v5/v9, IPFIX, Zeek)? | Product | NFR-02 validation, T-612 | OPEN |
| **Q-05** | Do we need multi-tenancy at v1.0, or is single-tenant per deployment acceptable? | Product | Schema design, T-301 | OPEN — currently assumed single-tenant per deployment (D-001 context); the schema includes `tenant_id` on thresholds only |
| **Q-06** | For volumetric attacks, should a flow window be keyed on the source entity, the destination, or both? | Model lead | **T-108**, T-201 | **CLOSED by D-013 (2026-10-03)** — both, chosen per family. Raised by T-107. `architecture.md` §7.1 keys the window on one source entity, but the synthetic DDoS scenario spreads a single flood across ~40 sources, so each per-source window holds about one flow and the attack is invisible at that granularity. Either the window key changes, or volumetric detection needs a destination-side feature path |
| **Q-07** | Where do release-gate numbers come from, given that no entity-disjoint split can hold out CIC-IDS2017's attack traffic? | Model lead | **T-203**, **T-208**, release gating | **PARTIALLY ANSWERED by D-016 (2026-10-04)** — the entity-disjoint option is closed, and by measurement rather than argument: 2,561 of Friday's 2,562 attack windows belong to one source entity, so R-61 is a coin flip at n=1 and destination-keying only mirrors it onto the victim. What remains is a **family-level holdout** (test detection of an attack class the model never trained on), which the two-day capture supports once. That is not built yet, so until it is, no model here has a release-gate metric and the 0.999+ ROC-AUC in the ledger is benchmark-comparable only |
| **Q-08** | The compose stack pins `bitnami/kafka:3.9`, which no longer exists — Broadcom deleted the public `docker.io/bitnami` catalog on 2025-09-29 and moved versioned tags to a frozen, unpatched `docker.io/bitnamilegacy`. Migrate to the official `apache/kafka`, or accept the legacy image? | Infra lead | **T-005**, any streaming path (T-401 onward) | OPEN — raised 2026-10-04 when a local `docker compose build` failed to resolve the reference. It now points at `bitnamilegacy/kafka:3.9`. It cannot be profiled out: `backend` depends on it with `condition: service_healthy`, and compose rejects a dependency on a service whose profile is disabled. The legacy image keeps the current `KAFKA_CFG_*` env scheme and `/bitnami/kafka` volume but receives no CVE patches, which is a poor fit for a security product; `apache/kafka` is maintained but needs `KAFKA_*` variables, a different data directory and a KRaft cluster id. Neither option has been run here — there is no Docker daemon in the sandbox — so the migration must be verified on a machine that has one |

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
| 1 | **Build analyst verdicts** — immutable once written, superseding with history (T-309) | T-309 | Next |
| 2 | Continue E3: verdicts, WebSocket channel, webhooks, audit service | T-309…T-320 | This sprint |
| 3 | Confirm Q-03 (false-positive budget) and Q-05 (multi-tenancy) with their owners | — | Before threshold defaults ship |
| 4 | Run the compose stack where a Docker daemon exists; close T-005 and settle Q-08 | T-005 | When Docker is available |
| 5 | Verify the T-301 migration up and down against a live PostgreSQL 16 | T-301 remainder | When a server is reachable |
| 6 | Apply the k8s manifests to a cluster — the checks are static only | T-504 | M5 |
| 7 | Build the family-holdout release gate Q-07 still owes, then a gated metric for `LogNet` | T-203, T-208 | Before release |

Completed since the last revision of this table: the datasets were fetched and checksummed (T-101–T-105, T-110), `features@1` was pinned (T-107), windowing, splits, the leakage audit and the evaluation harness landed (T-108, T-109, T-111, T-112), both models and the scoring modules landed (T-201–T-215), and E3 reached T-307.

### D-031 — R-51 is enforced where verification happens, and rotation means the old token dies
Argon2id hashing is easy to get nominally right and still be wrong, because the
rule is about what is stored, not what is written today. So `verify_password`
**raises** `NonArgon2Hash` for MD5, SHA-1, bcrypt and Argon2i instead of
returning False: a False reads as "wrong password, try again", and a legacy row
would produce that forever instead of being rehashed on next login.
`needs_rehash` is checked on success, which is the only moment the plaintext is
available.

Refresh rotation is single-use: `rotate` marks the presented `jti` spent before
returning a new pair. **Replaying a spent token revokes the entire family**, on
the reasoning that two parties holding one single-use credential means at least
one is not the user — so the legitimate session dies as well, and the user logs
in again. Rotation without replay detection would let a stolen refresh token be
used once and still look healthy. Families are independent, so revoking one
stolen session does not lock the user out everywhere.

**A test of mine was wrong and the code was right.** I forged a token by editing
the payload *and re-signing with the correct key*, so it verified — that is not
tampering, it is issuing. Real tampering keeps the original signature and fails.
That a correctly re-signed forgery **is** accepted is now its own test, because
HS256 is a symmetric MAC: the secret is the entire security boundary, which is
why a short secret is refused and why it comes from the environment.

`RefreshStore` is a protocol so T-303 can supply a persistent store. The
in-memory default is explicitly not for production — rotation state that
vanishes on restart lets a spent token be replayed against a fresh process.
Argon2-cffi raises `VerificationError`, not only `InvalidHashError`, for some
malformed hashes; catching only the narrow one turned a corrupt stored hash
into a 500.

### D-032 — A completeness check that reads the framework must be checked for reaching anything
R-53 is enforced by a matrix test that enumerates every route. The first version
read `app.routes` and compared paths against `ROUTE_MATRIX`. FastAPI's
`include_router` does not flatten: the parent holds an `_IncludedRouter`
container whose `original_router` holds the real routes, so `app.routes`
contains the four documentation endpoints and a container with no `path`. The
walk found no endpoint paths, concluded the matrix was complete, and the test
passed — while enforcing nothing. **A guard that cannot fail is worse than no
guard**, because it is read as coverage.

Two rules follow. Any completeness check that introspects a framework must be
paired with a test asserting it actually sees the things it claims to count
(`test_the_route_walk_is_not_vacuous` asserts `/healthz` and `/readyz` are
found). And the "adding a route is detected" test must be written against the
real application factory, not a toy `FastAPI()`, because the toy flattens and
hides the difference.

RBAC itself is default-deny with capabilities declared per role in a written-out
table, so a new capability cannot reach other roles by inheritance. A 403 names
the caller's role but never the missing capability, and an unknown role string
is refused rather than defaulted to the least privilege.

### D-033 — Ingest needed a capability R-53 does not name
R-53 enumerates read, verdict, export, webhook config, users, models and
retention. Ingest is none of them. Borrowing `READ` would have granted it to
`viewer`, which R-53 makes read-only, so ingest writes through a read
capability. `Capability.INGEST` was added instead and granted to analyst,
responder and admin. **This is a judgement call, not a reading of the rule** —
if the API-key path (architecture.md:133 authenticates ingest with "JWT or API
key") turns out to be the intended route for collectors, the capability should
move to that credential type and this should be revisited.

Batch semantics: FR-04's "never fail the whole batch" applies to records, so an
unparseable NDJSON line is a per-record `parse` error and the remaining lines
are still accepted. It does not apply to the request, so an oversized batch
returns 413 and a body that is not JSON or NDJSON returns 415 — neither has a
record to attribute the failure to. Line numbers are carried through the parse
rather than recomputed after dropping bad lines.

`flow@1` and `log@1` are duplicated in the backend rather than imported from
`aegis_ml.data.records`, because the two services deploy as separate containers
and the API process should not pull the ML package into its import graph.
Duplication that may drift is worse than coupling, so a test imports the real
models and asserts the two agree field for field.

### D-034 — Q-02 decided: partitioned PostgreSQL for the hunt console at v1.0, Elasticsearch deferred
Q-02 asked whether Elasticsearch is justified at v1.0 or whether partitioned
PostgreSQL with full-text search covers the hunt console. **Decision: partitioned
PostgreSQL, and Elasticsearch moves to the backlog (T-6xx).**

The reasoning, and its limits. The stated blocker was that the target log volume
is unknown until a reference deployment exists — and that is still true, so this
is a decision under uncertainty rather than a measurement. What tips it is the
asymmetry of the two errors. Choosing Postgres and being wrong costs a migration
once volume is known and a real query profile exists. Choosing Elasticsearch now
costs a second store to operate from day one, a second failure mode, duplicated
data with consistency lag between the two, and a hunt console whose correctness
depends on both agreeing. Paying that cost against an unmeasured volume is the
worse bet.

What already exists on the Postgres side: `alerts` and `ingest_stats` are
monthly-partitioned with pruning verified against a real server (D-030), R-34
makes every query time-bounded by signature (D-029), and Postgres supplies
`tsvector`/GIN and `pg_trgm` for text search natively.

**Re-open Q-02 if any of these is measured, not assumed:** sustained log volume
above roughly 50 GB/day; a hunt query that needs multi-field aggregation across
more than three months and misses its latency budget; or a full-text query whose
`EXPLAIN` shows a scan that partition pruning cannot help, because the predicate
does not include the partition key. That last one is the structural limit — FTS
queries that cannot name a time window defeat the partitioning entirely, and
that is a property of the workload rather than of tuning.

### D-035 — Ordering is a partition-assignment property, and there is no broker here to test against
Kafka orders records within a partition and makes no promise across partitions.
So "one entity's flows stay ordered" is decided entirely by which partition a
record is sent to, and the broker is not where to look for the bug. Two
consequences shaped the implementation.

The partitioner delegates to `kafka.partitioner.DefaultPartitioner` instead of
hashing the key directly. A hand-rolled hash would be perfectly deterministic,
pass every stability test, and still disagree with the broker -- and the
disagreement would only appear as out-of-order scoring after a rebalance. A test
asserts agreement across 50 keys, which is the only thing making the delegation
meaningful rather than decorative.

Resume after a restart is `committed + 1`. A Kafka offset identifies a record
already in the log, so resuming *at* the committed offset reprocesses it, and
resuming from the log end skips everything written while the consumer was down.
Commits are also monotonic: a stale commit arriving after a newer one, which
happens when a rebalance moves a partition, must not rewind the position.

Lag is exported per `(group, topic, partition)`. A single group-level number
hides the one case that matters -- a single stuck partition -- by averaging it
into a healthy-looking total. Lag is clamped at zero because retention can delete
records a consumer never reached, and a negative value reads as "ahead" when the
consumer has actually lost its place.

**What is not verified.** There is no Kafka broker in this environment. The
partitioning, the offset arithmetic and the gauge are tested; the broker call is
a one-line injection point (`Producer` protocol) and has never run against a real
cluster. Recording this rather than implying coverage: the untested part is small
and named, and the untested part is the part that needs a cluster.

### D-036 — Idempotence needs identity from data, not from process state
At-least-once delivery plus an idempotent sink is the standard way to get
exactly-once *effect*, and the sink is the easy half. The half that breaks is
choosing the identity.

Two failures were measured here rather than reasoned about. Windowing each batch
independently restarts the window numbering, so batch two's first window
collides with batch one's and overwrites it: the same 20 records produced 1, 2
or 4 windows depending on `batch_size`, a throughput knob. And a window counter
held in worker memory resets on restart, so a replayed window takes index zero
again and lands on an identity already used. That second one passes every test
that stays inside a single process lifetime and fails the one the task is about.

The fix is to key on the **log offset of the window's first record**. A Kafka
offset is a property of the record and is immutable, so it is stable across
reads and across restarts. The general rule: an idempotency key must be derived
from the data being processed, never from the state of the process processing
it. Process state is exactly what a restart destroys.

Records are now buffered per entity across batches so windows and their offsets
stay continuous. The windower is shared with `aegis_ml` rather than
reimplemented — a second implementation would number windows differently and
emit the same data under different identities, which is the same bug wearing a
different hat.

### D-037 — Correlation policy: a case is one incident, and it never gets quieter (T-308) (2026-10-05)
The correlator is small enough that every choice in it looks obvious and only
one reading of each is defensible. Writing them down so the next person changing
one knows what they are changing.

**Boundaries are inclusive, and the cool-down runs from `last_seen`.** A repeat
at exactly 15 minutes is still the same incident; 15 minutes and one second is a
new one. Measuring from the last occurrence rather than the first makes the
cool-down a debounce — a sustained attack stays one alert, which is the point of
FR-15 — at the cost that a case can stay open indefinitely under continuous
traffic. That is the intended trade: the analyst triages an incident, not a
stream of identical rows.

**A case never de-escalates.** Every occurrence is re-fused from the best score
per modality, and the case keeps the highest composite it has seen. Two reasons.
An alert that reads HIGH and later reads MEDIUM while nothing improved teaches
an analyst that the label is noise. And the loudest evidence in an incident is
what a triager needs; averaging it down with quieter repeats is how a real
intrusion gets triaged as noise. `first_severity` records what it opened at, so
escalation is visible rather than hidden.

**Retention must not become a severity input.** Occurrences are capped for
memory (a flood inside one cool-down would otherwise grow a case without bound),
but the count stays exact and the loudest score survives eviction. This was the
one clause my first test suite did not actually test: substituting
`fused.score` for `max(case.score, fused.score)` left both de-escalation tests
green, because `_fuse_best` already keeps the maximum per modality, so only
eviction can make a case's available best fall. The failing test — retention of
one, a 0.99 evicted by a 0.4 — was added and the substitution then failed it.

**Grouping is not deduplication.** Dedup keys `(entity, family)`; grouping keys
the entity, the opposite modality and ±60 s, symmetric because either model can
finish first. A grouped case clears `partial_evidence`, since it now genuinely
has both sides, and its score rises from the penalised single-modality number to
the fused one. The case keeps the family it opened with — the filter and the
cool-down key both refer to it — while `families` grows, and repeats of any
family the case carries dedup into it. A closed case absorbs nothing and groups
nothing: swallowing a fresh occurrence into a row the analyst has closed leaves
nobody looking at it.

**Replay safety is per evidence id.** T-307 emits at-least-once, so the same
window can arrive twice; a detection whose window is already recorded is a
no-op. The evidence index deliberately outlives the display retention, or a
replayed window whose occurrence was evicted would be counted twice — the same
class of defect D-036 describes, one layer up.

**The persistence gap is named, not hidden.** `CaseStore` is a protocol and the
in-memory implementation is what runs here. A SQLAlchemy adapter is not written
because the `alerts` table holds one `window_ref` per row and cannot answer "was
this window already counted?" without a queryable evidence index, and there is
no PostgreSQL in this environment to verify one against. `alert_row()` pins the
column encoding — including the bounded evidence trail under `window_ref`
(defined as opaque) and R-70's explanation payload — so the adapter is a thin
insert rather than a design question. `FusionRule` is injected for the same
reason `aegis_ml` is not installed in the backend image: one implementation of
the arithmetic, wired at the composition root.

**A defect found here and deliberately not fixed here:** `alerts.score` and
`thresholds.value` are `Float` and `alerts.severity` is an unconstrained
`String(20)`, against R-39 (`numeric(5,4)`) and R-38 (enum + check constraint).
Both are real, both are schema changes to a migration that has still never been
applied to a live server (D-030), and neither belongs inside T-308's change.
Raised as **T-321** so it is tracked with acceptance criteria rather than
carried in someone's head.



### D-038 — A verdict is an appended record, and a repeat is not a supersession (T-309) (2026-10-05)

**Decision.** An analyst's verdict is an immutable record appended to a per-alert
ordered ledger. `alerts.verdict`, `verdict_at` and `verdict_by` are a
denormalised pointer for the list view; the ledger is the source of truth, and a
change appends a record whose `supersedes` names the one it replaces, so the
history is a chain rather than a field whose previous values are lost. An alert
is addressed by `(id, created_at)`: D-030 makes a bare id ambiguous across
partitions and R-34 forbids touching the partitioned table without a time bound,
so the partition key is required on every verdict read and write, never
defaulted.

**A repeat is not a supersession.** Recording the verdict already current, for
the same alert by the same analyst, returns ``unchanged`` and appends nothing. A
different verdict appends, and so does the same verdict from a *different*
analyst: that is independent agreement, which is worth a record, while a re-sent
request is not. Without the rule, a timeout retry or a double-click pads the
history with rows that are indistinguishable from reconsideration.

**The alert row is written only when something changed.** `alert_verdict_update`
returns ``None`` for ``unchanged``; issuing the update anyway would move
`verdict_at` forward and make a re-submission look like a fresh decision.

**Open, and named in the code rather than left implicit.** A durable ledger needs
a new append-only table and a migration (R-32) -- the `alerts` row cannot carry
history -- and the actor is the token's opaque ``sub`` while
``alerts.verdict_by`` is a numeric ``users.id`` foreign key, so the adapter must
resolve one to the other through the users table rather than an ``int()`` cast.
Neither is written here because there is no PostgreSQL in this environment to
verify a migration against. Audit rows for mutating routes are T-312's job, per
the `AuditLog` model's own docstring.

### D-039 — The alert stream is a cache, and a client that fell behind is told so (T-310) (2026-10-05)

**Decision.** Alerts are pushed over one in-process hub that keeps a bounded window
of recent notifications, and the `alerts` table stays the record. Every
notification carries a sequence, every handshake carries the hub's `epoch`, and a
client reconnects by naming the last sequence it processed.

**A cursor that is out of step gets `resync_required`, in either direction.** Behind
the retained window means notifications are gone; ahead of the newest sequence
means the cursor came from somewhere else — another process's numbering, or a
replica that has not seen it. Both answer the same way: hand over the whole
retained window *and* set the flag, because a silent "nothing new for you" is how
an alert stream loses alerts while looking healthy. Cursor `0` is neither: it
means "no position yet", which is why sequences start at one.

**A subscriber that stops reading is dropped, with its cursor.** Each
subscription has a bounded queue; overflow marks it dropped with the reason and
the last sequence it actually received, and the transport closes carrying that
cursor. An unbounded queue turns one hung browser tab into a memory leak, and
dropping without a cursor turns it into a silent gap.

**Publishing is thread-safe because the producer is not the event loop.** The
correlator runs in the scoring worker, which is synchronous. `publish()` is a
plain call any thread may make; delivery hops onto each subscriber's own loop.
Subscribe and publish share one lock, so a publish either joins a catch-up or
arrives live — never both, never neither, which is what makes "no alert is lost
across the switch" a property rather than a hope.

**The cursor is per-process, so it comes with an epoch.** A restart renumbers
from one; a client whose epoch changed must resync rather than trust its cursor.
D-036's rule — identity from data, not from process state — applied to the
stream.

**Auth is the same check, not a second one.** The socket handshake calls the same
capability table the HTTP dependency does (`rbac.authenticate`), because a
WebSocket is not a `Request` and a second copy of "is this token valid, may this
role read" is exactly how a socket becomes the way around the matrix. The token
travels in `Sec-WebSocket-Protocol` for browsers, which cannot set a header, and
never in the URL, where it would reach access logs.

**Gaps, named.** The buffer is in-process and does not survive a restart, so a
multi-replica deployment needs a shared bus (Redis or Kafka) behind the same
interface. The `ws` extra is what lets uvicorn serve the socket; it is not
installed here, so the ASGI contract is verified and uvicorn's transport is not.
The dashboard half of the fallback — banner, 15 s polling, resume — is T-405.

### D-040 — A webhook signature covers the bytes that were sent, and the destination is re-checked per attempt (T-311) (2026-10-05)

**Decision.** An outbound webhook body is canonicalised once (sorted keys, compact
separators), signed as ``HMAC-SHA256(secret, "<timestamp>.<body>")``, and the
header ``X-AEGIS-Signature: t=<unix>,v1=<hex>`` is sent alongside those exact
bytes. Every attempt of one delivery carries the same timestamp, signature and
``X-AEGIS-Delivery`` id.

**Why sign bytes rather than an object.** A scheme that signs a re-serialised
object verifies right up until a field order or a float representation changes;
a scheme that signs the wire bytes verifies against what the receiver actually
holds. The timestamp is inside the MAC, so it cannot be swapped for a fresh one
over an old body, and the header carries a version, so a future scheme can be
introduced without a receiver accepting a downgrade.

**Why one signature per delivery rather than one per attempt.** A retry is the
same event: a receiver that deduplicates on the signature would otherwise see one
alert as several, and a receiver that enforces the replay window would refuse a
retry the moment the backoff exceeded it. The default budget — five attempts,
1/2/4/8 s of exponential backoff with full jitter, 15 s total — is deliberately
inside the 300 s window receivers are told to enforce, and a test asserts that
inequality so neither number can move alone. Full jitter, because a fleet
retrying a recovered receiver in lockstep is a self-inflicted thundering herd.
A 4xx that is not 408/425/429 is not retried: the receiver received and refused
the bytes, and repeating them only delays the operator learning that the endpoint
rejects the payload.

**Why the destination is validated per attempt, not once at registration.** The
address that was checked must be the address dialled (R-55). A hostname that
resolved public when the target was registered may resolve to
``169.254.169.254`` later, and a stored target is exactly what a rebinding attack
waits for. So the sender validates immediately before each attempt and hands the
transport a request that names the **pinned** address to connect to and the
hostname to present for ``Host``/SNI; the transport resolves nothing itself. A
DNS failure is a retryable network condition; a private answer is a block.

**The verdict is named, and multicast is refused first.** ``is_global`` is the
accept rather than a hand-written list of ranges, because the list is the thing
that goes stale — but CPython counts IPv4 multicast (224/4) as global, which a
smoke matrix found and a test now names. Loopback, link-local, multicast,
unspecified, private and not-globally-routable are refused in that order, so a
refusal names a cause, and a host with *any* refused address is refused whole.

**Secrets are sealed, and shown once.** A signing secret is 32 random bytes,
stored Fernet-sealed under an HKDF-SHA256 key derived from ``AEGIS_SECRET_KEY``,
and returned in the creation response only: no route opens it, so a listing
cannot leak it. Rotating the application secret orphans sealed secrets, and that
is a named error rather than an empty secret — a delivery signed with an empty
key would be refused by every receiver and look like the receiver's fault.

**Gaps, named.** The retry bound and per-attempt timeout are constructor
arguments, not environment settings: the pipeline that would read a setting
does not exist, and a knob nothing reads looks configurable and is not. No
HTTP client ships (``WebhookTransport`` is a protocol), so pinning, redirect
refusal and timeouts are contract, not verified behaviour;
retries are inline in the caller, so a pipeline that cannot afford the worst case
needs a delivery queue; the store is in-memory; and nothing calls ``dispatch()``
yet — the correlator is not wired to T-310's hub either, which is the same seam.

### D-041 — The trail records changes, and it is the widest-read thing in the system (T-312) (2026-10-05)

**Decision.** Every mutating route appends to an append-only audit trail after its
work succeeds. A request that changed nothing writes nothing, and the read side is
open to every authenticated role.

**Changes, not requests.** A refused request changed nothing, so there is no state
for anyone to answer for -- and a row per attempt would let any authenticated
client fill the trail with rows of its choosing, which is how a log becomes
unreadable exactly when someone needs to read it. Three consequences are spelled
out because each looks like an oversight otherwise: a 4xx writes nothing, an
ingest batch that accepted **zero** records writes nothing (nothing entered the
system; the access log already holds that the request was made), and a verdict
re-sent unchanged writes nothing (no decision changed). A *partly* bad batch **is**
recorded with both counts -- the rejected count is the only trace the trail keeps
of what it turned away.

**R-31 is asserted three ways, because one is not enough.** "No ORM update/delete
path" covers the mapper. It does not cover a service that hands back a mutable row,
or a store that grows an `update`. So the assertion also walks the trail object and
the protocol for any mutating name, and the record that comes back is frozen with
its ``detail`` in a read-only mapping -- freezing the field alone would leave the
caller able to edit the dict the frozen record points at. A source-level test
asserts no ``update(AuditLog)``/``delete(AuditLog)``/``on_conflict_do_update``
appears anywhere in the module: the strongest form available without a server.

**Completeness is a table plus a walk of the live application.** ``AUDITED_ROUTES``
maps ``(method, path)`` to an action and ``AUDIT_EXEMPT_ROUTES`` is deliberately
empty; the test enumerates every ``POST``/``PUT``/``PATCH``/``DELETE`` route on the
built app and fails if one is in neither. "Every mutating route is audited" is then
a property of the application rather than a list someone maintains -- the same
mechanism ``ROUTE_MATRIX`` uses for RBAC, and it is proved non-vacuous and proved
by planting an uncovered route.

**The trail is the widest-read thing in the system, so it carries the least.** It
is readable by every authenticated role; webhook configuration is
responder-and-above (R-53). Mirroring a target's URL or host into the trail would
therefore be a privilege leak dressed as thoroughness, and so would an analyst's
note or a record's content (R-54, R-58). What a row holds is what FR-42 asks for --
actor, action, target, timestamp, source IP -- plus thin counters. Each exclusion is
asserted by planting the value and asserting its absence.

**The source IP is the peer, never a header.** ``X-Forwarded-For`` is
attacker-controlled, and an audit log that records whatever the client claims about
itself is worse than one that omits the field. Behind a proxy the peer *is* the
proxy; making it the real origin is uvicorn's ``--proxy-headers`` with
``--forwarded-allow-ips`` naming that proxy. That is deployment configuration, so it
is named here and in the service's docstring rather than silently guessed.

**The read is bounded by construction.** ``start`` and ``end`` are required, the
window is capped at the repository layer's own ``MAX_QUERY_SPAN_DAYS`` so there is
one number rather than two that can disagree, and pages use an exclusive id cursor
-- offset paging would drift as the trail grows, and a page that repeats or skips a
row is a page an auditor cannot cite. The *compiled SQL* is asserted to carry both
bounds, not just the helper's guard: a range that lives in a Python check and not
in the WHERE clause reads the whole table while looking correct.

**Gaps, named.** ``audit_insert`` and ``audit_select`` are the two statements the
persistent trail will run, compiled and asserted, but **no session runs them**: no
database session is wired into the request path, so the trail that runs here is
in-memory and dies with the process. The table itself is in T-301's migration
(``backend/alembic/versions/0001_initial_schema.py``), which -- like every migration
here. That gap closed once on 2026-10-05: the migration was applied to a real
PostgreSQL 16 while verifying T-321 (D-055), and D-055 records that one run: the DDL is
checked in ``--sql`` mode *and* has been applied end to end once -- from a sandbox
install, not from CI, which still has no server. *Corrected while writing T-313, whose
own table is in the same migration: ``audit_log`` was recorded as having "no
migration" and that was wrong; what is missing is the adapter, not the schema.* The actor column wants a numeric
``users.id`` while the token subject is opaque, so the adapter needs the mapping
D-038 names for ``alerts.verdict_by``. The in-memory trail does not survive a
restart. The admin screen and the audited export (FR-43) are E4's and a later task's.

### D-042 — An API key is stored as a keyed digest, never as an Argon2id password (T-313) (2026-10-05)

**Decision.** `api_keys.key_hash` holds **HMAC-SHA256 over the whole presented key
string**, under a digest key derived with HKDF-SHA256 from `AEGIS_SECRET_KEY`
(salt `aegis.apikey.digest.v1`, info `api-key-digest`). 64 lowercase hex
characters -- exactly the column's width, so the schema T-301 created needs no
migration. Passwords stay Argon2id (R-51); a machine credential is not a password.

**Why not Argon2id, stated as a threat argument rather than a shortcut.** R-51
requires Argon2id because a user password is low-entropy and human-chosen, so the
hash has to be expensive per guess. A key is 256 bits drawn from
`secrets.token_urlsafe(32)`: there is nothing to guess and no amount of work makes
a dictionary attack on it interesting. What Argon2id would add here is a 64 MiB
allocation and tens of milliseconds **on every ingest request** -- a
denial-of-service vector the deployment pays for and no attacker suffers from.

**Why HMAC and not a bare digest.** ``sha256(key)`` is an offline oracle: anyone
holding a database dump can test candidate keys against it. Keying the digest means
the dump alone is not enough. The cost is the mirror image and is named: rotating
``AEGIS_SECRET_KEY`` invalidates every issued key at once, the same consequence
D-040 records for sealed webhook secrets. The digest key is a separate HKDF
derivation, so the key that authenticates an API key is not the key that signs a
JWT or seals a webhook secret.

**The stored row is irreversibly short, and the format is the reason the prefix
works.** A key is ``aegis_sk_<id>_<secret>``; the MAC covers prefix and secret
together, so the public id half is protected too and a key with its id rewritten
fails verification rather than merely missing a lookup. The record has no field
that could hold the plaintext, the module exposes no function that returns one
(asserted over its own names), and the only recoverable display value is
``aegis_sk_<id>_`` -- design.md's "only a prefix is stored", satisfied without a
second column.

**A missing row is compared anyway.** Verification against an id that does not
exist derives a digest and compares it against a dummy of the same length, so
"unknown id" and "wrong secret" cost the same work. The residual is named: which
ids exist is still observable through the store lookup, and that is metadata, not
credential material.

**Consequences.** The ``ix_api_keys_key_hash`` index is not on the lookup path
(lookup is by id) and stays as T-301 created it. The in-memory store is what runs
here, so a restart forgets issued keys; the persistent adapter's statements are
written and compiled but no session runs them (D-030's wiring gap).

### D-043 — A key is a principal with scopes, and it cannot outrank the least-privileged role on a route (T-313) (2026-10-05)

**Decision.** An API key authenticates as a *kind* of principal, not as a role.
``Principal`` gains ``kind``, ``scopes`` and ``key_id``; ``capabilities_of_principal``
resolves a user through ``ROLE_CAPABILITIES`` and a key through
``SCOPE_CAPABILITIES``. A key's ``role`` is ``None`` and the absence is deliberate:
filling in the owner's role would hand a machine its owner's authority.

**Reach is a table, and it is default-deny.** ``API_KEY_ROUTES`` maps
``(method, route template)`` to the scope it requires -- three entries: the two
ingest writes (``ingest:write``) and the alert list (``alerts:read``). A route
absent from it refuses keys with 403 "this route does not accept API keys", which
is a different 403 from a key that reached an accepting route without the scope
("lacks a scope granting ..."), because the two are fixed differently: change the
credential or change the route. The table is checked against the built application,
so an entry for a route that no longer exists fails the suite.

**The bound that makes scopes safe.** For every key-reachable route, the scope's
capabilities must be a subset of the capabilities that **every** role the matrix
permits there holds -- the intersection, not the union. Asserted for every entry,
so a key can never hold authority that the least-privileged human allowed on that
route lacks. That is the property which stops a sloppy scope map from becoming a
robot with an administrator's reach, and widening ``alerts:read`` by one capability
fails a test.

**Two credential kinds, one dependency.** ``require()`` now calls
``authenticate_request``, which knows about keys; ``authenticate()`` keeps its
signature and behaviour for the WebSocket handshake (T-310). A key arrives in
``X-API-Key`` or as a Bearer token shaped like one, because both are things
collectors do; presenting an ``Authorization`` header **and** an ``X-API-Key`` is
refused as 401 rather than resolved by precedence, since the failure mode of
precedence is a request authorised by the credential the operator did not mean.

**Revocation is a column, and it is immediate.** ``revoked_at`` is set, never
deleted: the row is the record of a credential having existed, and "was this key
revoked, and when" cannot be asked of a row that is gone. Verification reads the
store on every request -- there is no cache to go stale -- which is what makes
"rejected immediately" a property rather than a hope. A second revoke keeps the
first timestamp, because the fact recorded is when the credential stopped working,
not when someone last clicked.

**Management is its own capability.** ``Capability.API_KEYS`` is held by ``admin``
alone and is written into that row rather than inherited from ``USERS``: issuing a
machine credential is its own decision. The three management routes are admin-only
in the matrix, and issuing and revoking each append to the audit trail with the
key's id, name and scopes -- never the secret and never the digest, because the
trail is readable by every role while key management is not.

**Gaps, named.** The store is in-memory while no database session is wired into
the request path; ``api_keys`` itself has its table and index in migration 0001.
``owner_id`` wants a numeric ``users.id`` while the principal subject is opaque --
the same mapping D-038 and D-041 name. Per-key rate limiting (architecture.md
§11's threat table) is T-316, and the screen that renders the secret once is T-410's
``/admin/keys``.

### D-044 — Retention drops a month only when the whole month is outside the window, and the windows are configuration (T-314) (2026-10-05)

**Decision.** A monthly partition is droppable when its **end** is at or before the
cutoff: ``end <= cutoff``, never ``start <= cutoff``. The cutoff is ``today - window``
for that table, and the window comes from configuration: raw records
``AEGIS_RETENTION_RAW_RECORDS_DAYS`` (30, FR-05's default), alerts and
``ingest_stats`` ``AEGIS_RETENTION_ALERTS_DAYS``/``..._STATS_DAYS`` (400 each). The
policy refuses anything outside ``1..3650``, and refuses
``alerts_days < raw_records_days`` -- keeping fewer days of alerts than the raw
records they were derived from inverts FR-05, and that now fails at **startup**
rather than at the first retention run.

**Why the end, and not the start.** A month whose start is before the cutoff but
whose end is after it holds rows inside the promised window. Dropping it would
destroy data the policy says is retained, and -- worse -- the run would report
success, so nothing would look wrong. The two directions are asymmetric:
``start`` drops a month the policy protects, ``end`` keeps a month it could have
dropped, and only the first is a privacy-incident-shaped failure. The tests assert
the boundary from both sides, including the equality case where a partition's last
instant *is* the cutoff day (a 399-day window on 2026-10-05 ends exactly on
2025-09-01, so ``alerts_2025_08`` drops) -- an implementation using ``end <
cutoff`` passes every other boundary test while holding a day more than it claims.

**The plan is a pure function.** ``plan_retention(policy, today, partitions)``
takes the clock and the catalog as arguments rather than reading either, so every
boundary case is testable without a database, and the preview an operator approves
is exactly what the run executes -- the route builds both through one function.
``missing`` exists because there is no default partition: a month inside the window
with no partition is a month whose rows were rejected at insert, and reporting it
is what stops a plan's silence reading as "nothing to do".

**What retention will not do, named in every plan.** ``audit_log`` appears as
``unevictable`` with the reason: R-31 makes it append-only and it is deliberately
not partitioned, so nothing here can drop it, and erasing an actor from history is
a non-goal whose mechanism is the trail's own retention window. The raw records
themselves are retained **outside this service** -- Kafka's
``AEGIS_KAFKA_RETENTION_HOURS`` and the Elasticsearch ILM policy -- and the plan
reports those mechanisms and the source of each number rather than pretending to
execute them.

**Mechanism and authority.** ``DROP TABLE IF EXISTS`` of the partition, which is
immediate and reclaims space, unlike a ``DELETE`` that leaves dead tuples in every
replica and backup. The service produces drop statements and never runs DDL
itself; the runner is injected, so ``app/services/retention.py`` stays free of the
database (R-15) and of FastAPI. The four routes are admin-only under a new
``Capability.RETENTION`` (R-53); the read-only preview is not audited (D-041: the
trail records changes) and the run records the partitions it dropped **and** the
ones already absent -- "dropped nothing" and "dropped March" are different facts.
A run with no runner wired raises rather than reporting a clean run it did not
perform.

**Gaps, named.** The catalog query (``pg_class``) and the session-backed runner
are not written: there is no database session in the request path yet (D-030), so
``main.py`` installs a named catalog stand-in and a runner that refuses, and the
retention route fails loudly until a real one is wired.

### D-045 — Erasure is a pseudonym in the stores that hold history and a deletion in the stores that hold identity (T-314) (2026-10-05)

**Decision.** Erasure has two kinds. ``entity`` -- an observed host, address,
service, or a user seen in traffic -- is **redacted**: the identifier is replaced
with a tombstone and the row stays, because alerts reference it and removing it
would either destroy incident history an analyst may still be investigating or
leave those references pointing at nothing. ``user`` -- an account -- is
**deleted**, cascading to what hangs off it, because the row *is* the account and
an account whose identifier is a pseudonym has not been erased in any sense the
subject would recognise.

**The tombstone is a keyed pseudonym, not an anonymisation, and it is named as
one.** ``erased:`` plus the first 32 hex characters of
``HMAC-SHA256(HKDF(AEGIS_SECRET_KEY, salt="aegis.erasure.tombstone.v1", info="erasure-tombstone"), "<kind>:<value>")``.
The kind is in the MAC input, so ``bob`` the host and ``bob`` the user get
different tombstones, and a dump is not an offline oracle for the values because
the key is not in the database. It is stable per deployment (a repeat request
produces the same tombstone, which is how idempotence is visible) and not
reversible by inspection -- but an operator who holds the secret can test
candidate values, so this is pseudonymisation. That is stated in the module
docstring rather than implied, because "hashed, therefore anonymous" is the
mistake that turns a compliance answer into a false claim.

**Which stores are rewritten, and which are named instead.** ``audit_log`` (R-31,
append-only) and ``verdicts`` (D-038's actor history, which exists precisely to
attribute what an account did) are never rewritten; every report lists them as
preserved **with the reason**, so a report cannot be read as a complete inventory
of where a subject's data lives. ``api_keys`` rows are a cascade: the delete is
the schema's own ``ON DELETE CASCADE``, and the in-memory store's ``erase_owner``
models it (``revoke`` is the other operation, and it keeps the row).

**Idempotence comes from the ledger, not from the targets.** The ledger is
append-only, holds tombstones -- never identifiers -- plus per-target counts and
the authenticated ``requested_by``, and a repeat request for a tombstone already
in it returns ``already_erased`` with zero affected, **no ledger append and no
second audit row**. A client that retries a privacy request must not be able to
fill the trail with copies of it, and the ledger is the record of what happened,
so a second entry would be a false one. One identifier *is* in the ledger and the
trail -- ``requested_by`` -- because R-37 requires the action to be attributable;
that trade-off is named, not hidden.

**Where the identifier can appear, which is nowhere durable.** It arrives in one
request body, is in the process for the length of one call, and the response
carries the tombstone instead. No store keeps it (the entity row is redacted, the
user row is gone), no audit detail holds it, no ledger entry holds it, and no log
line is given it. The test module asserts this positively -- after a call it scans
the response, the store, the ledger and the trail for the value -- because "we
erased them" is a claim about where the data is *not*.

**Gaps, named.** Both stores are in-memory while no database session is wired
(D-030); ``erasure_ledger`` is a table in the schema with no adapter yet; and the
window where identifiers really do persist is the one D-044 names -- alert and
verdict history -- which is why the erasure report keeps saying so.

### D-046 — Promotion is one call, and a rollback is the reversal of one rather than a promotion (T-315) (2026-10-05)

**Decision.** ``POST /api/v1/models/{model_id}/promote`` makes a version ``active``
and retires the incumbent **in the same operation**. ``POST
/api/v1/models/{kind}/rollback`` reverses the most recent un-reversed promotion of
that kind, also in one call. The two are different operations, not two spellings
of one.

**Why promotion is one call.** Two calls -- promote, then retire the old one --
leave a window in which either two versions of a kind are active or none is. T-212's
registry took the same position, and FR-33's "no redeploy" is about exactly this
swap.

**Why a rollback is not a promotion.** ``model_status`` has no path back from
``retired``, deliberately: the set of versions that have ever served traffic must
stay append-only, so R-68's prohibition on reuse holds and a retired artifact is
never quietly re-qualified. A rollback is the *reversal of a promotion*, so it is
modelled as one: it re-activates the version that the current one displaced and
retires the current one. **The caller names the kind, not a version**, which is what
makes it one call and un-fakeable -- an operator cannot roll back to a version that
never served, and the previous version comes from the service's own history rather
than from the caller's memory. A second rollback moves one promotion further back,
because the reversal is recorded by marking the promotion it reversed (the schema's
own ``model_versions_history.rolled_back_at``) rather than by appending a second
transition; a kind whose active version displaced nothing has nothing older, and
that is a 409 rather than a guess.

**Authority.** R-53 already names a ``models`` capability and gives it to ``admin``
alone, so promotion and rollback use it and no new capability was invented. Reads
need only ``Capability.READ``: which model is serving, and what it scored, is
operational information an analyst needs to interpret an alert. A machine credential
cannot promote anything -- T-313's route table does not accept keys here -- and the
matrix rows say the same thing the tests assert behaviourally.

**What is recorded.** Each transition appends one audit row when it changes
something, carrying ids, kind and status. The justification for a promotion and the
reason for a rollback are required by the request, stored on the version and
returned in the response, and are **deliberately absent from the trail**: the trail
is readable by every role and notes do not belong in it (R-58, and T-309's precedent
for analyst notes). A promotion of the version that is already active changes
nothing, returns ``changed=false`` and writes **no** row, so a retrying client cannot
fill the trail with copies of one decision (D-041).

**Refusals are shaped by their remedy.** A floating id is ``400`` and names R-68,
because "``latest`` is forbidden" and "no such version" have different fixes; a
retired version or one with no training manifest is ``409``, because the request is
well formed and the conflict is with the version's own state (R-63 gates promotion,
not registration -- an unmanifested artifact can be listed and staged); an unknown
version is ``404``; an unknown kind or a blank note is ``400``; an unknown filter is
``422`` rather than a filter that silently matches nothing.

**Gaps, named.** Shadow mode is design.md's default promotion target and is **not
modelled**: ``model_status`` has no ``shadow`` value, and architecture.md §9's
staging → shadow-score → active step is T-213's harness with no scheduling decision
yet made about who runs the comparison. The promotion modal's "type the model id"
confirmation is T-409's. The durable ``models`` and ``model_versions_history`` tables
have no adapter while no database session is wired into the request path (D-030).

### D-047 — The backend restates the registry's rules at the edge, and refuses to invent a version or a metric (T-315) (2026-10-05)

**Decision.** ``app/services/model_ops.py`` holds the API-side model of the registry:
the versions a deployment serves, their recorded metrics, and the promote/rollback
transitions. It is pure -- no FastAPI, no HTTP client -- and it starts **empty**.

**The registry in ``ml-service`` is still the authority.** The backend cannot import
``aegis_ml`` (it is not a dependency of this service) and no client to the model
service exists, so the rules R-68 needs are restated here and the in-memory service
is the deployment's state until a client replaces it. What the restatement buys is
that a request is refused *before* a round trip with the right remedy: ``latest`` is a
400 naming R-68, not a 404. What it costs is named rather than hidden -- two
implementations of the same rules can drift, and the registry remains the authority,
not this module.

**Nothing is invented.** R-74 makes an unsourced number an honesty defect, so the
registry is empty at startup and a version is registered explicitly. A metric cannot
be built from a value alone: :class:`MetricPoint` names the artifact and the field
the value was read from, :class:`ModelMetrics` refuses a set that is missing any of
FR-31's five metrics (precision, recall, f1, roc_auc, pr_auc) or that names no split,
and a value outside ``[0, 1]`` is refused because every one of those metrics is a
proportion -- anything else is a units bug or a fabrication. A version with no
recorded evaluation renders as a gap rather than a zero: the listing shows
``metrics: null``, and the metrics route answers 404 saying the version *is*
registered but unmeasured, which is a fact about the model and not a missing record.

**Content addressing is enforced at the edge too.** A version's ``sha256`` must be 64
lowercase hex, and re-registering an id against different bytes is refused with both
addresses named. The check is duplicated from T-212 on purpose: an id that silently
changed content is the supply-chain failure R-68 exists to prevent, and it is cheap
to refuse at the edge.

**Gaps, named.** No client to the model service (so ``model_ops`` is in-memory and
``main.py`` says so); no ``shadow`` status; and the ``models``/
``model_versions_history`` tables are unadapted while no session is wired (D-030).

### D-048 — R-56 is a coverage rule, and the limiter answers before routing (T-316) (2026-10-05)

**Decision.** R-56 ("rate limiting on every unauthenticated and every write
endpoint") is read as a *coverage* rule rather than a rate to tune. The scope is
written down once, in ``app/services/limits.py``: every write method (POST, PUT,
PATCH, DELETE) and every unauthenticated route (``/healthz``, ``/readyz``,
``/openapi.json``, ``/docs``, ``/docs/oauth2-redirect``, ``/redoc``).
``EXEMPT_ROUTES`` is empty and asserted empty, because an exemption is how a
coverage rule stops being one; an exemption needs a decision recorded here first.

**The rule is checked against the application, not against a list.** A test
compares the literals with ``UNAUTHENTICATED_ROUTES | DOC_ROUTES`` from
``app.auth.rbac`` -- the literals are repeated in the service layer because
``app.services`` must not import the HTTP layer (R-15), so the test is what binds
them -- and another walks the built application, collecting every method/path the
route table exposes and requiring each write and each unauthenticated route to be
in scope. A new write endpoint is covered the moment it exists, and an endpoint
that is *not* covered fails the suite rather than production. The walk is proven
non-vacuous in both directions: planted write and unauthenticated routes are
asserted to be limited, and an authenticated read is asserted **not** to be, so
"everything is limited" is not a passing implementation.

**Identity is a keyed fingerprint or the peer address, never a header.** A
credential (API key or bearer token) is turned into an HKDF-SHA256 fingerprint --
``salt=b"aegis.ratelimit.fingerprint.v1"``, ``info=b"rate-limit-fingerprint"``,
deliberately a different purpose from the api-key digest's (D-042) so the two can
never be cross-matched even if both were leaked -- and the raw credential is
never stored, logged or echoed (R-58). A request with no credential is bucketed by
the address the kernel reports in the ASGI scope. ``X-Forwarded-For`` is *not*
consulted: it is attacker-controlled unless a trusted proxy is known to set it,
and a limiter keyed on a spoofable value is worse than one keyed on nothing,
since a client could rotate the header for a fresh bucket per request.

**Two rates, one bucket per identity:** 600 requests per minute for a credential
(an API key or a token) and 120 for an anonymous address, both settings. A request
with a credential is judged by that credential's bucket alone -- a shared office
address must not make two collectors compete -- and a request without one never
spends somebody else's allowance.

**Bucket semantics, each chosen for a reason.** A bucket starts full, so a fresh
client is not throttled before it has done anything and a restart is not a
punishment. It refills by elapsed time at ``per_minute / 60`` per second, capped
at capacity, so an idle client may burst a minute's worth and a hammering one gets
the same long-run rate; the client that has been waiting earns tokens while it
waits. A refused request consumes nothing, so a client retrying inside the window
neither extends its own wait nor is pre-charged for it. ``Retry-After`` is whole
seconds (RFC 9110), **rounded up** and never zero: truncating would make every
refusal a promise the client can disprove. Buckets idle past 600 s are dropped
when a new identity arrives -- they are full again by then, so nothing observable
is lost -- and the table is capped, evicting the least recently used identity, so
rotating identities cannot turn the limiter into a memory leak.

**Where it runs, and what it is not built on.** The limiter is a pure-ASGI
middleware, installed inside ``RequestIdMiddleware`` (the last one added is
outermost), so a refusal still carries ``X-Request-ID`` and can be traced.
``BaseHTTPMiddleware`` is not used: it holds response messages until more arrive,
which is exactly why T-310's stream avoided it, and a limiter built on the base
class would stall a long-lived SSE response. Running before routing is also why a
429 costs nothing downstream: no dependency, no store, no audit row.

**Reads that need a credential are out of scope** -- unless the path is one of the
unauthenticated ones. They are cheap, they are already gated by a token, and the
alert stream is a long-lived connection that must not be counted as traffic while
it stays open.

**Gaps, named.** Buckets live in the process: a multi-worker deployment gives each
worker its own allowance, so the effective limit is the configured rate times the
worker count (a shared store is the fix; Redis is not chosen here). The anonymous
identity is the peer address, so clients behind one NAT share a bucket by design.
The limiter is not applied to the WebSocket/SSE stream, which is a decision rather
than an omission.

### D-049 — Limits refuse explicitly: 413 before parsing, 503 with Retry-After for a full buffer (T-316) (2026-10-05)

**Decision.** Two request limits that had never been enforced are enforced now, and
"back-pressure" (architecture.md §12: *explicit back-pressure, never silent
drops*) is modelled as a refusal rather than as a queue.

**The byte cap refuses before any parser runs.** ``max_request_bytes`` existed as
configuration with nothing reading it. A request whose declared
``Content-Length`` is over the cap is answered **413 without reading the body**.
A body that arrives without a length, or with one that lies, is counted as it
streams: the middleware wraps ``receive`` and answers 413 the moment the running
total crosses the cap, so no parser is handed more than the cap. The header check
is an optimisation for honest clients; the count is the control, and a test drives
chunks through the middleware directly because the ASGI test client materialises a
streamed body into a single message -- counting only on the last chunk would pass
an integration test and fail a real upload. The refusal carries
``connection: close``: the rest of the body was never read, so the connection
cannot be reused, and saying so stops an intermediary from trying. The cap is
scoped to POST, PUT and PATCH; a body on a read is unusual enough that policing it
would break an odd client for nothing.

**This is a different limit from the record-count 413.** ``BatchTooLarge``
(``max_flow_batch``/``max_log_batch``) refuses a body that parsed into too many
*records* and names the counts; the byte cap refuses a body that is too large to
parse at all and names the cap. They are kept distinct -- one is about the work the
payload implies, the other about the request itself -- and both say so where they
live.

**A full buffer refuses the batch whole.** The ingest route takes the *accepted*
record count from an ``AdmissionController`` and answers **503 with
``Retry-After``** when the batch does not fit, rather than admitting the part that
fits and failing the request: a partial accept followed by an error is the silent
partial write the audit trail exists to prevent, and the client is told to retry
rather than left to guess. Only accepted records are charged (rejected records cost
the buffer nothing), and the budget is released in a ``finally`` so a route that
raises still gives it back. Per D-039 the budget is held for the duration of the
request until the producer exists; when a producer is wired it is released on
delivery instead, and that is the wiring's decision to make. ``retry_after()``
returns one second: the budget is released as work completes, and a longer wait
computed from a backlog with no arrival-rate estimate would be a fabricated number.

**The seam fails loudly.** ``admission`` raises when no controller is installed
rather than returning a default: an ingest path with no budget would accept
everything and drop it later, which is precisely the silent-loss failure the
architecture names. A test asserts the refusal.

**Ordering and testability.** Both middlewares are pure ASGI and are installed
inside ``RequestIdMiddleware``, so a 429 or a 413 still carries a request id. The
live policy and the byte cap are published on ``app.state`` as well as passed to
the middleware, so a test can tighten a limit on a built application instead of
rebuilding it, and the wiring is asserted against the setting end to end.

### D-050 — The metric names are the architecture's, the labels are a closed vocabulary, and the scrape is unauthenticated on purpose (T-317) (2026-10-05)

**Decision.** ``app/observability/metrics.py`` registers the names architecture.md
§13 lists -- ``aegis_flows_ingested_total``, ``aegis_score_latency_seconds``,
``aegis_alerts_created_total``, ``aegis_drift_psi`` (``aegis_kafka_consumer_lag``
already existed in :mod:`app.messaging.lag`) -- plus this process's golden signals,
on the default ``REGISTRY``. A dashboard is written against a *name*, so a name
that is approximated is a panel that silently shows nothing: a test reads the
names back from the registry and asserts they are the documented ones, and the
exposed name rather than the client's internal ``_name``, which drops the
``_total`` a counter adds to its samples.

**Labels are a closed vocabulary, not free-form text.** Every label is either a
constant this code chooses (``modality``, ``stage``, ``severity``, ``status``) or
the **route template** after routing, and a request that matched no route lands on
one ``unmatched`` series. A label taken from the request is a memory-growth vector
-- one series per path an attacker invents -- which is why the template is read
from the scope *after* the application has run, and why
:func:`~app.observability.metrics.metric_label_names` exists: a test can assert
the whole label set instead of a reviewer noticing a new one. Zero counts are
skipped, so a stage that never refused anything costs no series; the counter's unit
is the **record**, not the pydantic error (one record with three bad fields is one
rejection), and it is charged after validation and admission so nothing counts as
ingested that the buffer refused.

**No identifiers, no content (R-58).** Counters of numbers, histograms of
durations, one gauge of a drift statistic. A test asserts that a scrape taken after
an ingest carries no source address, no token, no family and no host name, which is
what lets the endpoint be readable without disclosing what the service protects.

**``/metrics`` is unauthenticated by decision.** A scraper is a process, not a
person, and the alternatives are worse: a token in the scraper's configuration is a
credential to rotate and leak. It is in ``UNAUTHENTICATED_ROUTES`` *and* in
``LIMITED_UNAUTHENTICATED_ROUTES``, so R-56 covers it like every other
unauthenticated route (the tests assert the exemption set is empty and that the
route is refused once its allowance is spent), and the request middleware skips the
scrape path so the observer never measures itself.

**Gaps, named.** Counters are per-process; a multi-replica deployment scrapes each
replica and sums, which is what Prometheus does. Nothing here alerts -- dashboards
and alert rules are T-505. ``aegis_drift_psi`` has a setter that nothing calls yet;
T-409's drift report is its caller.

### D-051 — One server span per request, the traceparent rides the record, and the collector is configuration (T-317) (2026-10-05)

**Decision.** ``app/observability/tracing.py`` is the process's tracing seam, built
on ``opentelemetry-api``/``-sdk``. The provider is installed once
(``configure_tracing`` is idempotent: OpenTelemetry refuses a second global
provider, and a provider replaced mid-run silently drops the spans the first one
had accepted) and it exports **only** when a deployment names an endpoint -- the
OTLP exporter is an opt-in extra that is not installed here. With no endpoint the
ids are still generated and propagated, which is what the pipeline and the
acceptance criterion need, and nothing leaves the process.

**Propagation is W3C ``traceparent``, both ways.** A valid inbound header continues
the caller's trace; a malformed one is ignored rather than refused, because
refusing a batch of security telemetry over a broken tracing header trades the data
for the telemetry. Every response carries ``traceparent`` and ``x-trace-id``, which
is what makes the id of an ingest request available to the client that sent it.
:func:`~app.observability.tracing.traceparent_for` passes the span's own flag byte
through instead of re-deriving "sampled": masking it to one bit made the header
disagree with the span it described.

**Context is carried explicitly between stages.** The scoring worker and the
correlator do not run inside the ingest request, so the traceparent rides the
record -- a Kafka header in production, the ``ConsumedRecord`` and the score sink
in process -- and each stage rebuilds the parent context from it
(``context_from_traceparent``). A window is attributed to the record that **opened**
it, and a case keeps the trace of the first occurrence that carried one
(``case.traceparent or detection.traceparent``): the question a trace answers is
which request opened the alert. The id is written into the alert's ``window_ref``
-- the pointer to the window the case opened on, already specified as opaque -- and
read back by the query API into ``AlertRow.trace_id``, so the alert record carries
it without a migration. ``Detection.traceparent`` is deliberately **not** part of
the evidence identity, because identity is what makes a replay idempotent and
telemetry must never be able to change it.

**One server span, named by this code.** The middleware opens ``GET request``,
renames it to the route template once the router chose one (a client-chosen path
never becomes a span name), and sets method, route and status. ``correlate
detection`` is a child of the ingest request that produced the window, and ``score
window`` is a child of the same trace in the worker. FastAPI 0.142 traces every
request natively unless it is told otherwise, which would produce a second,
identically named server span per request, a second export path configured from
``OTEL_*`` environment variables rather than from this application's settings, and
framework HTTP metrics competing with the ones §13 names; ``create_app`` therefore
turns the framework's native telemetry off explicitly, and a test asserts that a
request produces exactly one server span. The middleware is pure ASGI and sits
outside the limiters, so a 429 or a 413 is still traced and counted.

**Gaps, named.** No collector is configured in this environment, so propagation is
exercised and export is not. Kafka's per-record trace headers need
:meth:`~app.messaging.producer.FlowProducer.send`'s batch-per-source signature to
change (D-035), so the context is carried on the consumed record and in the sink
but not yet on the wire. There is no ``NOTIFY`` span: the notification payload
carries the alert row and therefore the trace id, but the delivery itself is not
traced. T-318 (structured logs with the trace id) and T-319/T-320 build on this and
are not done here.

### D-052 — R-54 is a mechanism here: an allowlist, a keyed hash, and one line per request (T-318) (2026-10-05)

**Decision.** Logging is structured JSON, one event per line, through structlog --
the library architecture.md selects -- with the console renderer in development and
the JSON renderer everywhere else, and **both go through the redaction processors**:
"human-readable" is not a reason to write a username to disk. Three controls
implement R-54 rather than asking call sites to respect it:

* **The field allowlist.** Every key is checked against a short, written-down set of
  fields this application actually logs. Anything else is **dropped**, including
  nested keys inside a mapping and the keys of a list's mappings. A dropped key is
  not reported in a warning: the *name* of a field can be the identifier
  (``alice@corp: 1``), so naming it would be the leak the drop exists to prevent.
  A test logs through the built application and asserts every key it emits is on
  the list, and that nothing is both allowed and redacted.
* **Identifiers are salted-hashed, secrets are masked.** ``user``, ``username``,
  ``actor``, ``subject``, ``email``, ``host``, ``hostname`` and the address fields
  become ``id:<12 hex>`` under an HKDF-derived key from ``AEGIS_SECRET_KEY``
  (purpose ``aegis.logging.redaction.v1``, distinct from the rate-limit fingerprint
  and the api-key digest so no two can be cross-matched). The relationship survives
  -- the same user is the same name within one deployment -- and the value does
  not. ``token``, ``authorization``, ``api_key``, ``password``, ``secret``,
  ``cookie`` and ``signature`` are ``[redacted]`` outright. Before a secret is
  configured an identifier is ``[redacted]`` too: hashing with a constant key would
  be a lookup table away from the value, which is a fake protection.
* **Free text is scrubbed.** The event name, every string value and the formatted
  exception go through the same scrubber: e-mail addresses (with the TLD optional,
  because an internal login is ``alice@corp`` and a rule requiring a dot walks
  past it), IPv4 and IPv6, bearer tokens and JWTs, and ``user=...``-style
  assignments, which keep the key and hash the value. The same scrub is the last
  step of the stdlib formatter, so records that never reach a structlog processor
  -- uvicorn's access line, a library's warning -- are covered too; a test plants a
  username in an access log and asserts it comes out hashed.

**One line per request, with both correlation ids.** The request observer emits
``event="request"`` with the method, the **route template**, the status and the
duration in milliseconds, plus ``request_id`` (T-304's ``X-Request-ID``) and
``trace_id`` (T-317) from the context. The template and never the path: a path
segment or a query string is where an identifier hides, and a test drives the
application with a planted username in both and asserts neither appears. The level
follows the outcome -- 2xx ``info``, 4xx ``warning``, 5xx ``error`` -- so an alerting
rule can be written against the level without parsing the status. The line lives in
the metrics middleware because that is the only layer that knows the status *and*
the duration while both ids are still bound; tracing therefore sits outside metrics
in the stack, which is asserted.

**The boundary, stated.** Shape cannot identify a hostname or a username: ``the
collector at web-01 is down`` has no pattern to match, and any word could be a
hostname. The control for those is the allowlist -- a hostname reaches a line only
by being bound to a field, and a ``host`` field is hashed. This is a test, so the
boundary is a decision on record rather than a surprise during a review.

**Gaps, named.** Logs go to stdout and no shipping, rotation or retention decision
is made here (that is the deployment's, like the metrics scrape). Alert *content*
is not logged at all -- the allowlist makes that structural, and the audit trail is
the table where content belongs -- so there is no redaction of record bodies to
test. The trace id on a log line is only as good as the propagation behind it, and
that is not yet on the Kafka wire (D-051's gap).

### D-053 — The golden path fakes the systems CI does not have, and a row needs a case id (T-319) (2026-10-05)

**Decision.** R-88's golden test runs the real stages over in-process fakes for the
two systems this environment does not have, and the fakes sit at the *external
system's boundary* rather than above it. `InProcessBus` is a broker -- a log per
topic and partition, offsets assigned on append, headers per record -- and
`FlowConsumer` decodes the `flow@1` payload the producer actually sent, so the
real `FlowProducer` still chooses the partition and the real `ScoringWorker` still
chooses the window. An in-process double that handed over `ConsumedRecord`s
directly would skip exactly the code the test exists to exercise.
`InMemoryAlertStore` is a row store: the query API reads back the same `Alert`
class a persistent adapter will hand it, so `paginate` cannot tell which store it
was given.

**The alert row is keyed by the case, and that is a schema gap.** An incident that
absorbs a repeat refreshes one row instead of appending another -- the row's own
`id` and `created_at` stay, its count and `last_seen` move, its severity can only
escalate. So `AlertStore.save` takes the correlator's case id, which is derived
from data (entity, family, first evidence) and therefore stable across a replay.
The `alerts` table has no column for it and no unique index over the data it is
derived from, so a persistent adapter has nothing to upsert against: it needs a
case-id column (or an equivalent indexed expression) before the seam can be wired.
That is recorded as schema work, in the same shape as T-321's typed columns,
rather than papered over with an insert-then-search.

**Times come from the data.** `ScoreSink.put` now carries `closed_at`, which the
worker fills from `Window.end` -- the last record's timestamp. A detection is
dated from that, not from the worker's clock, because an alert's `first_seen` says
when the traffic happened and a replay stamped with the replay's clock would move
an incident's start time. A sink that is not told refuses rather than inventing
one, and a test asserts the refusal. The consequence is visible in the API: an
alert opened by a 50-flow window carries the *window's close* as `first_seen`, not
the first record's time, which is T-308's documented `Detection.at` semantics
rather than a new choice.

**The trace context now travels on the record's headers.** D-035's gap --
"`FlowProducer.send` is batch-per-source so per-record Kafka trace headers need a
shape change" -- landed here: the broker-client protocol, `FlowProducer.send` and
`send_batch` take an optional header mapping, the ingest route passes the request's
traceparent (which the tracing middleware leaves on the request scope), and the
consumer reads it back into `ConsumedRecord.traceparent`. That is the mechanism
behind T-317's criterion: the id the ingest response returned is the id on every
alert that request opened, asserted through the API rather than at the sink.

**Gaps, named.** The log topic has no publisher and no consumer (the worker is
flow-only). The model-service HTTP call is not exercised -- the scorer is injected,
because no scoring endpoint exists. Family attribution is injected, because no
attributed classifier is wired into ingest. Entity ids are allocated in memory:
`entities.id` is an Identity column the ingest path does not write, so an alert's
`entity_id` is meaningful within one process and nowhere else. And the golden test
is deliberately not a deployment test: it asserts the path that is built, with the
broker and the store faked, which is what R-88 asks for and what a CI runner
without Docker can run.

### D-054 — The reference is generated from the schemas, and the file the build ships is checked (T-320) (2026-10-05)

**Decision.** T-320's reference is *rendered*, never written. `render_reference` in
`backend/app/api/openapi_docs.py` turns the application's own OpenAPI document into
markdown; `scripts/generate_api_reference.py` writes it to the committed root file
`api-reference.md`; and CI runs that script with `--check`, which re-renders the
document in-process and fails when the committed file differs. A route, a field or a
summary cannot change without the published document changing in the same commit, and
the render is a pure function of the schema and the route matrix: paths, methods and
components sorted, no timestamp, exactly one trailing newline.

**Completeness is a rule over the built application, and its exceptions are asserted to
still be necessary.** `documentation_problems` walks every registered route and every
operation in the schema: a route has an operation or a reasoned entry on
`EXEMPT_ROUTES` (the WebSocket route and the framework's own four); an operation has a
summary and a documented success response; a documented response is a schema, a
no-content status (204/205/304) or a declared media type that carries no JSON model;
every body method documents a body unless its path is on `BODYLESS_POSTS`; and every
`$ref` resolves to a component. Two details keep this from becoming a slogan. First, an
exemption that stopped being necessary — the route is documented anyway, the route is
gone, the reason is blank, the bodyless path takes no body or documents one — is itself
a problem, which is how T-316 reads R-56. Second, FastAPI's *empty* schema is not a
schema: it is what a route that declares no response model produces, so `-> Response`
fails rather than passing as "any JSON". Both ingest routes read their bytes
themselves, so FastAPI cannot infer a body: they declare the record model with
`ndjson_batch_body`, and the same declaration folds those models into
`components.schemas` (`declare_components`) so the `$ref`s they produce resolve instead
of naming nothing. The SSE route and the scrape declare `text/event-stream` and
`text/plain`, because the reference has to name the media type the route actually
serves.

**Two consequences of publishing a generated file are recorded rather than
rediscovered.** `api-reference.md` is excluded from prettier, which reflows markdown
tables, and the renderer ends the file with exactly one newline, which is what the
end-of-file hook keeps: a formatter and a drift check that disagree about the same
bytes would fail each other forever. The file is committed as the build's copy of
`/openapi.json`, so reading it needs no running server; it is not deployed to a
documentation site, and the schemas are described as FastAPI renders them — summaries,
descriptions and field types, no prose of their own.

### D-055 — Score columns are fixed-precision, severity is checked, and the migration was applied to a server (T-321) (2026-10-05)

**Decision.** `alerts.score` and `thresholds.value` are `numeric(5, 4)` and
`alerts.severity` carries a check constraint, added by migration `0002_typed_scores`
(R-38, R-39). The Python `Severity` enum moved to `app.db.models` — beside the column
that stores and checks it — and `app.services.correlator` re-exports it, so the bands
are defined once and the constraint is built from the same members: a band cannot be
added without the column accepting it. The migration's constraint text is a literal
rather than an import, because an applied migration must not change when the enum
does; `backend/tests/test_schema_conformance.py` parses the migration and asserts the
literal equals the model's, so the three copies (enum, constraint, migration) cannot
drift apart without a failing test.

**Checked without a server, then with one.** Alembic's `--sql` mode emits the DDL it
would run, so CI asserts that the upgrade types both columns, adds the constraint and
that the downgrade reverses all three — the migration is not merely compiled, it is
compared. T-321's acceptance criterion, that 0.90 round-trips without drift, cannot be
decided by DDL, so it is asserted against a server, and on 2026-10-05 the live suite
was run against a server in this sandbox: pgserver's PostgreSQL 16.2, psycopg 3.3.6
installed into the sandbox only, all **13 live tests passed** — upgrade, downgrade to
base, re-upgrade, both partitioned tables, the composite primary keys, the absence of a
default partition, partition pruning, the audit table's missing foreign key, and the
typed columns' round trip with the severity check refusing `urgent`. D-030 recorded the gap -- the DDL
compiled and checked rather than exercised -- and this run is the one that exercises it
here, from a sandbox install: evidence about the migration, not CI coverage, since the
tests still skip in CI, where there is no server. The offline claims are held by **51 injected
defects, each of which failed its target tests**: the types, the enum members and
their ranks, the constraint's name and text, the re-export, and every statement
in both directions of the migration.

**The driver is a gap, not an assumption.** Nothing in `backend/pyproject.toml`
installs a PostgreSQL driver, and the compose stack's DSN names `asyncpg`, which no
dependency provides, so `alembic upgrade head` cannot run from a plain install. Raised
as **T-323** rather than fixed here: which driver the deployment uses is a decision
(the compose DSN says asyncpg; the verification used psycopg), and the DSN, the
dependency and the live tests should agree on one answer.

### D-056 — The recalibration job fits benign labels in the window the score happened, and the guardrail is T-207's (T-322) (2026-10-05)

**Decision.** FR-18's weekly job is a backend service over an injected store, feedback
source and calibrator, with two routes: `GET /api/v1/thresholds` (the values in force
plus FR-13's documented defaults, R-69) and `POST /api/v1/thresholds/recalibrate`
(admin, one audit row per moved threshold). Four decisions make the acceptance
criteria structural rather than remembered.

**The window is when the score was alerted, not when it was labelled.** Architecture
§7.4 says "a rolling 14-day window of scores that analysts labelled
benign/false-positive"; the score's own time is what describes the traffic the
threshold is applied to next, and a labelling backlog must not re-shape the sample
around stale alerts. The label must exist *as of the run*, so a run replayed for a
past instant sees the verdicts that were in force then — `test_a_verdict_recorded_after_the_run_is_not_visible`.

**Only `benign` and `false_positive` are evidence.** A `true_positive` is evidence
about an attack, and the threshold is a statement about the benign distribution;
mixing the two moves the bar towards the attack scores, which is the
recall-for-quietness trade FR-18 exists to avoid. A family whose labels are all
`true_positive` still appears in the report, refused, so a run says it saw the
family and could not use it — `test_a_true_positive_label_is_not_benign_evidence`.

**Too little feedback means no fit, and the floor is derived, not chosen.** The
calibrator fits the 0.99 quantile (T-207's number, read from the ML package, never
restated here). Below `1/(1-0.99) = 100` samples that quantile *is* the top one or two
order statistics, so a "fit" from twenty scores is a fit from the two loudest
windows. `MIN_FEEDBACK` is asserted to equal that inverse, so the floor and the
quantile cannot drift apart — `test_the_minimum_sample_is_the_inverse_of_the_target_rate`.

**The guardrail is not reachable from the request.** `Calibrator` carries no
guardrail argument, `MlCalibrator` calls T-207's `calibrate` without one (leaving the
0.10 as that function's default), and the request schema forbids extra fields, so
neither a caller nor the backend can widen the movement an acceptance criterion is
about. A clamped move is applied and recorded with both the requested and the applied
value; the requested value is the interesting audit entry, exactly as T-207 argued.

**Two phases, so a refusal is not a partial write.** Every fit runs before any row is
written: a sample the calibrator refuses leaves the store as it was. A fit that lands
on the current value writes nothing and audits nothing — `changed` is what the route
records, and a fit that moved nothing is not a change (D-041).

**The tenant is where the schema is, and the gap is named.** `thresholds` is keyed by
`(tenant_id, family, band)` and so are the store, the report and the audit target.
`alerts` has no tenant column, so `AlertVerdictFeedback` cannot attribute a score to
a tenant and answers `()` for any tenant but the one the deployment was wired with —
a refusal to fit, which is visible, rather than another tenant's traffic in the
sample, which is not. **Gaps:** the run is a route, not a scheduler (no CronJob
exists in `k8s/`), and the store is in-memory while no session is wired (D-030), so
the `thresholds` table's adapter, like every other one, is unwritten.

### D-057 — The PostgreSQL driver is psycopg 3, declared as a runtime dependency, and every DSN names it (T-323) (2026-10-06)

**Decision.** `backend/pyproject.toml` declares `psycopg[binary]>=3.2`, the
application's default URL, `.env.example` and the compose stack all name
`postgresql+psycopg://`, and two guards keep the pair honest: rule 8 of
`scripts/check_compose.py` fails the build when a PostgreSQL URL in the compose file
or in `Settings.database_url` names a driver the backend does not declare, and
`backend/tests/test_database_driver.py` checks every DSN in the repository, the
declared set, and -- in a subprocess -- that the installed driver actually opens each
URL and reports the expected name.

**Why psycopg 3 and not asyncpg.** The DSN names a dialect, and the same URL is
opened by two engines: Alembic's *synchronous* engine at deploy time, and whatever
the request path uses later. `asyncpg` cannot serve the first at all. This was
measured, not assumed: with `asyncpg` installed, `alembic upgrade head` still fails,
because SQLAlchemy routes it through the asyncio shim -- `ImportError: ... requires
that the Python 'greenlet' library is installed`, plus un-awaited coroutine warnings
as the sync engine tries to use an async driver. psycopg 3 serves both halves
(synchronously through `engine_from_config`, and asynchronously through
`create_async_engine` when R-18's session arrives), so one driver is declared, one
dialect is deployed, and no second library can drift in unnoticed. `psycopg[binary]`
carries its own libpq, so `pip install ./backend` needs no system package.

**A URL that names no driver is refused too.** SQLAlchemy's fallback for a bare
`postgresql://` is psycopg2, which nothing here declares: a DSN without a driver is a
driver choice made by a library rather than by this repository, so both guards report
it.

**Verification.** On 2026-10-06, a venv holding nothing but `pip install ./backend`
ran `alembic upgrade head` against pgserver's PostgreSQL 16.2 and reached
`0002_typed_scores (head)` -- the first time the repository's own migration has been
applied from a plain install rather than from a developer venv with hand-installed
extras (D-055 covers the earlier application of the DDL). The 13 live migration tests
passed with the same `postgresql+psycopg://` DSN. Twelve injected defects each failed
their target command: every DSN reverted to `asyncpg` or stripped of its driver, the
dependency removed or swapped, and each branch of the checker including its
invocation.

**Gaps.** The compose stack is not started here -- there is no Docker daemon, so the
criterion is met against the server version the compose file pins (`postgres:16-alpine`)
rather than against its container, and T-005's compose smoke test remains written and
never executed. The request path still has no database session (D-030); when it gets
one it must use `create_async_engine` for R-18, which needs `sqlalchemy[asyncio]`
(greenlet), and nothing declares that yet -- recorded rather than papered over, and
`test_the_installed_driver_opens_every_shipped_url` will keep the sync half honest in
the meantime.

### D-058 — The token layer is a closed system: an off-token colour or an off-scale step compiles to nothing (T-401) (2026-10-06)

**Decision.** design.md §5's tokens live in `src/index.css` (the values, both
themes) and `tailwind.config.js` (the hooks), and the Tailwind scales that
design.md enumerates **replace** Tailwind's defaults rather than extending them:
`colors`, `spacing`, `fontSize` and `fontFamily` are exactly the documented sets,
so `bg-red-500`, `p-5`, `text-lg` and `font-serif` emit no CSS at all. Extend is
used only for the four scales design.md adds to and Tailwind has no default worth
keeping — density rows, icon sizes, the 3 px severity rail, the one overlay shadow.

**Why replace rather than extend.** "Every colour in use resolves to a token" is
not enforceable by review: a stray `bg-slate-700` in a component looks exactly
like a token class, and a review that misses it produces a colour that no theme
switches and no contrast test sees. Closing the scale moves that from a rule
someone remembers to a build failure at the *utility* level: the class names that
could express an off-token value do not exist, and `src/theme/tailwind.test.ts`
compiles the real config and asserts they emit nothing. The same argument closes
spacing (the doc's eight steps and 0), the type scale (the six steps, so the 12 px
floor cannot be undercut by `text-sm`) and the families (two stacks).

**Tailwind's own defaults had to be brought back on-token, and three of them were
off-palette.** A replaced palette leaves preflight and the plugin defaults pointing
at colours that no longer exist: the ring default was blue-300/50 %, the
placeholder default gray-400, and the focus-ring offset white. `borderColor`,
`ringColor`, `ringOffsetColor` and `placeholderColor` therefore carry a token
`DEFAULT` *plus* the colour scale (overriding a scale to change its DEFAULT also
deletes the scale — that mistake cost a passing test in this task: `border-line`
stopped existing). `future.respectDefaultRingColorOpacity` is on because Tailwind
otherwise composites the DEFAULT with an opacity, and a `var()` cannot be
composited: it silently writes the blue fallback instead. Two literals still reach
the stylesheet — Tailwind's `#0000` inside its shadow resets, which is
`transparent`, and preflight's `#9ca3af` placeholder fallback, which
`src/index.css` overrides with the muted token at equal specificity and later
order. Both are asserted, not assumed.

**The document is the specification, so the tests read it.** `tokens.test.ts`
parses design.md §5's tables — colour values, the contrast ratio printed in each
Contrast cell, the badge rule's six ratios, the focus-ring ratios, the type steps,
the spacing and radius steps, the density and icon numbers — and recomputes every
one against the shipped tokens with the WCAG formula. The ratios written as
comments beside each token are checked too, because a stale comment is how a
contrast claim rots. `tailwind.test.ts` then compiles the real config *and* the
real `src/index.css` through PostCSS and asserts on the emitted stylesheet: every
colour utility is a `var(--…)` a theme declares, no colour literal survives
outside the token definitions except the two above, and the numbers compiled for
rows, icons, rail, radii and type are the numbers the document publishes.

**R-27's CSS half is stylelint, as rules.md says.** `color-no-hex`,
`color-named: never` and a ban on `rgb()`/`hsl()` are enabled repo-wide with an
override for `src/index.css` — the token layer is the one file where a literal is
the value rather than a bypass, and its shadow token is an alpha colour that no hex
can express.

**Verification.** 33 new tests (25 token-conformance, 18 Tailwind-compile, 5
density) taking the dashboard from 34 to 67, `tsc`, eslint, stylelint and the vite
build green, and `./scripts/check_all.sh all` 26 checks, 0 failed. **29 injected
defects each failed their target command**: every token pushed below AA in either
theme, a token deleted from one theme, a restated ratio comment, both halves of the
placeholder override, a palette colour added to the scale, a token turned into a
literal, an off-scale spacing step, drifted row/icon/rail numbers, a caption under
the floor, a third font family, the ring default back to blue, a build that scans
nothing, the density threshold moved and made inclusive, and three component-level
smuggles (a palette class, a literal, an inline `rgb()`).

**Gaps, recorded rather than implied.** The shadow's blur and spread are the one
pair of numbers in the token layer design.md does not publish — it fixes the policy
("elevation is reserved for overlays") and this file says so in place. Duration and
easing tokens (§8.2's 120/200/300 ms, `ease-out`/`ease-in`) belong to the task that
first animates something, not here; the "nothing over 300 ms" rule is therefore
documented and not yet closed. Density is *persisted per user* per §5.5 — the
`defaultDensity` helper decides the default, and persisting a choice is T-410's.
The theme toggle exists (T-004) but nothing yet verifies the two themes *render*
identically-clean beyond the axe assertions in the existing component tests.

## Change log

| Date | Version | Change |
|---|---|---|
| 2026-10-06 | 1.46 | **T-401 done — the design tokens are a closed system, and the tests read design.md rather than restating it.** `dashboard/tailwind.config.js`, `dashboard/src/index.css`, `dashboard/src/theme/tokens.test.ts`, `dashboard/src/theme/tailwind.test.ts`, `dashboard/src/theme/density.ts`, `dashboard/.stylelintrc.cjs`. Policy recorded as **D-058**. **Tailwind's colour, spacing, type and family scales now *replace* the defaults instead of extending them**, so `bg-red-500`, `p-5`, `text-lg` and `font-serif` compile to nothing: "every colour in use resolves to a token" becomes a property of the build rather than of a review that misses things. **Three of Tailwind's own defaults were off-palette once the palette was replaced** — the ring was blue-300/50 %, the placeholder gray-400, the ring offset white — and all three now name tokens; overriding a scale to change its DEFAULT also deletes the rest of the scale, which cost a test during the task when `border-line` vanished, so the colour map is defined once and shared. Two literals still reach the stylesheet and are asserted rather than assumed: Tailwind's `#0000` in its shadow resets (`transparent`) and preflight's `#9ca3af` placeholder fallback, which `src/index.css` overrides at equal specificity and later order. **The suite parses design.md §5** — every colour value, every published contrast ratio, the badge rule's six ratios, the focus-ring pair, the type steps, the spacing and radius steps, the density and icon numbers — and recomputes each against the shipped tokens, including the ratios written as comments beside them, because a stale comment is how a contrast claim rots. Then it compiles the real config and the real `src/index.css` through PostCSS and asserts on the emitted stylesheet. **R-27's CSS half is stylelint as rules.md lists it**: hex, named colours and `rgb()`/`hsl()` are banned repo-wide with one override for the token file. **29 injected defects each failed their target command** — both halves of the placeholder override, every token below AA in either theme, a token deleted from one theme, a restated ratio comment, a palette colour added to the scale, a token turned into a literal, an off-scale spacing step, drifted row/icon/rail numbers, a caption under the 12 px floor, a third font family, the ring default back to blue, a build that scans nothing, and three component-level smuggles. Dashboard 34 → 67 tests; `check_all.sh all`: 26 checks, 0 failed. **Gaps:** the overlay shadow's blur and spread are the one pair design.md does not publish (the policy is what it fixes); §8.2's duration and easing tokens belong to the task that first animates something, so "nothing over 300 ms" is documented and not yet closed; and per-user density persistence is T-410's. |
| 2026-10-06 | 1.45 | **T-323 done — the deployment now names a driver it installs.** `backend/pyproject.toml` declares `psycopg[binary]>=3.2`; the `Settings.database_url` default, `backend/.env.example` and `docker/docker-compose.yml` all moved from `postgresql+asyncpg://` to `postgresql+psycopg://`; `scripts/check_compose.py` gained rule 8 and `backend/tests/test_database_driver.py` 14 tests. Policy recorded as **D-057**. **The task's premise was only half the defect.** Nothing installed a driver, yes -- but installing `asyncpg` would not have fixed the compose DSN either: Alembic's `env.py` builds a *synchronous* engine, and SQLAlchemy refuses an async-only driver there whatever is installed beside it, failing with `greenlet` missing and then un-awaited coroutines. Measured with `asyncpg` installed, before writing any fix. So the driver is psycopg 3: one library for the synchronous engine Alembic uses and for the async engine R-18 will require, shipped as `[binary]` so a plain install needs no system libpq. **A bare `postgresql://` is refused as well** -- SQLAlchemy would silently reach for psycopg2 -- and the guards are two: the compose checker's rule 8 compares the compose URL and the application default against the dependencies the backend declares, and the new test file scans every DSN in the repository and then, in a subprocess, opens an engine on each and asserts the driver the install loaded. The subprocess is not ceremony: importing psycopg in process would leave it in `sys.modules`, where `test_golden.py` asserts the golden path never needs a database client. **`alembic upgrade head` was then run for real from a venv containing nothing but `pip install ./backend`**, reaching `0002_typed_scores (head)` on pgserver's PostgreSQL 16.2 -- the first application of the repository's own migration from a plain install rather than a developer venv -- and the 13 live migration tests passed under the same `postgresql+psycopg://` DSN (D-055 covers the earlier DDL run). **12 injected defects each failed their target command**, including the checker's own invocation, so an unwired rule could not survive. One process finding worth carrying: the battery's first restore rewrote a file from an empty replacement and corrupted two of them -- a mutation that deletes a line must be restored from a snapshot of the bytes, and the second run verified all five mutated files by hash afterwards. Backend 1213 -> 1227 tests (13 skipped), coverage 98.56% -> 98.63%. **Gaps:** the compose stack is still not started here (no Docker daemon), and the request path's session will need `sqlalchemy[asyncio]` when D-030 is closed -- nothing declares it yet. |
| 2026-10-05 | 1.44 | **T-322 done — analyst verdicts now move the thresholds, one guarded step at a time.** `backend/app/services/recalibration.py`, `backend/app/services/ml_calibration.py`, `backend/app/schemas/thresholds.py`, five `ROUTE_MATRIX`/`AUDITED_ROUTES` rows in total across two routes, and 81 new tests (49 service, 32 API). Policy recorded as **D-056**. **The window is the score's, not the label's**: architecture §7.4's rolling fortnight is read over when each alert fired, so a labelling backlog cannot re-shape the sample around stale traffic, and a run replayed for a past instant sees the verdicts that were then in force. **`true_positive` is not benign evidence** — it is evidence about an attack, and a threshold is a statement about the benign distribution — so a family whose labels are all true positives is reported as refused rather than fitted, and never silently dropped from the report. **The sample floor is derived**: below `1/(1-0.99) = 100` scores the fitted 0.99 quantile *is* the top one or two order statistics, so a fit from twenty windows is a fit from its loudest two, and the floor is asserted equal to that inverse so it cannot drift from the quantile. **The guardrail is not reachable from a request**: the injected `Calibrator` has no guardrail parameter, `MlCalibrator` calls T-207's `calibrate` without one, and the request schema forbids extra fields — a caller who could pass 0.5 could remove the criterion. Clamped moves are applied and recorded with both the requested and the applied value, because the requested-and-refused entry is the record of the data disagreeing with the bar. **Fits happen before writes**: a sample the calibrator refuses leaves the store untouched, and a fit that lands on the current value writes and audits nothing (D-041). Both routes are exercised through the real seams — the alert store the query API reads and the ledger the verdict route writes, wired once in the composition root so the job cannot fit on feedback that never arrives. One `AuditAction` was added (`threshold.recalibrate`) and one existing file carried a defect found by the full suite rather than by its own module: `tests/test_schema_conformance.py`'s offline DSN tripped detect-secrets, which the T-321 commit had not seen because the hook only failed once the whole run was clean; it carries the repository's inline allowlist pragma now, and the `MlCalibrator` import moved to `importlib.import_module` so the two mypy configurations (backend-only and scripts) agree without a suppression comment. A third failure was the calendar's: `tests/test_privacy.py` asserted that a hard-coded month lay inside a 400-day retention window, and on 2026-10-06 the window's first day moved from 2025-08-31 to 2025-09-01, leaving the asserted gap outside it -- the month is now derived from today, which is what the window is measured against. **69 injected defects each failed their target tests**, covering the label filter, the sample floor both ways, the window's direction, the stored versus default value, the clamp, the two-phase write, the tenant and band scoping, the page loop and its cap, the audit row per change, the role matrix, the band refusal and the wiring. Two real gaps in the tests were found by that battery rather than by review: a refused family's `previous_was_default` and the *contents* of the missing-package message were both unasserted, and two mutants that looked equivalent turned out to be caught only once another tenant's row and another band's row were given families of their own. Backend 1131 → 1213 tests (13 skipped), coverage 98.52% → 98.56%; 26 checks, 0 failed. **Gaps:** the run is a route, not a scheduler (no CronJob in `k8s/`); the store is in-memory (D-030); and per-tenant feedback needs a tenant on the alert row. |
| 2026-10-05 | 1.43 | **T-321 done — the score columns are fixed-precision, severity is checked, and the migration was applied to a real server.** `backend/alembic/versions/0002_typed_scores_and_severity_check.py`, the `Severity` enum moved to `app.db.models` with the constraint built from it, `alerts.score`/`thresholds.value` typed `Numeric(5, 4)`, a check constraint on `alerts.severity`, and two test modules (10 offline, 13 live). Policy recorded as **D-055**. **The enum is defined once**: the column's check is built from the same members the correlator bands by, so a new band cannot be stored unless the column is migrated with it; the migration keeps a literal — an applied migration must not change when the enum does — and a test parses the migration and asserts the literal equals the model's, so the copies cannot drift apart silently. **The criterion is not DDL**: Alembic's `--sql` mode is asserted for the upgrade (both columns typed, the constraint added) and the downgrade (all three reversed), and the round trip is asserted against a server. That server is a sandbox one -- pgserver's PostgreSQL 16.2 with psycopg 3.3.6 installed there -- against which **all 13 live migration tests passed** — including the ones T-301 wrote and could never run — covering the two partitioned tables, the composite primary keys, the refused default partition, partition pruning, the missing foreign key on `audit_log`, a 0.9 score reading back as exactly 0.9000 with `numeric(5, 4)` declared, and `urgent` refused by `ck_alerts_severity`. Two defects in the new tests were found by running them rather than reading them: `numeric_precision(score)` is not a PostgreSQL function (the declared type comes from `information_schema`), and the round-trip query assumed an empty table, so a repeat run found many rows — it is now keyed on the entity it inserts. Backend 1121 → 1131 tests (13 skipped in CI), coverage 98.52% unchanged, and the check suite stays 26. **51 injected defects each failed their target tests** -- the column types and their decimal behaviour, the enum's members, values and ranks, the constraint's name, table and text, the correlator's re-export, and every statement and cast in both directions of the migration. **Gaps:** nothing in the repository installs a PostgreSQL driver and the compose DSN names one that is not declared, so `alembic upgrade head` cannot run from a plain install — filed as **T-323**; the live tests still skip in CI; and no database session is wired into the request path (D-030), so the stores remain in-memory. |
| 2026-10-05 | 1.42 | **T-320 done — the API reference is rendered from the schemas and the build fails when the committed file drifts.** `backend/app/api/openapi_docs.py` (the coverage rule and the renderer), `scripts/generate_api_reference.py` (the generator the build runs, with `--check`), the committed root `api-reference.md`, a `docs: api reference` check in `check_all.sh`, `openapi_extra` bodies on both ingest routes, the true media types on the SSE and scrape responses, and `declare_components` for the models those bodies reference; 38 tests. Policy recorded as **D-054**. **The rule is over the built application, not over a list someone maintains**: every registered route has an operation or a *reasoned* exemption, every operation has a summary and a success response, every response is a schema, a no-content status or a declared media type that carries no JSON model, every body method documents a body unless it is on `BODYLESS_POSTS`, and every `$ref` resolves — and the exemptions are asserted to still be *needed*, because an exemption nobody removes is how a coverage rule rots (the pattern T-316 set for R-56). **An empty JSON schema is not documentation**: FastAPI emits `{}` for a route that declares no response model, so `-> Response` is told apart from a modelled response rather than passing as "any JSON", and each rule is proved to bite by building applications that break exactly one of them. **The published file cannot drift**: `render_reference` is deterministic (sorted paths, methods and components, no timestamp) and the file ends with exactly one newline, because the end-of-file hook strips a trailing blank line; it is excluded from prettier for the same reason, since a formatter and a drift check that disagree about the same bytes would fail each other forever. **48 injected defects each failed their target tests**, covering every rule and every exemption branch, the declared bodies and their components, the media types, the renderer's ordering, escaping, roles, status filter and trailing newline, and the generator's check, write and default paths; one survivor was a *vacuous* test — it asserted on the first `name` row in the document, which belongs to another schema — and is now scoped to the section it means. Backend 1083 → 1121 tests, coverage 98.43% → 98.52% (`openapi_docs.py` at 100%), and the check suite 25 → 26. **Gaps:** the reference is the repository's copy of `/openapi.json`, nothing publishes it to a documentation site, and the schema is described as FastAPI generates it. |
| 2026-10-05 | 1.41 | **T-319 done — the golden path, and the four seams it needed to exist.** `backend/app/pipeline.py` (in-process bus, `flow@1` consumer, entity ids, the score→detection adapter, the case→row writer), `backend/app/services/alert_store.py` (the `AlertStore` seam and its in-memory implementation), the ingest route publishing what it accepted, the alerts route reading the store, `alert_row_of` shared with the stream, per-record broker headers on the producer, and `closed_at` on the score sink; `backend/tests/test_golden.py`, 11 tests. Policy recorded as **D-053**. **The fakes are at the external system's boundary, not above it:** a broker-shaped log per topic and partition with offsets assigned on append, and the consumer parses the payload the real producer sent, so `partition_for` still decides placement and the worker still decides windows — asserted per partition, not taken from the producer's return value. The alert row is keyed by the correlator's case id, so an absorbed repeat refreshes one row (id and `created_at` stable, count and `last_seen` move) rather than appending a second one for the same incident; the `alerts` table has no case-id column, which is recorded as schema work rather than worked around. **Detection times are the data's**: the sink is handed the window's close time (`Window.end`) and refuses to date a detection from the worker's clock, since a replay would move an incident's start. **The trace context rides the record's headers** — D-035's "batch-per-source needs a shape change" gap landed here — so the id the ingest response returned is the id on every alert that request opened, read back through `GET /api/v1/alerts`. The route now returns 400 rather than 500 for a window it cannot bound, and a missing store is a loud error rather than an empty page. **43 injected defects each failed their target tests**, across the pipeline, the store, both routes, the middleware seam, the producer and the worker; one candidate mutation turned out to be *equivalent* (keying the row on the case's first evidence id behaves identically, because that id is stable for the case) and was replaced with one that keys on the *newest* window, because an equivalent mutant is not a survivor. Backend 1072 → 1083 tests, coverage 98.47% → 98.43% (a 116-line module at 99% and a store at 96%). **Gaps:** the log topic has no publisher or consumer; the scorer, the fusion rule and the family labeler are injected (no scoring endpoint, no attributed classifier); entity ids are allocated in memory because ingest does not write `entities`; a persistent alert store needs a case-id column; and the golden test asserts the path that is built, with the broker and the store faked as R-88 prescribes. |
| 2026-10-05 | 1.40 | **T-318 done — structured logs that cannot carry a username, and one line per request that joins the trace.** `backend/app/core/logging.py` (rewritten around R-54), the request observer's access line, the trace id bound per request, `route_template` made public; 50 tests. Policy recorded as **D-052**. **The rule is enforced, not requested**: a field allowlist drops anything not written down — including a *key* that is itself the identifier, which is why nothing reports a dropped field — identifier fields are salted-hashed under an HKDF key derived from `AEGIS_SECRET_KEY` with a purpose no other subsystem uses, secret fields are `[redacted]`, and every remaining string (the event name, the values, the formatted exception) is scrubbed for e-mail addresses — with the TLD optional, because an internal login is `alice@corp` — addresses, bearer tokens, JWTs and `user=...` assignments. Before a secret is configured an identifier is `[redacted]` rather than hashed with a constant key, which would be a lookup table away from the value. The same scrub is the last step of the stdlib formatter, so uvicorn's own access line is covered as well; the acceptance criterion is asserted by planting the username in a token subject, a query string, a header and an exception message and reading the bytes the process actually wrote — not `structlog.testing.capture_logs`, which replaces the processor chain and would pass with every redaction deleted. **One structured line per request** carries method, the route *template*, status, duration and both correlation ids, at a level that follows the outcome, so a refusal the limiter produced before routing is still logged with its status. **Three defects were found by the tests rather than by reading:** the IPv6 pattern matched clock times, so a loose `two or more hex groups` rule was mangling every ISO timestamp (including the timestamp of the log line itself) and now requires the standard's `::` or all eight groups; `detail` was missing from the allowlist, so a nested mapping was dropped whole; and a test asserting that ids do not leak after a request was **vacuous**, because `asyncio.run` hands its coroutine a copy of the context — a leak is only observable inside the task that made the binding, so the check moved there and the tracing middleware now has its own test driven without the request-id middleware above it. **37 injected defects each failed their target tests**, in a battery that also separates an invalid mutant (a deletion that is a `SyntaxError`) from a survivor. Backend 1022 → 1072 tests, coverage 98.40% → 98.47%. **Gaps:** logs go to stdout and shipping/rotation is the deployment's decision; alert content is never logged (the allowlist makes that structural); a hostname or a bare username in prose has no shape to match, so the allowlist and the hashed `host`/`user` fields are the control, and the boundary is a test rather than an assumption. |
| 2026-10-05 | 1.39 | **T-317 done — the metrics the architecture names and a trace id that survives from ingest to the alert row.** `backend/app/observability/{metrics,tracing}.py`, `GET /metrics`, `MetricsMiddleware`/`TracingMiddleware`, the `otel_exporter_endpoint` setting, `ConsumedRecord.traceparent` and the score sink, the correlator's span and `AlertCase.trace_id`, `window_ref.trace_id` read back as `AlertRow.trace_id`; 60 tests. Policy recorded as **D-050** (metric names, the closed label vocabulary, the unauthenticated scrape) and **D-051** (one server span per request, the traceparent that rides the record, the collector as configuration). **Every name is the architecture's and every label is finite**: the four §13 names plus the golden signals are asserted against the registry, a request that matched no route collapses into one `unmatched` series so a client cannot grow the process by choosing paths, zero counts create no series, the rejection counter's unit is the record rather than the pydantic error, and a scrape is asserted to carry no address, token or alert content (R-58). `/metrics` is unauthenticated **by decision** — a scraper is a process — and is therefore covered by R-56 and skipped by its own measurement. **Tracing is W3C `traceparent`**: the ingest response returns `traceparent` and `x-trace-id`, the context rides the consumed record into the scoring worker and the correlator, and the id a case was opened on is written into the alert's `window_ref` and read back by the query API — the acceptance criterion is asserted end to end through the real components. `traceparent_for` passes the span's flag byte through (masking it to the sampled bit made the header disagree with the span), and a malformed inbound header starts a fresh trace rather than failing the request, because refusing telemetry over telemetry is the wrong trade. **Two real defects were found by driving the framework rather than by reading it:** FastAPI 0.142 traces, measures and logs every request natively, so a request produced two identically named server spans and — the reason it matters — a mutation that removed our own trace-continuation still passed, because the framework was continuing it for us; the application now disables the framework's native telemetry explicitly and a test asserts exactly one server span per request. The second was a zero-count series: `.labels(...)` creates a child even when the count is zero, so "a stage that never refused anything has no series" needed a series assertion, not a value assertion (an absent series reads as zero). **65 injected defects each failed their target tests**, in a battery that first reported a clean sweep while every "kill" was the interpreter refusing to run a script named `-q` — the pytest invocation is now checked against a baseline before any mutation is applied. Backend 966 → 1022 tests, coverage 98.13% → 98.40%. **Gaps:** no collector is configured here (ids propagate, export is unexercised, the OTLP exporter is an opt-in extra), Kafka's per-record trace headers need the producer's batch signature to change (D-035), there is no `NOTIFY` span, and drift PSI has no caller yet (T-409). |
| 2026-10-05 | 1.38 | **T-316 done — limits that refuse before work is done, and a buffer that refuses whole batches.** `backend/app/services/limits.py`, `backend/app/api/middleware.py`, the three limit settings, `app.state.rate_limit_policy`/`max_request_bytes`/`admission` in `create_app`, the `admission` seam and the ingest gate; 75 tests. Policy recorded as **D-048** (R-56 is a coverage rule; identity and bucket semantics) and **D-049** (413 before parsing, 503 with `Retry-After` for a full buffer). **R-56 is read as coverage, not as a rate**: every write method and every unauthenticated route, with `EXEMPT_ROUTES` empty and asserted empty, checked three ways -- the literals equal the union of `UNAUTHENTICATED_ROUTES` and `DOC_ROUTES`, every write and unauthenticated route on the *built* application is in scope, and a planted write route is limited the moment it exists, while an authenticated read is asserted out of scope so "everything is limited" cannot pass. **Identity is an HKDF fingerprint or the peer address**: the fingerprint uses a purpose distinct from the api-key digest's (D-042) so the two can never be cross-matched, the raw credential is never stored or echoed, and `X-Forwarded-For` is deliberately **not** consulted because a spoofable identity is worse than none. Buckets start full, refill at a minute's rate, charge nothing for a refusal, and `Retry-After` is rounded **up** and never zero; buckets idle past 600 s are pruned and the table is capped so rotating identities cannot leak memory. The limiter is pure ASGI and sits inside `RequestIdMiddleware` (a 429 carries the id), never `BaseHTTPMiddleware`, which buffers and would stall T-310's SSE stream. **`max_request_bytes` was configuration nothing read**: it is now enforced before any parser runs -- a declared oversize length is answered 413 without reading the body, and a body with no length or a lying one is counted as it streams -- with `connection: close` because the rest of the body was never read, and kept distinct from `BatchTooLarge`, which is the *record-count* 413. **Back-pressure refuses whole batches**: the ingest route charges an `AdmissionController` for the accepted records and answers 503 with `Retry-After` when they do not fit, because admitting the part that fits and failing the request is the silent partial write the audit trail exists to prevent; only accepted records are charged and the budget is released in a `finally`; the seam raises when unwired rather than defaulting to a budget that accepts everything. **59 injected defects each failed their target tests.** The first run left six alive and the two categories are worth separating: two were *battery* defects (a replacement that is not valid Python inside a list comprehension -- on which the battery reports "error" and counts it as a survivor rather than as a kill -- and a mutation neutralised by the guard above it), and four were real gaps that are now tested (a GET carrying a body, two credentials alternating so neither can reset the other's bucket, a running total that spans chunks, and the configured cap reaching the middleware rather than only `app.state`). **Two mistakes of mine were found by tests rather than by review:** the unauthenticated set was written `/docs/oauth-redirect` where the framework mounts `/docs/oauth2-redirect`, caught by the equality test that exists for exactly that; and the ingest fixture used in the back-pressure tests was a record the API *rejected*, so `accepted` was 0, the gate admitted zero, and four tests passed without exercising it -- the fixture is now valid and the accepted count is asserted, so the gate cannot go unexercised again. Backend 891 → 966 tests, coverage 98.00% → 98.13%; 25 checks, 0 failed. **Gaps:** limits are per-process (a multi-worker deployment gets one allowance per worker; a shared store is not chosen here), the anonymous bucket is shared behind NAT by design, and the budget is held for the request rather than released on delivery to Kafka while the producer does not exist (D-039). |
| 2026-10-05 | 1.37 | **T-315 done — model ops, where promotion is one call and a rollback is the reversal of one.** `backend/app/services/model_ops.py`, `backend/app/schemas/model.py`, `backend/app/api/v1/endpoints/models.py`, four `ROUTE_MATRIX` entries, two `AUDITED_ROUTES` rows and the `model_ops` seam; 74 tests. Policy recorded as **D-046** (promotion, rollback, authority) and **D-047** (the registry authority and R-74 at the edge). **Promotion retires the incumbent in the same call**, because two calls leave a window with either two active versions of a kind or none; **a rollback is not a promotion** -- `model_status` has no path back from `retired` (R-68 keeps the set of versions that have served traffic append-only), so rollback is modelled as the *reversal* of a promotion: it re-activates the version the current one displaced and retires the current one, both in one call. The caller names the **kind**, not a version, so an operator cannot roll back to something that never served, and the predecessor comes from the service's own history. The reversal is recorded by marking the promotion it reversed -- the schema's own `rolled_back_at` -- rather than by appending a second transition, so a second rollback moves one promotion further back instead of bouncing the same two versions, and a kind whose active version displaced nothing answers 409 rather than guessing. Authorisation needed no new capability: R-53 already names a `models` capability and gives it to `admin` alone, so promote and rollback use it while reads only need `READ` (which model is serving is what an analyst interprets an alert with), and a machine credential cannot promote anything because T-313's route table does not accept keys here. **The trail records ids, kind and status only**: the promotion justification and the rollback reason are required by the request, stored on the version and returned, and deliberately absent from the widest-read table (R-58, T-309's precedent); a no-op promotion returns `changed=false` and writes no row, so a retrying client cannot fill the trail. Refusals are shaped by their remedy: 400 for a floating id (naming R-68, since "forbidden" and "not found" have different fixes) and for a blank note or unknown kind, 404 for an unknown version, 409 for a retired version or one without a training manifest (R-63 gates promotion, not registration), 422 for an unknown filter. **R-74 is enforced structurally**: the registry starts empty, a metric cannot be built from a value alone (each names its artifact and field), a set missing any of FR-31's five metrics or naming no split is refused, a value outside [0, 1] is refused as a units bug or a fabrication, and a version with no recorded evaluation renders as a gap -- the metrics route says the version is registered but unmeasured rather than showing a zero. **45 injected defects each failed their target tests**, covering every R-68 refusal, the manifest gate, the incumbent retirement, no-op promotions, the rollback's predecessor and marking, the wrong-actor record, the two audit rows and their absent notes, the 400/404/409/422 mapping, the role matrix, and the seam that must refuse rather than answer with an empty registry. One survivor was real and is now closed: a seam that returned an empty `ModelOpsService` instead of raising would have answered "no models are registered" for a deployment that has some -- a confident wrong answer -- and a test now asserts the refusal. Backend 817 → 891 tests, coverage 97.83% → 98.00%; 25 checks, 0 failed. **Gaps:** shadow mode is design.md's default promotion target and is not modelled (`model_status` has no `shadow`; architecture.md §9's staging → shadow-score → active step is T-213's harness with no scheduling decision yet), the promotion modal's type-the-id confirmation is T-409's, no client to the model service exists (so `model_ops` is in-memory), and the `models`/`model_versions_history` tables are unadapted while no session is wired (D-030). |
| 2026-10-05 | 1.36 | **T-314 done — retention that drops only the months the policy has finished with, and an erasure that says what it did not touch.** `backend/app/services/retention.py`, `backend/app/services/erasure.py`, `backend/app/schemas/privacy.py`, `backend/app/api/v1/endpoints/privacy.py`, the retention settings, `Capability.RETENTION`, four `ROUTE_MATRIX` entries and two `AUDITED_ROUTES` rows; 111 new tests (32 retention, 43 erasure, 31 API, plus the audit-table enumeration). Policy recorded as **D-044** (retention) and **D-045** (erasure). **The boundary is the whole task**: a month may be dropped only when its *end* is at or before the cutoff, so a month that straddles it keeps the rows the policy promised; the equality case (a 399-day window ending exactly on a partition's last day) is asserted on its own, because an implementation using `<` passes every other test while retaining a day more than it claims. Windows are configuration -- 30 days for raw records per FR-05, 400 for alerts and ingest stats -- and an inverted pair (alerts kept shorter than the raw records they came from) fails at startup, not at the first run. The plan is a pure function of policy, today and the catalog, which is what lets the admin preview and the run build it the same way; `missing` months are reported because there is no default partition, and `audit_log` is reported unevictable with its reason (R-31) in every plan rather than omitted. Kafka and Elasticsearch retention are reported as mechanisms, not executed. **Erasure redacts entities and deletes accounts**: a host row stays with a tombstone because alerts reference it, a user row goes because the row *is* the account, and the `api_keys` rows go with it (the schema's own `ON DELETE CASCADE`). The tombstone is an HKDF-keyed HMAC truncated to 32 hex, prefixed `erased:`, kind-separated -- and explicitly a pseudonym rather than anonymisation, since whoever holds the secret can test candidates. `audit_log` and `verdicts` are named as preserved with reasons and never rewritten. **Idempotence comes from the ledger**: a repeat request appends nothing and writes no second audit row, so a client that retries cannot fill the trail; the identifier is in the process for one call and appears in no response, store, ledger entry or audit detail -- asserted by scanning all four. **46 injected defects each failed their target tests**, covering the boundary rule both ways, the cutoff arithmetic, per-table window mapping, the equality and range validations, unevictable reporting, swallowed drop failures, an already-absent partition counted as dropped, unkeyed and kind-blind tombstones, a ledger that ignores its cursor or its own history, a row-deleting entity store, kept API-key rows, a repeat erasure audited twice, the identifier copied into the audit detail or echoed back in the report, an unknown kind guessed instead of refused, a cursor that skips a page, widened matrix rows, a runner seam that reports a clean run, and both audit-table rows. Two survivors in the first run were *equivalent* rather than missed -- stats and alerts shared a window of 400, so mapping one to the other changed nothing, and the matrix's role lists are intent while `require` is the gate -- and were closed by adding the tests that make the difference observable instead of counting them. One battery bug matters more than any mutation: the first run invoked pytest without `-m`, every run exited 2 in milliseconds, and a battery that read a collection error as "the tests failed, so the mutation was killed" reported a 45/45 sweep while proving nothing; it now checks a baseline first and treats a collection error as infrastructure. The pre-commit detect-secrets scan was failing on two pre-existing false positives (the public `aegis_sk_` prefix constant and a JWT-shaped test string); both carry the repository's inline allowlist pragma now. Backend 706 → 817 tests, coverage 97.39% → 97.83%; 25 checks, 0 failed. **Gaps:** the catalog query and the statement runner are seams with no session behind them (D-030), the ledger table has no adapter, and erasure of the raw records that live in Kafka and Elasticsearch is reported, not performed. |
| 2026-10-05 | 1.35 | **T-313 done — scoped API keys, hashed with a key the database does not hold.** `backend/app/auth/api_keys.py`, `backend/app/schemas/api_key.py`, `backend/app/api/v1/endpoints/api_keys.py`, three `ROUTE_MATRIX` entries, `Capability.API_KEYS`, and the `Principal` extension that lets a key authenticate; 110 tests. Policy recorded as **D-042** (storage) and **D-043** (authorisation). **The hashing decision is the interesting one:** `key_hash` is `String(64)` and an Argon2id encoding is far longer, so the task's own bar -- "hashing" -- had to be settled rather than assumed. Argon2id is right for passwords because they are low-entropy and human-chosen; a 256-bit `secrets` key has nothing to guess, and memory-hard verification on every ingest request would be a self-inflicted denial-of-service. So the stored value is **HMAC-SHA256 over the whole presented key under an HKDF-derived key from `AEGIS_SECRET_KEY`** -- 64 hex characters, no migration, and a stolen database is not an offline oracle because the digest key is not in it. The consequence is named: rotating the application secret invalidates every key at once, as it already does for sealed webhook secrets. **The secret is exposed exactly once and this is asserted as an absence**: `ApiKeyOut` has no field for it, the record dataclass has none, the module exposes no name that returns a plaintext, issuing twice yields different strings, and a scan of the store and the audit trail after a create finds neither the key nor its digest. The only recoverable display value is the prefix `aegis_sk_<id>_`. **Only a prefix is stored**, and the MAC covers the id half too, so a key with its id rewritten fails the digest rather than merely missing a lookup; an unknown id is compared against a dummy so "no such key" and "wrong secret" cost the same work (the residual -- which ids exist -- is metadata and is named). **Revocation is a column, never a delete, and it lands on the next request**: verification reads the store every time, there is no cache, and a second revoke keeps the first timestamp. **Authorisation is by scope, not by role:** `API_KEY_ROUTES` is a default-deny table of three routes, and for each one the scope's capabilities must be a subset of the **intersection** of the capabilities of every role the matrix allows there -- so a key cannot outrank the least-privileged human on its own route, and that is asserted rather than intended. Presenting an `Authorization` header *and* an `X-API-Key` is a 401 rather than a precedence rule, since guessing authorises the request with the credential the operator did not mean. **38 injections each failed their target tests** -- including a digest over only the id, a short-circuit that skips the dummy comparison, a revoked key that still resolves, a revoked key that still grants, a second revoke that moves the timestamp, a store that deletes instead of revoking, both SQL guards dropped, a widened `alerts:read`, a key principal that borrows its owner's subject, a listing served with the create schema, a repeated revoke audited again, and an endpoint that silently drops an unknown scope. Two survivors in the first run were equivalent mutants (a no-op `int(int(...))`) and one was a mis-targeted battery entry; the equivalent ones were replaced with real defects rather than counted. **Gaps:** the store is in-memory while no database session is wired into the request path (`api_keys` has its table and index in migration 0001, so this is the same adapter gap D-030 names, not a schema one); `owner_id` wants the numeric `users.id` the opaque subject cannot supply (D-038); per-key rate limiting is T-316; and the `/admin/keys` screen is T-410's. Backend 596 → 706 tests, coverage 96.89% → 97.39%. |
| 2026-10-05 | 1.34 | **Environment reset, and the tree re-verified rather than assumed.** The sandbox was recreated between sessions: `.venv`, `dashboard/node_modules` and the local git history were gone, and `.git` was the initial shallow clone at `04aeb71` again. **The working tree was intact** — every E3 file, test and documentation edit unchanged — but `a2c29e1` (T-308), `b6975f4` (T-309), `c6eacd4` (T-310) and `34dc7ff` (T-311) no longer exist here and were never pushed (the branch has no upstream), so **`415a5b1`** re-establishes their content: one commit standing in for four, and the per-task commit boundaries are gone with them. No file content changed, so every recorded measurement still describes what is on disk. The Python environment was then rebuilt from `backend/pyproject.toml` (which is also what proves `cryptography>=44` is declared rather than hand-installed) and the dashboard dependencies from `package.json`, and the full suite re-run to 25 checks / 0 failed before T-312 began. |
| 2026-10-05 | 1.33 | **T-312 done — the audit trail, append-only and complete over mutating routes.** `backend/app/services/audit_log.py`, `backend/app/schemas/audit.py`, `backend/app/api/v1/endpoints/audit.py`, `backend/app/api/v1/deps.py`, one `ROUTE_MATRIX` entry, 72 tests. Policy recorded as **D-041**. **R-31 is asserted three ways** — the mapper, the trail object and the protocol are each walked for a mutating name, and the record handed back is frozen with its `detail` in a read-only view, because freezing the field alone leaves the dict it points at editable; a source-level test asserts no `update(AuditLog)`, `delete(AuditLog)` or `on_conflict_do_update` exists in the module, which is the strongest form available without a server. **FR-42's completeness clause is a table plus a walk of the built app**: every `POST`/`PUT`/`PATCH`/`DELETE` route must be in `AUDITED_ROUTES` or the deliberately-empty `AUDIT_EXEMPT_ROUTES`, proved non-vacuous and proved by planting an uncovered route. **The trail records changes, not requests** — a 4xx writes nothing, an ingest batch that accepted zero records writes nothing, and a verdict re-sent unchanged writes nothing, while a partly-bad batch records both counts and is the only trace of what was refused. **The trail is the widest-read thing in the system and carries the least**: a webhook's URL or host, an analyst's note, a signing secret and any record content are each asserted absent by planting them, and the actor column is documented as needing the `users.id` mapping D-038 names. The source IP is `request.client`, never `X-Forwarded-For`, with the proxy caveat named as deployment configuration. Reads require `start`/`end`, are capped at the repository's own `MAX_QUERY_SPAN_DAYS`, page on an exclusive id cursor, and the *compiled SQL* — not just the Python guard — is asserted to carry both bounds. **35 injections each failed their target tests**, including the SQL losing its time bound (which survived the first battery and added the compiled-statement test), a trail that grows `update`, a re-sent verdict audited, the webhook host or the analyst note mirrored in, and a header-read client IP. **Gaps:** the persistent trail is unwritten and un-migrated, the in-memory one dies with the process, and the admin screen and audited export (FR-43) are later work. Backend 524 → 596 tests, coverage 96.41% → 96.89%. |
| 2026-10-05 | 1.32 | **T-311 done — outbound webhooks, signed over the bytes that were sent and re-checked per attempt.** `backend/app/services/webhook_targets.py`, `backend/app/services/webhook_delivery.py`, `backend/app/schemas/webhook.py`, `backend/app/api/v1/endpoints/webhooks.py`, three `ROUTE_MATRIX` entries, 149 tests. Policy recorded as **D-040**: the signature is `t=<unix>,v1=<hmac-sha256 hex>` over `"<timestamp>.<body>"` with the body canonicalised once and the exact bytes sent; one timestamp, signature and delivery id per delivery so a retry is not re-signed into a second event; the default 15 s retry budget sits inside the 300 s replay window and a test asserts that; full jitter; 5xx/408/425/429/3xx retried and other 4xx not, because the receiver already refused those bytes; and **the destination is validated before every attempt and the transport is given the pinned address**, since a host that resolved public at registration is what a rebinding attack waits for. **The smoke matrix found what reading would not: CPython reports IPv4 multicast (224/4) as globally routable**, so `224.0.0.1` passed the first verdict function — the multicast refusal now precedes the `is_global` accept and a test names it. Secrets are 32 random bytes sealed with Fernet under an HKDF-SHA256 key from `AEGIS_SECRET_KEY`, returned once and never readable again; the allowlist is empty by default (fail-closed) and parsed at startup; and the log carries the target id, attempt, outcome and status and **never the URL, the operator note or the alert body** (R-58 asserted by planting all three). 30 injections each failed their target tests — including the multicast/private/CGNAT accepts, a rebinding target sent anyway, an unreadable secret returning `""`, 5xx not retried, a refusal retried as an overload, the replay window unchecked, the timestamp out of the MAC, a per-attempt delivery id, the hostname dialled instead of the pinned address, an exclusive floor, every delivery counted as delivered, the URL/description/body logged, jitter ignored and the retry bound off by one. **Gaps:** no HTTP client ships (a protocol, not an implementation); retries are inline, so a delivery queue is what a busy pipeline needs; the store is in-memory; and nothing calls `dispatch()` yet — the correlator is not wired to T-310's hub either. Backend 375 → 524 tests, coverage 95.67% → 96.41%. **One earlier verification claim corrected by this run:** `hooks: pre-commit` reported green at T-310 does not reproduce on this tree — `detect-secrets` flags a test-only settings literal in `backend/tests/test_alert_stream.py:334`, a file **byte-identical to `c6eacd4`**, plus three test-only fixtures added here (two application-secret constants and two `user:pass@` URLs that exist to be refused). Each is marked inline with `pragma: allowlist secret` at the line rather than added to `.secrets.baseline`, so a reviewer sees the claim where the literal is. Bandit's B311 on the delivery id was a real finding about the wrong tool: the id is now drawn from `secrets` rather than `random`. |
| 2026-10-05 | 1.31 | **T-310 done — the alert stream, with the gap made visible.** `backend/app/services/alert_stream.py`, `backend/app/schemas/stream.py`, `backend/app/api/v1/endpoints/stream.py`, three `ROUTE_MATRIX` entries, 50 tests. Notification sequences give the fallback something to resume from: `WS /alerts/ws`, SSE with `Last-Event-ID`, and the REST polling endpoint at architecture.md §14's 15 s cadence. Policy recorded as **D-039** — a cursor out of step in either direction gets `resync_required` plus the whole retained window, a slow consumer is dropped with its resume cursor, cursor 0 means "no position yet", the cursor is per-process and comes with an epoch, and `publish()` is thread-safe because the producer is the scoring worker rather than the event loop. **Two defects were found by tests, not by reading.** The reader task must check for `websocket.disconnect` explicitly, because a server that hands the message back turns the reader into a busy loop; and `RequestIdMiddleware` had to become **pure ASGI**, since `BaseHTTPMiddleware` holds response chunks in a task group and an endless SSE response therefore never reaches the client. **Harness facts recorded for the next stream task:** Starlette's `TestClient` runs the app to completion before returning a response, so an endless stream cannot be read through it — the SSE tests drive the ASGI app directly — and a `receive` that returns immediately starves the event loop (that is how the first version hung rather than failed). 15 injections each failed their target tests: inline (non-loop) delivery, either half of the resync rule, a tail instead of the window on resync, an undetected full queue, no drop check before waiting, delivery to one subscriber, an ignored disconnect, SSE frames without ids, the resume header ignored or tolerated when malformed, header-only socket auth, 4401/4403 swapped, an accepted unauthorised handshake, accept-before-authenticate, and shutdown that leaves the hub open. **Gaps:** the in-process buffer does not survive a restart, so multi-replica needs a shared bus; uvicorn needs the new `ws` extra to serve the socket, and it is not installed here. Backend 325 → 375 tests, coverage 95.67%. |
| 2026-10-05 | 1.30 | **T-309 done — analyst feedback is an append-only ledger, not a mutable field.** `backend/app/services/verdict_service.py`, `backend/app/schemas/verdict.py`, `POST /api/v1/alerts/{alert_id}/verdict` + `GET .../verdicts`, two `ROUTE_MATRIX` entries, 42 tests. The acceptance criterion is tested against the store rather than the return value: the first record still reads exactly as written after a supersession, and the interface is asserted to expose `current`/`history`/`append` and nothing else -- no update, no delete -- the way R-31 is asserted for `audit_log`. **A repeat is not a supersession** (D-038): the same verdict by the same analyst returns `unchanged` and appends nothing, so a client retry cannot manufacture a reconsideration; a different verdict, or the same verdict from a different analyst, appends and links `supersedes` to the previous record; `alert_verdict_update` returns `None` for `unchanged`, because writing `verdict_at` forward on a re-send would make a repeat look like a fresh decision. Alerts are addressed by `(id, created_at)` -- D-030's partition key, required rather than defaulted -- and a test proves `12:00+02:00` and `10:00Z` address the same alert. `require()` now returns a `Principal` (role + token subject) so the route records **who** decided without decoding the bearer token twice; viewer is refused by capability and absent from the matrix entry, with a parity test over all four roles. **Nine injections each failed their target tests:** an actor-blind repeat check, a removed unchanged short-circuit, a dropped `supersedes` link, off-by-one ids, an unstripped note, a write on `unchanged`, a viewer in the matrix, a placeholder actor, and a route that ignored the body's partition key. **Gaps named:** the durable half needs a new append-only table and a migration (the schema's `alerts.verdict` holds only the current decision) and a mapping from the token's opaque `sub` to `alerts.verdict_by`'s numeric `users.id`; audit rows for mutating routes are T-312's. Backend 283 → 325 tests, coverage 96.03%. FR-18's weekly recalibration job is filed as **T-322** — this task persists what it consumes. |
| 2026-10-05 | 1.29 | **T-308 done — the alert path now runs from detection to row.** `backend/app/services/correlator.py` + 71 tests. The acceptance criterion is verified by counting rows in the store rather than reading the returned action, because an implementation that reports `absorbed` and inserts anyway passes the weaker test. Banding treats published thresholds as inclusive boundaries and refuses an out-of-range score instead of clamping it; the bounds are data (R-69). The composite is fused from the best score per modality through the **injected** real `aegis_ml.scoring.fusion` rule — one implementation of the arithmetic, wired at the composition root, since the backend image does not install the ML package. Policy recorded as **D-037**: cool-down measured from `last_seen` and inclusive at the boundary, a case that never de-escalates, grouping by entity + opposite modality ±60 s which clears `partial_evidence`, closed cases that absorb nothing, and replay safety keyed on the window's evidence id with an evidence index that outlives display retention. **One clause was vacuous until injection proved it** — `max(case.score, fused.score)` could be replaced by `fused.score` and the original de-escalation tests still passed, because the best per modality only falls when retention evicts the loudest occurrence; that test was added, and four other injections (zero-width cool-down, removed replay check, same-modality grouping, exclusive band boundary) each failed their target tests. `CaseStore` is the persistence boundary and `alert_row()` pins the encoding; the SQL adapter is the named gap. Also found while writing the row mapping and raised as **T-321**, not fixed here: `alerts.score`/`thresholds.value` are `Float` and `severity` is an unconstrained `String(20)`, against R-39 and R-38. Backend 212 → 283 tests, coverage 95.81%. |
| 2026-10-05 | 1.28 | **T-307 done.** `backend/app/workers/scoring_worker.py`. Loss and duplicates pull in opposite directions — commit before the work is at-most-once and loses records on a crash, commit after is at-least-once and replays them — so the worker commits **after** emitting and gets "no duplicates" from the other end: emission is idempotent per window identity. Two bugs, both found by tests rather than by reading. Windowing each batch independently restarted the numbering, so batch two's first window silently **overwrote** batch one's — the idempotent sink that makes replay safe became the thing hiding the loss — and batch sizes 3/7/50 produced 1, 2 and 4 windows from the same 20 records. A window counter held in worker memory then collided across restarts, passing every test that stays inside one process lifetime. Identity is now the entity plus the **log offset of the window's first record**: a property of the data, not of the process (D-036). My own test asserted the opposite and had to be reversed. The windower is shared with `aegis_ml` rather than reimplemented, so the two cannot number windows differently. **Gap:** ml-service still exposes only `/healthz`, so the model call behind `Scorer` is injected and untested. 16 tests. |
| 2026-10-05 | 1.27 | **T-306 done.** `backend/app/messaging/{partitioner,producer,lag}.py`. Ordering is a **partition-assignment** property, not a broker guarantee: two flows from one source on different partitions have no ordering however correct the broker is. The partitioner therefore delegates to Kafka's own `DefaultPartitioner` rather than reimplementing a hash that would agree in tests and disagree in production, and keys on `src_ip` alone — a port or timestamp in the key would split one entity and lose exactly what this exists to provide. Resume is `committed + 1`; the committed offset reprocesses and the log end skips. Lag is per `(group, topic, partition)`, because one stuck partition averages away into a healthy-looking total, and clamps at zero since retention can delete records a consumer never reached (D-035). **No broker exists here**, so the arithmetic is tested and the broker call is a one-line injection point that is not. 26 tests. |
| 2026-10-05 | 1.26 | **T-305 done.** Q-02 recorded before the work, as the row required — D-034 chooses partitioned PostgreSQL and defers Elasticsearch, on the asymmetry that being wrong about Postgres costs a later migration while being wrong about Elasticsearch costs a second store from day one. Pagination is keyset on `(created_at, id)`, because offset pagination cannot be stable under concurrent inserts and `id` alone is not unique across partitions (D-030); the cursor compares as a **row value**, since `created_at < a AND id < b` silently drops rows that share the cursor's timestamp. `start`/`end` are required with no default, because a generous default is how an unbounded partitioned scan ships, and a malformed cursor is a 400 rather than a silent restart from page one. 23 tests. |
| 2026-10-05 | 1.25 | **T-304 done.** `backend/app/schemas/ingest.py`, `services/ingest_service.py`, `api/v1/endpoints/ingest.py`. "No partial batch is silently dropped" is arithmetic rather than a promise: `received == accepted + rejected` with one error entry per rejected record, both halves asserted. An unparseable NDJSON line is a per-record `parse` error, not a whole-batch 415 — my first version failed the batch, which is exactly what FR-04 forbids — and line numbers are carried through the parse rather than recomputed, so "record 7 is bad" still points at record 7. Every pydantic error becomes an entry, so a record with three bad fields explains all three. R-53 does not name ingest, so `Capability.INGEST` was added for analyst/responder/admin and not viewer; recorded as a judgement call, not a reading of the rule (D-033). 34 tests (27 ingest, 7 contract). |
| 2026-10-05 | 1.24 | **T-303 done.** RBAC dependency plus a route × role matrix test. **The first completeness check enforced nothing:** it read `app.routes`, and FastAPI's `include_router` does not flatten — the parent holds a container whose `original_router` holds the real routes — so the walk found four documentation endpoints, concluded the matrix was complete and passed. Two rules follow (D-032): a completeness check that introspects a framework carries a test asserting it sees the things it claims to count, and the "adding a route is detected" test runs against the real app factory rather than a toy `FastAPI()`. RBAC is default-deny from a written-out capability table; a 403 names the caller's role but never the missing capability, and an unknown role string is refused rather than defaulted. 25 tests. |
| 2026-10-05 | 1.23 | **T-302 done.** `backend/app/auth/{passwords,tokens}.py`. R-51 is enforced where verification happens: `verify_password` **raises** on MD5, SHA-1, bcrypt and Argon2i rather than returning False, because False reads as "wrong password" and would turn a migration into an endless stream of login failures instead of a rehash on next login. Refresh rotation is single-use, and replaying a spent token revokes the whole family — two holders of one single-use credential means at least one is not the user. **A test of mine was wrong and the code was right:** I forged a token by editing the payload *and re-signing with the correct key*, which is issuing, not tampering; that a re-signed forgery is accepted is now its own test, because HS256 is a symmetric MAC and the secret is the entire boundary (D-031). `RefreshStore` is a protocol; the in-memory default is explicitly not for production. 28 tests. |
| 2026-10-05 | 1.22 | **T-301 — R-34 clause done and verified; the migration clause is NOT verified here and says so.** `backend/app/db/{models,partitions,repository}.py` + `backend/alembic/`. R-34 is enforced by two layers because either alone has a hole: `query_partitioned` takes the `TimeRange` positionally so no call shape omits it, and `assert_time_bounded` inspects hand-built statements and refuses any partitioned table whose partition column is unconstrained — catching `select(func.count()).select_from(Alert)`, which `column_descriptions` would have missed since it reports `None` for aggregates. Partitioned primary keys must include the partition key, so `id` is not globally unique on `alerts`/`ingest_stats`; no default partition, because one accumulates silently until retention is meaningless. **Honest gap: no PostgreSQL is reachable in this sandbox (no `psql`, 5432 refused, no container runtime) and partitioning is PostgreSQL-only, so "migration up and down apply cleanly" is unverified.** What is verified: all 9 tables compile for the postgres dialect, both partitioned tables emit `PARTITION BY RANGE`, the migration imports with both hooks and `down_revision = None`, and the pure partition builders are unit-tested including December rollover. `audit_log.actor_id` has no foreign key on purpose — a cascade would give an append-only table a delete path. 40 new backend tests, 60 total. |
| 2026-10-05 | 1.21 | **T-215 done.** `training/search.py`. **`search()` has no test-split parameter at all** — train and valid only, with the omission pinned by a test on `inspect.signature`, because a discipline note holds only until someone is in a hurry. R-71's second half is a separately named `final_test_evaluation` so the one permitted look cannot be reached by accident. Selection defaults to ROC-AUC since it is threshold-independent; selecting on F1 at a fixed cut would reward a fortunate threshold rather than better ranking. Every trial logs the complete config, and a test asserts the logged key set equals `TrainingConfig.model_fields` so a new knob cannot go unlogged by default. **A gap recorded rather than hidden:** `TrainingConfig` does not validate `d_model` divisibility by `nhead`, so an incompatible pair passes expansion and fails later at model build. **A bug mypy caught that my tests shared:** both entry points were annotated flat rows where `train` needs windows of timesteps; now a named `Windows` alias. 25 tests. |
| 2026-10-05 | 1.20 | **T-214 done.** `registry/model_card.py` + `scripts/model_card.py`. **A number cannot reach a card without a recorded run behind it:** `SourcedMetric` requires `artifact` and `field` beside the value, `load_metric` reads the value from the file itself, and the CLI's `--metric` takes `NAME=ARTIFACT:FIELD.PATH` with no way to pass a value. Citing an absent field raises `MetricNotFound`, an unrecorded run raises `FileNotFoundError`, both exit 1 — verified end to end. `bool` is refused explicitly since `isinstance(True, int)` is True in Python. A card with no limitations or no adversarial caveat is refused; the default caveat is concrete (padding, rate-limiting below the detection window, splitting across hosts) because a vague one tells an operator nothing. **The card is generated at release, not committed**, since it cites gitignored run artifacts and a committed copy would eventually cite numbers nothing in the repository reproduces. Built a real card from regenerated runs: recall 0.795472, precision 0.590382, ROC-AUC 0.746354 — reproducing D-022 exactly — p95 20.9889 ms, 2562 attack windows, five metrics all cited. 31 tests. |
| 2026-10-05 | 1.19 | **T-213 done.** `scoring/shadow.py`. The harness takes **no alert sink and exposes no publishing method**, so it cannot produce an alert rather than being told not to — a `if shadow_mode: return` guard has to be remembered at every call site and fails open the moment one is added. Structure is pinned by tests: no sink-like constructor parameter, no public name containing publish/alert/notify/emit, and a spy on a real alert sink sees nothing after three windows scored above threshold. "Comparable" is measured with T-211's PSI on the active model's own bins at the same 0.25. Recorded explicitly that a low PSI does not bound disagreement, so `disagreement_rate`, `shadow_alerts` and `active_alerts` are reported too, with a test for the pathological case (active all 0.9, shadow all 0.1 → disagreement 1.0). `compare()` refuses rather than guessing when there is no incumbent or fewer than two paired scores. Three of my own tests were wrong and the code was right; one mypy narrowing error was fixed by restructuring rather than casting. 26 tests. |
| 2026-10-05 | 1.18 | **T-212 done.** Both acceptance clauses enforced in `registry/model_registry.py`. `latest` raises `ForbiddenModelId` rather than `ModelNotLoaded`, because a typo and a forbidden pattern have different remedies; the id is rejected at construction, and `stable`/`current`/`newest` are covered case-insensitively. Promoting a retired model raises `InvalidTransition` naming the remedy, and `retired` has no exit at all. `ModelInfo.sha256` is required and validated as 64 lowercase hex — adding it broke six existing call sites, which were updated rather than given a default that would have satisfied mypy while defeating R-68. Overwriting an id with different bytes raises `ImmutableArtifact` naming both addresses; identical bytes are a no-op, since an unchanged redeploy is ordinary. `verify()` reports whether the artifact on disk still matches. Promotion retires the incumbent in the same call and returns `PromotionResult`, because T-315 needs rollback to be one call. One asymmetry is deliberate and my first test got it wrong: retiring twice is idempotent, promoting a retired model is not. 40 registry tests. |
| 2026-10-05 | 1.17 | **T-211 done.** `scoring/drift.py` + `scripts/drift_report.py`. FR-32's criterion is tested by doing the arithmetic in the test itself — reference (0.5, 0.3, 0.2) against actual (0.4, 0.4, 0.2) gives `−0.1·ln(0.8) + 0.1·ln(4/3) = 0.051082562`, asserted to rel=1e-12 — because a test that builds its own expected value from the function under test passes against a wrong implementation too. Bin edges come from the reference alone (R-62 applied to a different artifact); empty bins are floored, not skipped, with the resulting upper bound pinned by a test; categoricals are never binned. **Measured UNSW→CIC: 20 of 23 features exceed 0.25**, worst `state` 26.6670, `direction` 9.0923, `service` 3.9367; only `fin`, `protocol` and `rst` are stable. The top drifters are exactly the categoricals D-022 blamed for the transfer failure, so a monitor written afterwards independently corroborates that diagnosis. Drift exits 0 by default because a monitor that fails the build on legitimate traffic change gets switched off; `--fail-on-drift` gates. 42 tests. |
| 2026-10-05 | 1.16 | **T-210 done.** ONNX export path. **Agreement: max abs Δ 9.537e-07 / 1.341e-07** on the two heads against a 1e-4 tolerance, ~100× inside it and reproducible run to run — which is why it gates the build. **The latency figure first written here (−0.088 ms) was single-round noise and is corrected:** three further runs gave −1.123, +2.311 and −2.257 ms with the sign flipping. The script now interleaves both backends over `--rounds` and reports the spread; over 5 rounds the delta median is **+1.172 ms** (range −0.975 to +2.224) with ONNX faster in **2 of 5**, so it reports the sign as inconsistent and the backends as the same speed at this resolution. **Two exporter facts found by measurement:** opset must be 18 (torch 2.14 refuses 17 and fails its own downgrade conversion), and **`dynamo=False` is required** because the default exporter specialises the batch dimension and fails above batch 1 on a baked-in Reshape. Fallback is an `onnx` extra, imports cleanly with neither torch nor ONNX present, `load_scorer` returns the backend it chose. 16 tests, 13 passing in a torch-free and ONNX-free interpreter. |
| 2026-10-05 | 1.15 | **T-209 done.** `scripts/inference_benchmark.py` measures both halves. **R-67 determinism passes all four checks** — repeated passes byte-identical, a second instance from the same seed identical, the torch RNG state unchanged by a forward pass, and the weights untouched — compared over raw storage bytes rather than approximate equality. **Latency p95 22.590 ms** per window (1×50×23, 300 passes, 20 warmups discarded) against NFR-01's 150 ms. Recorded honestly: NFR-01 specifies 4 vCPU, this machine has 2, and the script writes `matches_nfr01_reference: false` instead of labelling the figure a 4 vCPU result; the measurement was taken single-threaded, a stricter configuration. Two threads measured *slower* than one on a window this small (p95 28.611 vs 26.609 ms), so the scoring path should pin one thread. Replaced an `assert` in the byte-extraction helper with a `TypeError` — asserts vanish under `python -O`. |
| 2026-10-05 | 1.14 | **T-208 solved; R-66 passes at recall 0.7955 — and D-021's diagnosis was wrong.** Measured the real cause: `family_split(holdout=['Generic'])` leaves the training fold benign-only (`POSITIVES=0` out of 95 windows), so the supervised head that `transfer_eval.py` was scoring could only learn to emit a constant. Switched the transfer signal to the **reconstruction** head via a new `per_window_reconstruction_error` in `flownet.py`, with the operating point fitted target-blind on the source's benign validation scores through T-207 (`0.3622` at the 0.99 quantile). Same split and training run as before, recall goes 0.1725 → **0.7955** and the gate passes. The supervised head had the *higher* AUC (0.9048 vs 0.7464) and the worse recall — a near-constant head still ranks, so AUC rewarded the broken signal. Precision 0.5904 against a 40% attack base rate remains the open problem. D-021 kept, corrected, and marked superseded by D-022. Added 9 tests. |
| 2026-10-04 | 1.13 | **T-208 closed as a measured negative result; R-66 blocks the release.** Training on UNSW-NB15 and scoring CIC-IDS2017 whole, with the source preprocessor and no refit, gives **ROC-AUC 0.9048 but recall 0.0000** at the source's 0.50 threshold — and only 0.0679 recall at 0.05. Ranking transfers; calibration and coverage do not. Two concrete causes are recorded in D-021: CIC's `state` and `service` categoricals never appear in UNSW's vocabulary so both collapse to the reserved unknown column, and CIC's numerics are standardised with UNSW statistics and land far outside the trained range. The gate exits non-zero rather than being tuned into passing. Also fixed durably: E402 is now off for `scripts/` in `ruff.toml`, because black kept re-wrapping long imports and moving the trailing `# noqa` to the closing parenthesis where it suppressed nothing — the third time that broke the docs job. |
| 2026-10-04 | 1.12 | **T-205, T-206 and T-207 closed.** Late fusion is monotonic in both inputs, asserted by sweeping the whole range at five levels of the other modality rather than spot-checking; a missing modality is penalised *and* flagged, because a penalised 0.9 still reads as a confident score. Threshold calibration clamps a run's movement to ±0.10 rather than refusing it — refusing would freeze the threshold the first time the calibration data is unusual — and records the requested value alongside the applied one, since the refused part is the interesting record. D-020 records that `explain()` uses occlusion attribution: attention weights are unreachable through `nn.TransformerEncoderLayer` (measured: no `need_weights` pass-through), and `shap` would add numpy, scipy and scikit-learn for what occlusion computes directly. Also fixed: `_safe_score` let a `ValueError` escape, so a malformed window crashed the explanation instead of being marked `explanation_unavailable`. |
| 2026-10-04 | 1.11 | **Q-01 closed by D-019: `LogNet` is a from-scratch transformer over mined template IDs.** Decided on four measurements rather than preference: T-104's 103 templates at 0.9530 purity mean a log window is ~100 discrete tokens with little language left to transfer; the `TemplateMiner` already exists and is tested; NFR-05's p95 150 ms cap on 4 vCPU rules out DistilBERT over a 200-line window on CPU; and a self-contained model keeps R-67 determinism and the container size tractable. The cost is recorded rather than glossed: novel *wording* is invisible to this model, an unseen message becoming an unknown-template token, which is why `template_known` is a feature at all. |
| 2026-10-04 | 1.10 | **T-203 closed; the leakage audit now inspects artifacts rather than declarations.** T-111's `check_scaler_leakage` audits what the caller *says* it fit on, so a caller that fits on the whole stream and passes `fit_on=split.train` sails through. `check_scaler_statistics` recomputes mean and standard deviation from the training fold and compares them against the values actually inside the fitted scaler, catching the leak regardless of what anyone declared; the acceptance case — re-fitting on the full dataset — is pinned by a test. `blocking_findings` separates a leak a split *declares* (a family-holdout split reporting a time finding, which is policy) from a violation of an invariant it claims to enforce, which blocks; scaler, record and label findings block under every policy. Wired into `train_pipeline.py` as a hard gate. Also recorded: a fixture whose numeric columns are constant cannot exercise a scaler check at all — measured as one distinct value across all 120 rows — so the leakage tests needed a fixture with per-band volume variation. |
| 2026-10-04 | 1.9 | **T-202 closed; reproducibility measured at exactly zero.** `TrainingConfig` (`extra="forbid"`) is the single home for every knob, seeds are derived per role from one root, and `RunManifest` records dataset SHA-256, git SHA **plus the dirty flag**, config, seeds, metrics and environment — with **no timestamp**, so two runs produce byte-identical manifests and the agreement is checkable against the artifacts rather than only the metrics. Measured: AUC spread **0.000000** across two runs, tolerance ±0.005. Resume is tested by interrupting at epoch 2 and requiring bit-identical weights, which only passes because the shuffle order is a function of (seed, epoch). Two defects fixed while building: a progress callback ran before the checkpoint write, so a callback failure cost the epoch just trained; and resuming after editing the config silently mixed two configurations, which is now refused by config digest. **The ±0.005 clause is not CI-enforced** — torch is an optional extra CI does not install. |
| 2026-10-04 | 1.8 | **`family_split` built (D-018); first non-inflated number in the ledger; a silent labelling defect fixed.** Holding out an attack family is now a tested primitive, but measured on UNSW-NB15 no single-family holdout is clean — windows mix up to seven families, so withholding Exploits still trains on five families present in test. The honest setting is train-on-benign-only: **ROC-AUC 0.8053, PR-AUC 0.7772**, against 1.0000 under a leaky temporal split. Also fixed: `_window_label` returned `None` for mixed windows and `design_matrix` dropped those rows, silently discarding **all 21 attack windows** in a UNSW test fold while leaving 34 benign ones — invisible on a single-family capture, which is why it survived. |
| 2026-10-04 | 1.7 | **T-201 closed; D-017 recorded; two acceptance clauses, and the second one was nearly missed.** `FlowNet` ships at 1,163,076 parameters — inside the ±20% band of the 1.2 M target — and trains a 1% sample of CIC-IDS2017 Friday in 0.017 minutes against a 10-minute budget. A first cut was 88% under the size target and passed a pinned-parameter-count test while failing the gate, so the band is now its own test. D-017 records why synthetic data cannot carry any held-out metric, retracting two wrong explanations of the same failure along the way. torch 2.14.1 lands as an `ml-service[training]` extra, not a core dependency. Also recorded: a commit pushed on a green local mypy run failed three CI jobs, because strict's `disallow_subclassing_any` only fires when torch is *absent* — the configuration CI has and the local venv did not. |
| 2026-10-02 | 0.1 | Created during the repository reset. Recorded the reset (487 files removed, recoverable from `60e9adf`), ten decisions, four data sources, five open questions, and an empty measurement ledger. |
| 2026-10-03 | 0.2 | Sprint S1 opened: T-106 shipped the canonical `flow@1` / `log@1` records and a seven-scenario synthetic generator. Added D-011 (where the telemetry schemas live), refreshed the current-state and data-source tables, and re-marked the completed next actions. |
| 2026-10-03 | 0.3 | T-107 shipped `features@1` (23 features, hash-pinned). Added D-012 and Q-06, and corrected `architecture.md` §7.1 from 24 to 23 features. Two defects found and fixed while building it: three scenario builders emitted out-of-order timelines, and `backend[dev]` never declared `import-linter` or `pytest-cov` even though CI runs both. |
| 2026-10-03 | 0.4 | T-108 shipped sliding windowing with count and inactivity triggers. D-013 closes Q-06: the window key is a parameter, source by default and destination for volumetric families. `extract_flow_window` now takes the same key so destination-keyed windows are scorable. |
| 2026-10-03 | 0.5 | T-109 shipped the temporal, entity-disjoint split. D-014 records why it drops and counts spanning windows and refuses when a cut would leave a fold empty — evaluation needs entity churn, which real captures may not have. |
| 2026-10-03 | 0.6 | T-111 shipped the leakage audit: time, entity, record, scaler and label leakage, all reported in one pass. It deliberately does not trust `split_windows`, so a hand-built split fails the same way. |
| 2026-10-03 | 0.7 | T-112 shipped the evaluation harness in pure Python, pinned to hand-checkable values. `architecture.md` §3 corrected: every Python package lives inside `aegis_ml/`, since only that directory is installed. |
| 2026-10-03 | 0.8 | The dashboard container ran as root. `check_compose.py` had a privilege check scoped to the two Dockerfiles with importable ASGI targets, so it could never see the third — a green check that covered 2 of 3 images. Widened to all three; the dashboard now uses `nginxinc/nginx-unprivileged` with `USER 101` on port 8080. Not yet run under Docker. |
| 2026-10-03 | 0.9 | T-001 closed: `k8s/` manifests and `scripts/check_k8s.py`, wired into `check_all.sh` and CI. Comparing the declared tree to the filesystem also found two root files `architecture.md` had never listed. The manifests have never been applied to a cluster. |
| 2026-10-04 | 1.1 | T-104 closed: `log_parsers.py` mines BGL templates from raw lines and reproduces LogHub's published severity counts exactly (critical 347, error 48, info 1,597, warning 8). Two defects found by measuring instead of assuming: tie-break order in the greedy template search changed the result set (284 vs 296 vs 103 templates), so it is now fixed and recorded, and `_build()` had to receive original tokens rather than templated ones. An earlier prototype figure of 121 templates / 0.9835 purity is retracted — it came from iterating a `set`. ml-service tests 197 → 219. |
| 2026-10-04 | 1.6 | **The kafka profile broke the project, and the claim behind it was false.** I had written that nothing else in the stack depends on kafka and put it behind a `streaming` profile. `backend` depends on postgres, redis, kafka and elasticsearch, all with `condition: service_healthy`, and compose refuses a dependency on a service whose profile is not enabled: *service "backend" depends on undefined service "kafka"*. The claim came from reading one slice of the compose file and generalising from it. Reverted the profile and repointed the image at `bitnamilegacy/kafka:3.9`, which is a drop-in for the `KAFKA_CFG_*` scheme and the `/bitnami/kafka` volume. The tag itself is **not verified** — there is no Docker daemon in this sandbox — so the compose change ships with a `docker manifest inspect` pre-flight rather than a claim that it works. |
| 2026-10-04 | 1.5 | **The stack could not be built outside the sandbox, and both causes were invisible here.** There is no Docker daemon in this environment, so `docker compose build` had never been run — `check_compose.py` validates the file, not the build. Two defects surfaced on the first real attempt. First, no `.dockerignore` existed anywhere, so the dashboard's `COPY . .` overwrote the container's `npm ci` result with the host's `node_modules`; on a machine still carrying dependencies from the discarded implementation that meant TypeScript 4.x, and `tsconfig.json`'s `bundler` resolution and `allowImportingTsExtensions` failed as unknown options despite the lockfile pinning 5.9.3. It also sent 731 MB of build context. Second, `bitnami/kafka:3.9` no longer exists — the public Bitnami catalog was deleted on 2025-09-29 — and its resolution failure aborted the whole `up`, including four services that need no broker. Added `.dockerignore` to all three build contexts and moved kafka behind a `streaming` profile; **Q-08** tracks the image migration, which cannot be verified here. |
| 2026-10-04 | 1.4 | **D-016 closes the entity-disjoint option in Q-07, by measurement.** Added `group_split` and `--split-policy entity-only`: whole entities partitioned by SHA-256 (not a salted hash), so R-61 holds exactly and R-60 is dropped deliberately. Running it on Friday produced a test fold of 44,595 rows with **0 positives**, and the diagnosis is decisive — 2,561 of the 2,562 attack windows belong to a single source entity, `172.16.0.1`, and destination-keying only mirrors the concentration onto the victim. **This retracts D-015's explanation**: the failure is attack-entity concentration, not persistent attack sources, and the internet-wide-servers story was an inference I had not measured. The primitive stays (six tests, ml-service 223 → 229) because it is correct for a corpus with entity diversity; the release gate moves to an attack-family holdout, which is not built yet. |
| 2026-10-04 | 1.3 | **T-007 and T-009 closed.** `.pre-commit-config.yaml` with 14 hooks — `pre-commit run --all-files` exits 0, and a planted AWS key and Stripe key are both blocked by `detect-secrets` against a committed `.secrets.baseline`. A CI job runs the hooks because a local hook is bypassable with `--no-verify`. `scripts/check_frontend_boundaries.py` enforces the frontend contracts (no feature→feature imports, dependencies point down the layering) and is injection-proved against three violation classes. Wiring the formatters surfaced three genuine conflicts rather than cosmetic ones: stylelint's `color-hex-length` wanted `#fff`, which would have **silently** dropped tokens from `tokens.test.ts` because that test extracts them with a six-digit regex; prettier's default double quotes rewrote the `[data-theme='dark']` selector a test finds by literal substring, breaking the whole file with 0 tests collected; and the prettier mirror tops out at 3.1.0 against the 3.9.9 this repo formats with. The first two are documented in the configs, and the third is why prettier, stylelint and commitlint run the dashboard's own pinned binaries. `generate_synthetic.py` was found missing from both mypy invocations. check_all.sh 18 → 25 checks. |
| 2026-10-04 | 1.2 | **T-110 closed; D-015 and Q-07 recorded; CI was red for 17 hours.** D-015 makes R-61 a measured policy rather than an axiom while R-60 stays unconditional, and `Split.audit()` now reports overlap *counts*. Both baselines are scored on real CIC-IDS2017 captures, with the two-day and single-day runs disagreeing for a reason worth keeping: the two-day split holds different capture days, so it separates days as much as attacks. A fixed 0.5 threshold turned out to be meaningless on a 4.7%-positive fold (F1 0.1605 at 0.50 versus 0.9977 at the best-F1 threshold of 0.65), so reports now carry both plus the base rate. Separately, every CI run since T-107 had failed: `requirements-dev.txt` never declared pydantic, which the root `mypy.ini` needs for its plugin, and that error masked a second one — `check_compose.py` imports the backend settings model, so typechecking it needs the services, which the docs job does not install. Script typechecking moved to the infra job and now covers all five scripts instead of two. ml-service tests 219 → 223. |
| 2026-10-04 | 1.0 | **Real benchmark data obtained; T-101–T-103 and T-105 done.** The claim that the datasets were unreachable was wrong. `api.github.com`'s contents endpoint serves file bytes with `Accept: application/vnd.github.raw`, unauthenticated, so `scripts/fetch_datasets.py` runs in this sandbox; a page-fetching tool that is outside the allowlist supplied the publishers' record counts. CIC-IDS2017 (225,745 rows) and a 49-column UNSW-NB15 sample (10,000 rows) are now on disk, hash-verified. Nine integrity findings recorded in Data sources — including two mirrors with the train/test file names transposed, and the fact that the widely used `UNSW_NB15_training-set.csv` is a 45-column derivative with no addresses or timestamps. T-110 is blocked by the data, not the code: no reachable capture yields a test fold with both classes under R-60 + R-61. ml-service tests 134 → 197. |
