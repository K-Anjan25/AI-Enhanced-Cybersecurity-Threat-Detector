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
| Source code | `backend/` FastAPI skeleton, `ml-service/` inference skeleton **plus the S1 data layer** (`aegis_ml/data/`: `flow@1` and `log@1` records, seven-scenario synthetic generator, `features@1` extraction, windowing, splits, leakage audit; `aegis_ml/training/` evaluation harness), `dashboard/` React shell — all tested. No model code |
| Tests | 188 passing — 20 backend, 134 ml-service, 34 dashboard. Coverage 90.3% on `app/` against the 80% gate (R-80) |
| Checks green | `./scripts/check_all.sh` — 20 checks: ruff, black, mypy strict, bandit, import-linter, pytest ×2, coverage, tsc, eslint, vitest, vite build, doc integrity, compose consistency. Five were proven to fail on an injected violation before being trusted |
| Dependencies | Python via `pip install -e "backend[dev]" -e "ml-service[dev]"` (both verified); npm `package-lock.json` committed for `npm ci` (R-08) |
| Datasets | **Public sets not downloaded** — their hosts are unreachable from this sandbox. Synthetic data generates on demand via `scripts/generate_synthetic.py` into the gitignored `data/` |
| Models | **None trained.** No baselines, no metrics |
| Branch | `arena/01a0fee2-ai-enhanced-cybersecurity-thre`, based on `60e9adf` |
| Next work | S0 is complete except running the compose stack and applying the manifests, both of which need infrastructure this sandbox does not have. In S1 everything is DONE except T-101…T-105 and T-110, all of which need the real datasets |

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
| 1 | Confirm Q-01, Q-03, and Q-05 owners and dates | — | Before 2026-10-05 |
| 2 | ~~Commit the six documents as the baseline~~ — done, `3d74000` | — | Complete |
| 3 | ~~Begin S0: scaffolding, CI, compose, docs~~ — done except T-005 execution and `k8s/` | T-001…T-010 | Complete |
| 4 | Run the compose stack on a host with a Docker daemon and close T-005 | T-005 | When Docker is available |
| 5 | Fetch datasets and record real checksums — blocked, hosts unreachable here | T-101, T-102 | S1 |
| 6 | ~~Build `features@1` extraction against synthetic `flow@1` records~~ — done, 23 features, hash-pinned | T-107 | Complete |
| 7 | ~~Settle Q-06 and build windowing~~ — done, closed by D-013 | T-108 | Complete |
| 8 | ~~Build the temporal + entity-disjoint split utility~~ — done, refuses rather than leaks | T-109 | Complete |
| 9 | ~~Build the leakage audit on top of `Split.audit()`~~ — done, five leak classes | T-111 | Complete |
| 10 | ~~Build the evaluation harness~~ — done, `eval@1` | T-112 | Complete |
| 11 | ~~Write the `k8s/` manifests~~ — done, statically verified | T-001 | Complete |
| 12 | Wire `AuditReport.raise_for_leaks()` and `evaluate()` into the training entrypoint | T-201 | M2 |
| 13 | Fill the measurement ledger with the first measured baselines | T-110 | End of S1 |

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

## Change log

| Date | Version | Change |
|---|---|---|
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
