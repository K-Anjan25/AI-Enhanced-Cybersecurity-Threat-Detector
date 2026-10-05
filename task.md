# Tasks & Projects — AI-Enhanced Cybersecurity Threat Detector (AEGIS)

| | |
|---|---|
| **Document** | Work breakdown, backlog, and delivery plan |
| **Version** | 0.1 |
| **Last updated** | 2026-10-02 (Friday) |
| **Status** | Live planning document — update as work lands |
| **Derives from** | [prd.md](prd.md) · [architecture.md](architecture.md) |
| **Gated by** | [rules.md](rules.md) — Definition of Done §10 |
| **Related** | [design.md](design.md) · [memory.md](memory.md) |

---

## 1. How to read this document

**Task IDs are stable.** `T-1xx` data, `T-2xx` models, `T-3xx` backend, `T-4xx` frontend, `T-5xx` platform/QA, `T-6xx` backlog. IDs are referenced from other documents — never renumber a task, mark it `DROPPED` instead.

**Estimates** are ideal engineer-days at one senior engineer, not calendar days. Points are deliberately absent: the unit is days because that is what the team actually argues about.

**Every task has acceptance criteria.** A task with no testable criteria is not ready to start. "Investigate X" tasks must state what artifact the investigation produces.

**Status values:** `TODO` · `IN PROGRESS` · `BLOCKED` · `DONE` · `DROPPED`. Status changes are made in this file in the same PR as the code.

**Status as of 2026-10-02.** Sprint S0 is under way. The backend and ml-service skeletons are written and passing their checks; per-task status is recorded under each epic table.

## 2. Milestones

| ID | Milestone | Window | Exit criteria |
|---|---|---|---|
| **M0** | Foundations | 2026-10-05 → 2026-10-16 | `docker compose up` serves `/healthz`; CI runs lint + typecheck + test on a trivial module; docs are the only content in the repo and are cross-linked |
| **M1** | Data & baselines | 2026-10-19 → 2026-10-30 | Datasets fetched with verified checksums; feature schema frozen at `features@1`; baseline metrics recorded in [memory.md](memory.md#baseline-results) |
| **M2** | Transformer models | 2026-11-02 → 2026-11-13 | Both models beat their baselines on the temporal split; cross-dataset transfer measured; determinism test green |
| **M3** | Serving & API | 2026-11-16 → 2026-11-27 | Synthetic traffic → ingest → score → alert via authenticated API; RBAC and audit log enforced by contract tests |
| **M4** | Dashboard | 2026-11-30 → 2026-12-11 | Triage loop completable in the UI on live data; accessibility checks passing on the three core screens |
| **M5** | Hardening & release | 2026-12-14 → 2027-01-08 | All NFRs verified with evidence; load test report attached; k8s manifests deploy cleanly |
| **v1.0** | Ship | 2027-01-15 (Fri) | Release note with real metrics, published docs, rollback rehearsed |

**Staffing assumption: three engineers** (see [§9.1](#91-capacity--read-this-before-committing-to-the-dates)). At two, v1.0 lands in late February 2027.

Sprints are two weeks, Monday→Friday: S0 = 2026-10-05…10-16, S1 = 10-19…10-30, S2 = 11-02…11-13, S3 = 11-16…11-27, S4 = 11-30…12-11, S5/S6 combined = 2026-12-14…2027-01-08 to absorb the year-end break.

## 3. Epic E0 — Foundations (M0)

Goal: an empty but correct skeleton. Nothing clever, everything repeatable.

| ID | Task | Est. | Deps | Acceptance criteria |
|---|---|---|---|---|
| T-001 | Repository scaffolding: directory tree per [architecture.md](architecture.md#3-repository-layout), `.gitignore`, `.editorconfig`, `README` pointer to the six docs | 0.5 | — | Tree matches the architecture doc exactly; `git status` clean on a fresh clone; no build output or data paths tracked |
| T-002 | Backend skeleton: FastAPI app factory, `/healthz`, `/readyz`, typed `core/config.py` from env, structlog JSON logging | 1 | T-001 | Both endpoints return 200 with a documented payload; a missing required env var fails startup with a named error, not a stack trace |
| T-003 | ML-service skeleton: inference app factory, `/internal/healthz`, model registry stub returning `model_not_loaded` | 0.5 | T-001 | Health endpoint distinguishes "up, no model" from "up, model active" |
| T-004 | Dashboard skeleton: Vite + React + TS + Tailwind, router shell, `ConnectionStatus`, theme provider wired to tokens in [design.md](design.md#5-design-tokens) | 1.5 | T-001 | App renders the nav shell in both themes; `tsc --noEmit` clean; tokens come from one CSS-variable source |
| T-005 | `docker/docker-compose.yml`: postgres, redis, kafka, elasticsearch, backend, ml-service, dashboard | 1 | T-002, T-003, T-004 | `docker compose up` reaches all-healthy in under 5 minutes from a clean clone (NFR-12); each service has a healthcheck |
| T-006 | GitHub Actions CI: lint, typecheck, test, docker build + Trivy scan, per [architecture.md](architecture.md#113-cicd) | 1 | T-001 | CI fails on an intentionally introduced lint error, a type error, and a failing test — verified by three scratch commits on the branch |
| T-007 | Tooling config: ruff, black, mypy strict, bandit, eslint, prettier, stylelint, commitlint, pre-commit secret scan | 1 | T-001 | `pre-commit run --all-files` passes; a planted fake API key is blocked |
| T-008 | ADR + decision workflow: template and first entries in [memory.md](memory.md#decisions-log) | 0.5 | T-001 | Template covers status/context/decision/consequences; three real decisions recorded |
| T-009 | Import-boundary contracts (services must not import FastAPI; features must not import other features) | 0.5 | T-002, T-004 | CI fails when a deliberate violation is introduced |
| T-010 | Developer docs: setup, run, test, and "how to add an endpoint / a model / a page" | 1 | T-005 | A new contributor follows it unaided and gets a running stack |

**E0 total ≈ 8.5 days.**

**Progress (2026-10-02).**

| ID | Status | Note |
|---|---|---|
| T-001 | DONE | Every directory in `architecture.md` §3 now exists, `k8s/` included. Verified by listing the declared tree against the filesystem, which also caught two root files the doc had never listed (`mypy.ini`, `requirements-dev.txt`) — now added |
| T-002 | DONE | 20 tests pass. `/healthz` and `/readyz` live; missing `AEGIS_SECRET_KEY` exits 1 naming the variable with no traceback; readiness returns 503 on an unavailable probe |
| T-003 | DONE | 15 tests pass. `/internal/healthz` distinguishes `no_model_loaded` from `serving`; staging-only models do not count as serving |
| T-004 | DONE | 34 tests pass. Nav shell, routing, dark/light theming via one CSS-variable source, `ConnectionStatus`. `tsc --noEmit` clean under `strict` + `exactOptionalPropertyTypes`; production build succeeds (83 modules) |
| T-005 | **WRITTEN, NOT EXECUTED** | 7-service compose stack plus three Dockerfiles and an nginx config. **Docker is unavailable in this sandbox, so neither the images nor the stack have been run.** `scripts/check_compose.py` verifies what can be verified without a daemon: every `AEGIS_*` variable is a real `Settings` field, the secret is interpolated rather than hardcoded, published ports match the app, healthcheck URLs are real routes, Dockerfile CMDs resolve to importable ASGI apps, and build contexts exist. It caught a genuine defect — `ml-service` served `:app` but exposed only a factory. **Second defect found later, while writing the k8s manifests:** the dashboard image had no `USER` line and ran nginx as root. The privilege check could not see it because it was scoped to the two Dockerfiles with an importable ASGI target — a check that silently covers 2 of 3 images. The check now covers all three, and the dashboard moved to `nginxinc/nginx-unprivileged` on port 8080 with `USER 101`. **That image change is unverified here** (no Docker daemon); it is the first thing to confirm when the stack is next run |
| T-006 | DONE | Five jobs — docs, infra, backend, ml-service, dashboard. `actionlint` reports no issues. Every command in the workflow was executed locally first, including the exact `pip install -e ".[dev]"` steps, and `npm ci` has a committed lockfile to resolve against |
| T-007 | DONE | ruff, black, mypy strict, bandit, pytest + coverage for both Python services; eslint with jsx-a11y and typed rules; prettier 3.9.9, stylelint 17.16, commitlint 21.2 and a 14-hook `.pre-commit-config.yaml`. **`pre-commit run --all-files` exits 0 with every hook passing**, and a planted AWS key plus a Stripe key were both blocked (exit 1) by `detect-secrets` against a committed `.secrets.baseline`. A dedicated CI job runs the hooks, because a local hook is bypassable with `--no-verify`. Three real conflicts found while wiring it: stylelint's `color-hex-length` wanted `#fff`, which would have silently dropped tokens from `tokens.test.ts`'s six-digit contrast regex, so the rule is off with the reason recorded; prettier's default double quotes rewrote a CSS selector that a test locates by literal substring, so `singleQuote` is set; and the prettier mirror has no 3.9.9, so prettier/stylelint/commitlint run the dashboard's own pinned binaries rather than a mirror that would drift |
| T-008 | DONE | Ten decisions recorded in [memory.md](memory.md#decisions-log) using a status/context/decision/consequences format |
| T-009 | DONE | Two import-linter contracts on the backend, plus `scripts/check_frontend_boundaries.py` for the dashboard: a feature may not import another feature, and dependencies must point down `lib → theme/test → components → features → app shell`. It walks all 13 source files and 16 relative imports, and **injection-proved**: a planted `features/alerts → features/overview` import, a `components → features` upward import and a dangling specifier each produced a distinct failure and exit 1. Runs in the infra CI job rather than the dashboard job, because it is pure Python and must not be skipped when `node_modules` is absent |
| T-010 | DONE | `CONTRIBUTING.md` covers setup, running each service, the compose stack with its unverified status stated, and step-by-step guides for adding an endpoint, a model, and a page — each citing the rules it must satisfy |

**Verified with (2026-10-03):** 188 tests passing — 20 backend, 134 ml-service, 34 dashboard — and `./scripts/check_all.sh` reporting 20 checks passed, 0 failed. The ml-service figure includes the S1 data, feature, windowing, split, audit and evaluation tests added later the same day; at S0 completion it was 15. `ruff check` clean, `black --check` clean, `mypy` strict clean on 22 Python files, `bandit` no issues, backend coverage 90.3% against the 80% gate, `lint-imports` 2 contracts kept, `tsc --noEmit` clean, `eslint --max-warnings 0` clean, `vite build` succeeds.

Five checks were proven non-vacuous by injecting a violation and watching them fail: `lint-imports` (`app.services.health_service -> fastapi`), the WCAG contrast test (a light-theme medium-severity text token measured 1.5782:1 against the 4.5 minimum), eslint (3 errors across R-20, R-23 and R-28), `scripts/check_docs.py` (a broken anchor, exit 1), and `scripts/check_compose.py` (a typo'd `AEGIS_*` variable and a wrong healthcheck path). All five were reverted and re-run green.

## 4. Epic E1 — Data, features, and baselines (M1)

Goal: a frozen, leak-free feature pipeline and a baseline worth beating.

| ID | Task | Est. | Deps | Acceptance criteria |
|---|---|---|---|---|
| T-101 | Dataset fetch script: UNSW-NB15 and CIC-IDS2017 download, SHA-256 verification, extraction into `data/raw/` | 1 | T-001 | Re-running verifies existing files instead of re-downloading; a corrupted file fails loudly with the expected vs. actual hash |
| T-102 | Dataset inventory: source URL, licence, checksum, record counts recorded in [memory.md](memory.md#data-sources) | 0.5 | T-101 | Every dataset used later has an entry; script output and doc agree (checked by a test) |
| T-103 | Parsers: UNSW-NB15 and CIC-IDS2017 CSV → normalised Parquet under a single `flow@1` schema | 2 | T-101 | Row counts match published dataset counts; unmapped columns are reported, not silently dropped |
| T-104 | Log corpus acquisition + parsing to `log@1` schema | 1.5 | T-001 | Template/parameter split recorded; unparseable line count surfaced as a metric |
| T-105 | Preprocessing: standardisation, categorical vocabularies, PII redaction pass | 1.5 | T-103 | Scalers and vocabularies are fit on the train split only and serialised as artifacts (R-62) |
| **T-106** | **Synthetic data generator**: seeded generator for normal traffic plus recon, brute-force, beaconing, exfiltration, and insider-threat scenarios | 3 | T-103 | Same seed → byte-identical output (asserted in CI); every record labelled by construction; scenarios cover the T4–T6 families absent from the public sets |
| T-107 | Feature extraction library `features@1`: the 24 flow features and log features from [architecture.md](architecture.md#71-flow-sequence-model-flownet) | 2 | T-105 | Feature matrix reproducible from raw; a feature-definition change requires a version bump (enforced by a schema hash test) |
| T-108 | Windowing: sliding per-entity windows (50 flows / 200 log lines) with count and inactivity triggers | 1.5 | T-107 | Window boundaries deterministic given an input stream; asserted with a fixed stream fixture |
| T-109 | Temporal + entity-disjoint split utility | 1 | T-107 | Test asserts test timestamps are strictly later than train and that no entity appears in two folds (R-60, R-61) |
| T-110 | Baseline models: logistic regression and gradient boosting on `features@1` | 1.5 | T-107, T-109 | precision / recall / F1 / ROC-AUC / PR-AUC recorded to a run log; results copied into [memory.md](memory.md#baseline-results) |
| T-111 | Leakage audit: automated checks for scaler leakage, label leakage in derived features, and time leakage | 1 | T-109 | Audit runs in CI on the split utility and fails on a deliberately leaked scaler |
| T-112 | Evaluation harness: single entrypoint producing the full metric set + confusion matrix + threshold sweep | 1.5 | T-110 | Output schema validated; running twice on the same artifact yields identical numbers |

**E1 total ≈ 18 days.** The largest epic, and deliberately so. Every later result is only as trustworthy as this pipeline.

**Progress (2026-10-03).**

| ID | Status | Note |
|---|---|---|
| T-106 | DONE | Seven scenarios — normal, recon, DDoS, brute force, beaconing, exfiltration, insider threat — in `aegis_ml/data/`, over the canonical `flow@1` and `log@1` records in `aegis_ml/data/records.py`. 45 ml-service tests pass, 28 of them new. Determinism is asserted by SHA-256 across two CLI runs at the same seed, not just by unit tests. Three assertions were proven non-vacuous by injection: an unseeded RNG, a constant destination port in the scan, and 30 s of beacon jitter each failed their target test. A fourth injection (moving insider activity to business hours) failed both T5 tests. CLI: [`scripts/generate_synthetic.py`](scripts/generate_synthetic.py) |
| T-101 | DONE | `scripts/fetch_datasets.py` + the manifest in `aegis_ml/data/datasets.py`. **Executed, not just authored**: `api.github.com`'s contents endpoint serves file bytes with `Accept: application/vnd.github.raw` and needs no token, so the script runs here. All three acceptance behaviours were demonstrated on the 36 MB CIC file — cold download, a warm re-run that reported `verified` with the mtime unchanged (0.23 s vs 4.07 s), and a one-byte corruption that exited 1 printing both digests. Hashes live in exactly one place; `test_datasets.py` fails if memory.md drifts from it |
| T-102 | DONE | Inventory in [memory.md](memory.md#data-sources): measured SHA-256, byte size, row counts, licence, mirror and caveats for every file, plus what is and is not reachable and why. Agreement with the manifest is enforced by a test that was proven non-vacuous twice — retyping one hash digit turned 3 tests red, changing `175,341` to `175,342` turned 1 red, and both were restored byte-identically |
| T-103 | DONE | `aegis_ml/data/parsers.py`: UNSW-NB15 and CIC-IDS2017 → one `flow@1` contract. On real data the row counts read match the inventory exactly (225,745 and 10,000), 56 and 244 rows were rejected against named reasons rather than dropped silently, and 14 and 34 unmapped columns were reported. 20 tests assert values read out of the fixtures by hand. Writes NDJSON, not Parquet — recorded as a deviation with its reason |
| T-104 | DONE | `aegis_ml/data/log_parsers.py`: LogHub's BGL corpus → `log@1`. **2,000 of 2,000 lines parsed, zero unparseable**, across 1,778 hosts and 5 components; severity counts match LogHub's published labels exactly. Templates are mined in two passes — a lexical pass plus iterative merging of templates differing in one position — and measured against LogHub's own labels: **103 templates against their 120, 0.9935 agreement** in that direction and 0.9530 the other way, where the lexical pass alone scored 0.4185. 22 tests, two proven non-vacuous by injection (recording `<*>` instead of the original value; disabling the merge pass). BGL was chosen over Thunderbird because Thunderbird has no severity column and `log@1` requires one — inferring a level from message keywords would have fabricated training data. Q-01 is still open; this is the from-scratch side of it |
| T-110 | DONE | `scripts/run_baselines.py` scored both baselines on real CIC-IDS2017 captures, and the blocker was a decision, not data or code. **D-015** makes R-61 a policy that is *measured* — `Split.audit()` now reports `shared_train_test_entities` as a count — while R-60 keeps no off switch. Measured: at the 80% cutoff a temporal-only split holds out 1,045 attack windows, but entity-disjointness leaves 598 that are 100% normal, at every cutoff from 0.5 to 0.9, because the attack sources are *persistent* entities (a reflected DDoS from internet-wide servers plus a web-attack host present throughout) and so always land before the cut. Friday-only, within one capture day: logistic regression ROC-AUC 0.9990 / PR-AUC 0.9398, gradient boosting 1.0000 / 1.0000, at their best-F1 thresholds of 0.95 and 0.65. Those thresholds matter — at the fixed 0.5 point the same models score F1 0.6207 and 0.1605 on a 4.7%-positive fold — so every report now carries both plus the base rate. Results are in [memory.md](memory.md#baseline-results) and `data/runs/`. Both runs are `temporal-only`, so they are benchmark-comparable rather than release-gate evidence; **Q-07** tracks where a genuinely entity-disjoint holdout comes from |
| T-105 | DONE | `aegis_ml/data/preprocess.py`: `StandardScaler`, `Vocabulary`, keyed `redact()`, and a `Preprocessor` bundle that round-trips to JSON byte-identically. Fitting takes training rows and nothing else (R-62), asserted against hand-computed mean and population σ. A zero-variance feature is centred to 0.0 rather than divided by zero. **Gap, stated plainly: the redaction primitive exists and is tested, but it is not yet wired into the ingest path** |
| T-110 | DONE | See above — scored on real data under D-015, with the leakage measured and recorded rather than relaxed silently |
| T-107 | DONE | `features@1` in `ml-service/aegis_ml/data/features.py`: the 23 flow features `architecture.md` §7.1 enumerates, plus three provisional log features pending Drain3 at T-204. The contract is pinned by a SHA-256 golden hash, so a feature change without a version bump fails the build — proven by injecting a 24th feature and watching five tests go red. 24 new tests, 69 in ml-service total. Values are asserted against hand-computed numbers, not against the implementation |
| T-108 | DONE | `ml-service/aegis_ml/data/windowing.py`: per-entity sliding windows (50 flows / 200 log lines) with count and inactivity triggers. Inactivity is applied first, so no window spans a burst boundary; stride defaults to size because overlapping windows double-count events (D-009). 19 new tests assert **exact** boundaries against a fixed 12-flow fixture — counts, start/end timestamps, trigger per window and `is_complete`. Three injections proved them non-vacuous: dropping the tail window (3 tests red), ignoring inactivity (2 red), and iterating keys in insertion order instead of sorted (1 red) |
| T-109 | DONE | `ml-service/aegis_ml/data/splits.py`: train/valid/test under both invariants at once — test starts strictly after every train start (R-60) and no entity appears in two folds (R-61). Windows whose entity spans a cut are dropped **and counted**; a cut that would empty a fold raises. 10 tests assert exact fold sizes, cutoffs and entity sets on a fixed eight-host fixture. Two injections proved them non-vacuous: keeping spanning entities in the late fold (3 red) and an off-by-one on the cut boundary (4 red) |
| T-111 | DONE | `ml-service/aegis_ml/data/audit.py`: five leak classes — time, entity, record (the same window in two folds), scaler (statistics fit outside train) and label (a feature a single threshold separates perfectly). Every check returns findings rather than raising, so one pass reports all of them; `raise_for_leaks()` is the CI gate. **It does not trust `split_windows`** — the bad splits in the tests are hand-built, which is the only reason an audit is worth having. 19 tests. Three injections proved them non-vacuous: disabling the scaler check (3 red), the label check (3 red), and dropping the train/test entity pair (1 red) |
| T-112 | DONE | `ml-service/aegis_ml/training/evaluation.py`: one entrypoint, `evaluate()`, producing precision, recall, F1, ROC-AUC, PR-AUC, accuracy, a confusion matrix and a 21-point threshold sweep as a validated `eval@1` document. Metrics are implemented in pure Python — no scientific stack yet — and pinned to values checkable on paper: ROC-AUC 0.75 and PR-AUC 0.8333 on the textbook example. Ties share an average rank, so reordering the input cannot move a number. 17 tests; three injections proved them non-vacuous (positional instead of averaged ranks, exclusive threshold boundary, inverted tie-break) |
| T-110 | DONE | See above — scored on real data under D-015, with the leakage measured and recorded rather than relaxed silently |

**Two choices worth recording.** Undefined metrics raise instead of returning NaN, because a NaN in a metrics table gets read as zero by whoever looks next. And `best_f1` breaks ties toward the *higher* threshold, since at equal F1 fewer false positives is the safer operating point — both asserted by tests rather than left to convention.

**`architecture.md` §3 corrected while placing this file.** The tree drew `registry/` and `training/` as siblings of `aegis_ml/`, but only `aegis_ml/` is installed by `pip install -e ml-service`, so a sibling package would not be importable. The doc now shows every Python package inside `aegis_ml/`, and records that the data pipeline is one package (`data/`) rather than split across `features/` and `scoring/`, which are reserved for T-201.

**Two notes on the audit's honesty.** The label check is a heuristic — perfect single-feature separation — so it catches a feature that *is* the label, not one that is merely correlated; a subtly leaky feature still needs a human. And it reports rather than guesses: the scaler and label checks are skipped when the caller supplies nothing to inspect, instead of passing silently.

**What T-109 made unavoidable (D-014).** A split that is both strictly temporal and entity-disjoint is only possible when hosts appear and disappear over time. On a stream where every host is active end to end, every host spans the cut and the utility refuses rather than leaking — asserted against the synthetic `normal` stream, where all four hosts run throughout. Real captures may well look like that, so this constrains T-110 and is the reason `Split.audit()` reports the dropped count instead of hiding it.

**Q-06 closed by D-013 while building T-108.** The window key is a parameter rather than a constant: source by default, destination for volumetric families. Measured, not argued — the synthetic DDoS flood spreads across 40 sources, so source-keying yields 40 windows of one flow each while destination-keying yields two windows of 20. `extract_flow_window` takes the same key, which required a small change to T-107: validating the source dimension would have rejected exactly the destination-keyed windows that need scoring.

**Two defects T-107 exposed.** (1) Three synthetic builders — `normal`, `exfiltration`, `insider_threat` — computed offsets as `index * rng.uniform(a, b)`, redrawing the multiplier each iteration, so their timelines ran *backwards* (12, 7 and 11 out-of-order adjacent pairs at count 30). Nothing caught it because no test asserted ordering. Fixed with cumulative cursors, and `generate_flows`/`generate_logs` now refuse to return an out-of-order sequence, so a future builder cannot regress it. (2) `backend[dev]` declared neither `import-linter` nor `pytest-cov`, although `ci.yml` runs `lint-imports` and the suite runs `pytest --cov`; they only worked locally because they had been hand-installed. Both are now declared and verified from a clean virtualenv.

**Not covered by T-106.** The generator invents no real capture. Its scenarios are shaped to be separable by the features named in the PRD, so model scores on synthetic data measure the pipeline, not field performance — that caveat belongs in the model card (R-42).

## 5. Epic E2 — Transformer models (M2)

Goal: two models that beat the baselines for a defensible reason.

| ID | Task | Est. | Deps | Acceptance criteria |
|---|---|---|---|---|
| T-201 | `FlowNet`: embeddings + 4-layer transformer encoder + reconstruction and anomaly heads | 3 | T-107 | Trains end to end on a 1% sample in under 10 minutes on CPU; parameter count within 20% of the 1.2 M target |
| T-202 | Training pipeline: config-driven, seeded, checkpointing, resume, run manifest | 2 | T-201 | Two runs of the same config agree within ±0.005 AUC (R-67); manifest contains dataset hashes, git SHA, config, seeds, metrics — **DONE, see below** |
 2 | T-201 | Two runs of the same config agree within ±0.005 AUC (R-67); manifest contains dataset hashes, git SHA, config, seeds, metrics |
| **T-203** | **Leakage audit on the trained model**: verify no train/test contamination in the reported metrics | 1.5 | T-111, T-202 | Audit is a **release blocker**; re-fitting the scaler on the full dataset must cause the audit to fail (R-62) — **DONE, see below** |
| T-204 | `LogNet`: Drain3 template mining + embeddings + 6-layer encoder + masked-template and hypersphere losses | 3.5 | T-104, T-107 | Mining is stable across re-runs on the same corpus; **decision Q-01 (pretrained DistilBERT vs. from-scratch templates) must be recorded in [memory.md](memory.md#decisions-log) before this task starts** — **DONE, see below** |
| T-205 | Fusion: late fusion, single-modality penalty, `partial_evidence` flag | 1 | T-201, T-204 | Composite score is monotonic in both inputs; single-modality output is flagged, never presented as full evidence — **DONE, see below** |
| T-206 | Explanation: attention rollout + SHAP on flow features, top-3 plain-language rendering | 2.5 | T-201 | Every scored window yields ≥ 3 reasons or an explicit `explanation_unavailable` marker (R-70); reasons name the feature, the value, and the baseline — **DONE with a recorded method change (D-020), see below** |
| T-207 | Threshold calibration: quantile fit per family/tenant with the ±0.10 guardrail and audit write | 1.5 | T-205 | A run cannot move a threshold by more than 0.10; every change appears in the audit log — **DONE, see below** |
| T-208 | Cross-dataset transfer evaluation (UNSW-NB15 → CIC-IDS2017) | 1.5 | T-112, T-202 | Recall on the transferred set recorded; a drop below 0.70 blocks the release (R-66) — **DONE: recall 0.7955 ≥ 0.70 with a target-blind threshold, gate passes (D-022)** |
| T-209 | Inference determinism and latency benchmark | 1 | T-201, T-204 | Identical input + pinned model → byte-identical output (R-67); p95 window scoring ≤ 150 ms on 4 vCPU (NFR-01), measured and recorded — **DONE: determinism 4/4, p95 22.590 ms; the 4 vCPU half is unverified here (2 vCPU sandbox) and says so in the artifact (D-023)** |
| T-210 | ONNX export fallback path | 1.5 | T-209 | Exported model scores within 1e-4 of the PyTorch model on a fixed batch; latency delta recorded — **DONE: max abs Δ 9.537e-07; latency delta within noise, backends the same speed (D-024)** |
| T-211 | Drift monitoring: per-feature PSI computation on incoming windows | 1 | T-107 | PSI matches a hand-computed reference case; > 0.25 raises the drift metric — **DONE: 0.051082562 hand-verified; measured 20/23 features drifting UNSW→CIC (D-025)** |
| T-212 | Model registry: immutable, content-addressed artifacts with status transitions | 1 | T-202 | `latest` is not resolvable; promoting a retired version is refused with a clear error |
| T-213 | Shadow-mode scoring harness | 1.5 | T-212 | Shadow scores are recorded without producing alerts; distributions comparable to the active model |
| T-214 | Model card per release: intended use, metrics, limitations, adversarial-evasion caveat | 1 | T-208 | Card lists the measured numbers only, each traceable to a run (R-74) |
| T-215 | Hyperparameter search on the validation split only | 2 | T-202 | Search config and results logged; the test split is untouched during search (R-71) |

**E2 total ≈ 25.5 days.** Parallelisable across two engineers from T-204 onward
**Progress (2026-10-04).**

| ID | Status | Note |
|---|---|---|
| D-016 gate | PARTIAL | `family_split` in `ml-service/aegis_ml/data/splits.py` (+9 tests, 29 in `test_splits.py`): every window containing a held-out family goes to test, benign negatives come from entities training never saw, and nothing held out reaches training. Wired into `train_flownet.py` as `--split-policy family-holdout --holdout-family X`. **Measured on UNSW-NB15, no single-family holdout is clean** — see D-018. The defensible setting is train-on-benign-only: **ROC-AUC 0.8053 / PR-AUC 0.7772**, versus 1.0000 under a leaky temporal split. Found and fixed a silent defect: `_window_label` returns `None` for mixed windows and `design_matrix` dropped those rows, discarding **all 21 attack windows** in a UNSW test fold while keeping 34 benign ones. Gate narrowed, not closed. |
| T-205 | DONE | `ml-service/aegis_ml/scoring/fusion.py`. **Late** fusion, so each model scores independently and only the two scalars combine — a single head over concatenated representations would usually score better and cannot say which modality produced an alert, which is what T-206 needs. Monotonicity is asserted by sweeping all 101 points of the range at five levels of the other modality, plus the single-modality paths, rather than spot-checking: a fusion rule can be monotonic at the points you tried and still break between them. A missing modality is penalised **and** flagged, because a penalised 0.9 still reads as a confident score to whoever is triaging it. Missing evidence is never imputed to zero — that would turn a probe outage into a quiet-looking network — and `fuse(None, None)` raises rather than inventing a score. 23 tests. |
| T-206 | DONE | `ml-service/aegis_ml/scoring/explanation.py`. **Method changed and recorded as D-020**: occlusion attribution, not attention rollout and not the `shap` package. Attention weights are unreachable — `nn.TransformerEncoderLayer.forward` does not forward `need_weights` and `nn.TransformerEncoder.forward` has no parameter that requests them, measured rather than assumed — and re-implementing the block would put a second copy of the model's arithmetic beside the first. `shap` would add numpy, scipy and scikit-learn for what occlusion computes directly on 35 columns. **R-70 enforced exactly**: ≥ 3 reasons naming feature, value and baseline, or an explicit `explanation_unavailable`; never a short list, never an empty one without the flag. A test requires the feature that was actually driven to be attributed first, which shape and ordering checks cannot substitute for. 13 tests. |
| T-208 | DONE | `scripts/transfer_eval.py`: trains on one corpus and scores another whole, **with the source preprocessor and no refit** — refitting on the target would leak (R-62) and would hide the shift this task exists to measure. The T-203 leakage audit runs on the source split before anything is trained. **Measured: UNSW-NB15 → CIC-IDS2017 gives ROC-AUC 0.9048 but recall 0.0000** at the source's 0.50 threshold, and 0.0679 at 0.05. Ranking transfers; calibration and coverage do not (D-021). **The R-66 gate fires and the script exits non-zero — the release is blocked.** Recorded as a negative result rather than tuned into passing, since a transfer number that reaches 0.70 by moving the threshold is not a transfer result. Two concrete causes identified: CIC's `state`/`service` categoricals are absent from UNSW's vocabulary and collapse to the reserved unknown column, and CIC's numerics are standardised with UNSW statistics into a range the model never saw. |
| T-211 | DONE | `aegis_ml/scoring/drift.py` + `scripts/drift_report.py`. **Hand-computed criterion met:** reference (0.5, 0.3, 0.2) vs actual (0.4, 0.4, 0.2) gives `−0.1·ln(0.8) + 0.1·ln(4/3) = 0.051082562`, asserted to rel=1e-12 — the arithmetic is done in the test, not taken from the function, because a test that builds its own expected value from the implementation passes against a wrong one too. Bin edges from the reference alone (R-62 for a different artifact); empty bins floored not skipped, with the upper bound pinned; categoricals never binned. **Measured UNSW→CIC: 20 of 23 features over 0.25** — `state` 26.6670, `direction` 9.0923, `dst_ip_count` 6.7233, `service` 3.9367; only `fin`, `protocol`, `rst` stable. **The top drifters are exactly the categoricals D-022 blamed for the transfer failure, so this independently corroborates that diagnosis.** Publishes `aegis_drift_psi{feature}` per architecture.md §12 for every feature, not only drifted ones, since a gauge that appears only on failure cannot show stability. Exits 0 on drift by default — a monitor that fails the build on legitimate traffic change gets switched off — with `--fail-on-drift` to gate. 42 tests. |
| T-210 | DONE | `aegis_ml/serving/onnx_export.py` + `scripts/onnx_export.py`. **Agreement: max abs Δ 9.537e-07** (`reconstruction`) and 1.341e-07 (`anomaly_logits`) on a fixed seeded 8×50×23 batch, ~100× inside the 1e-4 tolerance and reproducible run to run — which is why it gates the build. **Latency delta is within measurement noise:** the first run said −0.088 ms, then three more gave −1.123, +2.311 and −2.257 ms with the sign flipping, so the script now interleaves both backends over `--rounds` (default 5) and reports the spread. Over 5 rounds × 200 passes: torch p95 median 19.120 ms, ONNX 19.425 ms, delta median **+1.172 ms** (range −0.975 to +2.224), ONNX faster in **2 of 5** — the script reports the sign as inconsistent and the backends as the same speed at this resolution. With T-209 already 6.6× inside budget, this is preparation, not a speedup. **Two exporter facts found by measurement:** opset must be 18 (torch 2.14 refuses 17 and fails its own downgrade conversion, leaving a graph that will not load), and **`dynamo=False` is required** — the default exporter specialises the batch dimension, so the graph scores batch 1 and fails at any other size on a Reshape with the count baked in. Fallback is an `onnx` extra; the module imports with neither torch nor ONNX present, and `load_scorer` returns the backend it chose because that is an audit question. 16 tests, 13 passing in a torch-free and ONNX-free interpreter. |
| T-209 | DONE | `scripts/inference_benchmark.py`. **R-67 determinism passes all four checks**: repeated passes byte-identical; a *second instance* built from the same seed identical (separating "the seed determines the weights" from "the weights stayed in memory"); the torch RNG state **unchanged** by a forward pass, so scoring consumes no randomness; weights untouched. Compared over raw storage bytes, not approximate equality. **Latency p95 22.590 ms** per window (1×50×23, 300 passes, 20 warmups discarded) against the 150 ms budget. **Honest gap:** NFR-01 says 4 vCPU, this machine has 2, so the script writes `matches_nfr01_reference: false` rather than labelling it a 4 vCPU result — the run was single-threaded, a stricter configuration, but that is an argument, not a measurement on the specified machine. Measured oddity: 2 torch threads are *slower* than 1 on a window this small (p95 28.611 vs 26.609 ms), so the scoring path should pin one thread. |
| T-208 | DONE (solved) | `scripts/transfer_eval.py`: trains on one corpus, scores another whole, **source preprocessor and no refit** (refitting on the target would leak, R-62, and would hide the shift this task measures), T-203 leakage audit on the source split before anything is trained. **First attempt failed** — recall 0.0000, release blocked, and I diagnosed it wrongly (D-021). The measured cause: the family-holdout training fold is benign-only (`POSITIVES=0` of 95 windows), so the **supervised** head being scored could only learn a constant. Fixed by scoring the **reconstruction** head instead — new `per_window_reconstruction_error` in `flownet.py`, asserted equal to the training loss — with the cut fitted **target-blind** on source benign validation scores via T-207 (`0.3622` @ q0.99). **Recall 0.1725 → 0.7955; R-66 passes.** Note the trap: the broken head had the *higher* AUC (0.9048 vs 0.7464) and the worse recall, because a near-constant head still ranks — ROC-AUC alone cannot detect a degenerate detector. Precision 0.5904 vs a 40% attack base rate is the remaining open problem. 9 new tests. |
| T-207 | DONE | `ml-service/aegis_ml/scoring/thresholds.py`. The guardrail **clamps** rather than refuses: refusing would freeze the threshold the first time the calibration data is unusual, and a threshold that cannot move is not calibrated but abandoned — a test shows ten successive runs still reach a distant threshold. The requested value is recorded alongside the applied one, because the refused part of a change is the record of the data disagreeing with the model. Both acceptance clauses are swept, not spot-checked: no single run moves more than 0.10 from any starting threshold, and every change — ordinary, clamped, and no-op — lands in the append-only audit log. `calibrate_and_record` combines fit and write so an unrecorded change takes extra effort. 101 tests. |
| T-204 | DONE | `ml-service/aegis_ml/models/lognet.py`: embedding → **6-layer** encoder → masked-template head + hypersphere objective. Q-01 was recorded as **D-019 first**, as the task requires: from-scratch over mined template IDs, decided on four measurements rather than preference (T-104's 103 templates at 0.9530 purity leave little language to transfer; the `TemplateMiner` already exists; NFR-05's 150 ms cap rules out DistilBERT over a 200-line window on CPU; a self-contained model keeps R-67 and container size tractable). **Acceptance met: mining is stable across re-runs** — and across a *shuffled* corpus, which is the stronger claim, since a miner whose output depends on arrival order cannot be reproduced from the data alone. A third test asserts the corpus actually collapses, so the stability tests cannot pass because nothing was mined. Both losses are self-supervised, because unlabelled logs are the production case. 16 tests; 296 in ml-service. |
| T-203 | DONE | `audit_trained()` + `check_scaler_statistics()` + `blocking_findings()` in `ml-service/aegis_ml/data/audit.py`; wired into `scripts/train_pipeline.py` as a hard gate that exits non-zero. **Acceptance met: re-fitting the scaler on the full dataset fails the audit.** The point of T-203 over T-111 is that T-111's `check_scaler_leakage` audits what the caller *declares* it fit on — a caller that fits on everything and passes `fit_on=split.train` satisfies it. `check_scaler_statistics` audits the artifact: it recomputes mean/std from the training fold and compares them against the values actually inside the scaler, so the leak is caught regardless of what anyone declared, and a test pins exactly that case. Tolerance is relative, because bytes-per-second and seconds differ by orders of magnitude and one absolute tolerance cannot serve both. `blocking_findings` separates a leak the split *declares* (a family-holdout split reporting a time finding) from a violation of an invariant it claims to enforce; scaler, record and label findings block under every policy. 29 tests in `test_audit.py`. |
| T-202 | DONE | `ml-service/aegis_ml/training/pipeline.py` + `scripts/train_pipeline.py`. `TrainingConfig` is the only place a knob may live (`extra="forbid"`, so a new one cannot enter a run without entering the schema); seeds are derived per role from one root rather than repeated; `RunManifest` carries dataset SHA-256, git SHA **and dirty flag**, config, per-role seeds, metrics and environment. **Acceptance measured: AUC spread 0.000000 across two runs of one config, tolerance ±0.005 — PASS** (`data/runs/pipeline/reproducibility.json`), both runs identical to six decimals. Resume is tested the only way that matters: interrupt at epoch 2, resume, and land on bit-identical weights — which requires the shuffle order to be a function of (seed, epoch) and never of history. 19 tests. **Caveat: the ±0.005 clause is verified locally, not enforced by CI**, because torch is an optional extra CI does not install; the 17 torch-free tests (manifest, digest, config, seeds) do run there. |
| T-201 | DONE | `ml-service/aegis_ml/models/flownet.py`: projection → 4-layer transformer encoder → reconstruction head + anomaly head. **Both acceptance clauses measured on real data, not asserted.** Wall clock: 0.017 min to train 3 epochs on a 1% sample (42 of 4,149 training windows) of CIC-IDS2017 Friday, against a 10-minute budget. Size: **1,163,076** parameters against the 1.2 M target, inside the 960 k–1.44 M band. 13 tests. A first cut shipped at 139,160 parameters — 88% under target — and passed a pinned-count test while failing the gate, so the band is now its own test. **The metric is not the result:** ROC-AUC 1.0000 comes from a temporal-only split with 20 shared train/test entities over a single DDoS family (D-015, D-016), on 26 attack test windows. Best F1 0.8667 at threshold 0.65. `scripts/train_flownet.py` records both clauses and the split audit in `data/runs/flownet_cic_1pct.json`. Synthetic data could not be used at all — see **D-017**. |
.

## 6. Epic E3 — Backend and API (M3)

Goal: telemetry in, ranked alerts out, with auth and audit enforced.

| ID | Task | Est. | Deps | Acceptance criteria |
|---|---|---|---|---|
| T-301 | Database models + migrations for the schema in [architecture.md](architecture.md#6-data-model-postgresql), monthly partitioning on `alerts` and `ingest_stats` | 2 | T-002 | Migration up and down both apply cleanly; a query without a time predicate is rejected by the repository layer (R-34) |
| T-302 | Auth: Argon2id hashing, JWT issue/refresh with rotation, session invalidation | 2 | T-301 | Expired and tampered tokens are rejected; refresh rotation invalidates the previous token (R-51) |
| T-303 | RBAC dependency + route-role matrix test across `viewer`/`analyst`/`responder`/`admin` | 1.5 | T-302 | Matrix test enumerates every route × role; adding a route without a matrix entry fails CI (R-53) |
| T-304 | Ingest API: `POST /ingest/flows`, `POST /ingest/logs`, NDJSON batching, per-record validation errors (FR-01, FR-02, FR-04) | 2.5 | T-301 | A batch with one malformed record returns a per-record error list and accepts the rest; no partial batch is silently dropped |
| T-305 | Query API for alerts/entities/metrics with filtering and pagination — **decision Q-02 (Elasticsearch vs. partitioned Postgres for hunt) must be recorded before this task starts** | 2 | T-301 | Filters combine correctly; pagination is stable under concurrent inserts; decision recorded in [memory.md](memory.md#decisions-log) |
| T-306 | Kafka producer/consumer with `src_ip` partitioning and consumer-group lag metrics | 2 | T-302 | One entity's flows stay ordered across a restart; lag is exported as a Prometheus gauge |
| T-307 | Scoring worker: consume → window → call model service → emit scores | 2.5 | T-306, T-209 | Restarting the worker resumes from the committed offset with no data loss and no duplicates |
| T-308 | Correlator: severity banding, cool-down dedup, flow↔log grouping, alert persistence (FR-12…FR-15, FR-19) | 2 | T-307 | Duplicate (entity, family) within 15 min increments `occurrence_count` instead of creating a row |
| T-309 | Analyst feedback endpoints and verdict persistence (FR-16, FR-18) | 1 | T-308 | Verdicts are immutable once written; a second verdict supersedes with history retained |
| T-310 | WebSocket alert channel + REST/SSE fallback (FR-20) | 1.5 | T-308 | Killing the socket mid-stream triggers client fallback; no alert is lost across the switch |
| T-311 | Outbound webhooks: HMAC signing, allowlist, SSRF block, retry with backoff (FR-21) | 1.5 | T-308 | Private IP ranges are refused; signature verifiable with the documented scheme; retries are bounded and logged |
| T-312 | Audit log service, append-only, covering every mutating route (FR-42) | 1 | T-303 | A test asserts no ORM update/delete path exists on the audit model (R-31) |
| T-313 | API keys with scopes, hashing, and revocation (FR-44) | 1 | T-302 | Secret is returned exactly once; only a prefix is stored; revoked keys are rejected immediately |
| T-314 | Retention + GDPR erasure service (NFR-05) | 1.5 | T-301 | Erasure cascades across stores, logs the action, and is idempotent |
| T-315 | Model ops endpoints: list, metrics, promote, rollback (FR-30…FR-33) | 1.5 | T-212 | Promotion to `active` requires `admin`; rollback is one call and needs no redeploy |
| T-316 | Rate limiting, request size caps, and back-pressure semantics | 1 | T-304 | Exceeding the limit returns 429 with `Retry-After`; oversize bodies are rejected before parsing |
| T-317 | Prometheus metrics + OpenTelemetry traces across ingest → score → correlate → notify | 1.5 | T-308 | A trace ID from the ingest response appears in the alert record |
| T-318 | Structured logging with correlation IDs and PII redaction allowlist | 1 | T-302 | A planted username in an error path never reaches the log output (R-54) |
| T-319 | End-to-end golden test: synthetic traffic → alert visible via API, using in-process fakes | 1.5 | T-308 | Runs in CI without Docker-in-Docker (R-88) |
| T-320 | API reference generated from the Pydantic schemas, published with the build | 1 | T-304 | Every route has a documented request and response schema; a route missing a schema fails CI |

**E3 total ≈ 31.5 days.**

## 7. Epic E4 — Frontend (M4)

Goal: the triage loop, finished properly. Screens in priority order.

| ID | Task | Est. | Deps | Acceptance criteria |
|---|---|---|---|---|
| **T-401** | Design tokens: Tailwind config + CSS variables from [design.md](design.md#5-design-tokens), both themes | 1 | T-004 | Every colour in use resolves to a token; a contrast regression test asserts the documented ratios (R-27) |
| **T-402** | UI primitives per [design.md](design.md#6-component-library): Button, Badge, Card, DataTable, Modal, Toast, EmptyState, ErrorState, Skeleton, ConnectionStatus | 3 | T-401 | Each primitive has a test for its states and an axe-clean render |
| **T-403** | Overview dashboard: KPI tiles, severity area chart, top entities, pipeline health strip (FR-50) | 2.5 | T-402, T-305 | Degraded pipeline stages render red with the exceeded budget; stale data shows a "last update" age |
| **T-404** | Alert triage screen: list + detail with the four zones and keyboard verdicts (FR-51) | 4 | T-402, T-308 | Full triage loop completable without a mouse; `explanation_unavailable` and `evidence expired` states render explicitly |
| T-405 | Real-time layer: single WebSocket at the app shell, pub/sub hook, reconnect with backoff, disconnected banner | 1.5 | T-310 | Killing the connection shows the banner and falls back to polling; reconnecting replays missed alerts |
| T-406 | Traffic explorer: D3 time-series with brushing + entity graph with the ≥ 2,000-node fallback (FR-52) | 3.5 | T-402, T-305 | Brushing filters all dependent panels; the graph switches to adjacency mode and labels the switch |
| T-407 | Log explorer with template clustering and pausable live tail | 2.5 | T-402, T-305 | 10,000 identical lines collapse to one row with a count; pause freezes the view |
| T-408 | Hunt console: query input, autocomplete, saved queries, results table, audited CSV export | 3 | T-305 | Export is blocked below `responder` and writes an audit entry; empty results show the executed query |
| T-409 | Model ops + drift screens (FR-53) | 2.5 | T-315 | Promotion requires typing the model ID; drift bars mark the 0.25 threshold |
| T-410 | Admin screens: users/roles, API keys, thresholds with the 7-day impact preview, retention, audit | 3 | T-313, T-314, T-315 | The last `admin` cannot self-demote; the API key secret renders exactly once |
| T-411 | Command palette and global keyboard shortcuts | 1.5 | T-402 | `⌘K` navigates, filters, and runs saved hunts; the shortcut reference is in-app |
| T-412 | Responsive behaviour per [design.md](design.md#83-responsive-breakpoints) | 1.5 | T-404 | Below 768 px only the triage loop is offered, with a banner saying so |
| T-413 | Accessibility pass: axe assertions, keyboard audit, screen-reader pass on the three core screens | 2 | T-404 | No critical/serious axe violations; the screen-reader result is recorded in the release note |
| T-414 | Frontend test suite: component tests for states, plus a triage-loop integration test | 2 | T-404 | Tests query by role/label, not implementation details (R-87) |
| T-415 | PDF/CSV export of alert batches (FR-23) | 1.5 | T-404 | Exported rows match the filtered view exactly, including the filter definition |

**E4 total ≈ 35 days.** T-404 is the critical path; start it as soon as T-402 lands, even against a stubbed API.

## 8. Epic E5 — Platform, QA, and release (M5)

| ID | Task | Est. | Deps | Acceptance criteria |
|---|---|---|---|---|
| T-501 | Load test: k6 or Locust at 5,000 flows/s and 10,000 logs/s for 30 minutes | 2 | T-317 | NFR-02 sustained with no error-rate increase; results attached to the release note |
| T-502 | Latency verification against the NFR-01 budget, stage by stage | 1 | T-501 | Measured p95 per stage compared to the budget table in [architecture.md](architecture.md#5-data-flow-one-flow-record-end-to-end); overruns filed as tasks, not absorbed |
| T-503 | Failure-mode drills per [architecture.md](architecture.md#14-scalability-and-failure-modes) | 2 | T-501 | Each row of the failure table is exercised and the observed behaviour recorded |
| T-504 | Kubernetes manifests + Helm values, secrets from the cluster store | 2.5 | T-005 | Deploys to a clean cluster; HPA scales scoring workers on consumer lag |
| T-505 | Grafana dashboards and alert rules for AEGIS itself | 1.5 | T-317 | Consumer-lag, drift, latency, and error-rate alerts fire in a drill |
| T-506 | Security review against [architecture.md](architecture.md#12-security-of-the-system-itself) | 2 | T-311 | Each threat row has a verified control or a filed task; findings recorded, not just listed |
| T-507 | Backup and restore rehearsal (Postgres, Elasticsearch, Kafka) | 1.5 | T-504 | Restore from backup reproduces a known alert set |
| T-508 | Release pipeline: tagged images, changelog generation, metrics section from the eval run | 1.5 | T-006 | A release produces a note whose numbers trace to a recorded run (R-74) |
| T-509 | Documentation set: deploy, operate, tune thresholds, incident runbook | 2 | T-504 | An operator follows the runbook unaided through a simulated incident |
| T-510 | v1.0 release: tag, model cards, published metrics, rollback rehearsed | 1.5 | all | Rollback executed once in a drill and timed |

**E5 total ≈ 17.5 days.**

## 9. Delivery plan

| Sprint | Window | Epic focus | Key tasks | Milestone |
|---|---|---|---|---|
| S0 | 2026-10-05 → 10-16 | E0 | T-001…T-010 | **M0** |
| S1 | 2026-10-19 → 10-30 | E1 | T-101…T-112 | **M1** |
| S2 | 2026-11-02 → 11-13 | E2 | T-201…T-209 | **M2** |
| S3 | 2026-11-16 → 11-27 | E2 + E3 | T-210…T-215, T-301…T-310 | **M3** |
| S4 | 2026-11-30 → 12-11 | E3 + E4 | T-311…T-320, T-401…T-406 | **M4** |
| S5/S6 | 2026-12-14 → 2027-01-08 | E4 + E5 | T-407…T-415, T-501…T-510 | **M5** |
| — | 2027-01-15 | Release | T-510 | **v1.0** |

### 9.1 Capacity — read this before committing to the dates

Total estimate ≈ **136 ideal engineer-days** (8.5 + 18 + 25.5 + 31.5 + 35 + 17.5).

The window from 2026-10-05 to the last working day before the 2027-01-15 ship date contains **74 working days**. At a realistic 65–70% utilisation, one engineer delivers 48–52 of those days. Therefore:

| Staffing | Effective capacity | Verdict |
|---|---|---|
| 2 engineers | 96–104 days | **Under-committed by ~32–40 days.** Finishes 2027-02-16 to 2027-02-26, not 2027-01-15 |
| 3 engineers | 144–156 days | Fits, with 8–20 days of slack. **This is the staffing the dates above assume** |
| 4 engineers | 192–208 days | Comfortable, but E1 and E2 serialise on the data pipeline — a 4th engineer yields little before M2 |

**The milestone dates in §2 are only achievable with three engineers.** With two, either move v1.0 to late February 2027 or cut scope. That is a decision to make now, not in December.

If capacity is fixed at two engineers, defer in this order: T-415 (1.5) → T-408 (3) → T-410 (3) → T-411 (1.5) → T-412 (1.5) → T-213 (1.5) → T-215 (2) → T-210 (1.5) → T-320 (1) → T-409 (2.5) → T-507 (1.5) → T-407 (2.5) → T-214 (1). That removes **24 days, leaving 112** — still 8–16 days above two-engineer capacity, so the balance must come from the ship date. These cuts leave the triage loop, both models, and the API intact.

**Never cut** T-203, T-111, or T-413. Those are the leakage audits and the accessibility pass — the controls that stop the project lying to itself and to its users. A smaller honest product beats a larger unverifiable one.

The schedule risk is **E4 (35 days), not the models**: it is the largest epic, it depends on the API contract being stable, and it is where "almost done" hides.

## 10. Critical path

```
T-001 ─► T-002 ─► T-301 ─► T-304 ─► T-308 ─► T-319 ─► T-501 ─► T-510
  │        └────► T-101 ─► T-107 ─► T-109 ─► T-110 ─► T-201 ─► T-202 ─► T-203 ─┘
  └────► T-004 ─► T-401 ─► T-402 ─► T-404 ─► T-413
```

The longest chain runs through the data pipeline into `FlowNet`, then into the API and load testing. Data work is the schedule owner: a week lost in E1 is a week lost at v1.0.

## 11. Backlog (T-6xx) — explicitly not v1.0

These are parked deliberately per [prd.md](prd.md#32-explicitly-out-of-scope-for-v10). Nothing moves out of this section without a PRD version bump.

| ID | Item | Notes |
|---|---|---|
| T-601 | Encrypted-payload / TLS-fingerprint analysis | Needs JA3/JA4 features; separate feature version |
| T-602 | Phishing-email NLP classifier | Different modality, different data licence |
| T-603 | Endpoint (EDR) telemetry ingestion | Process trees, registry, file events |
| T-604 | SOAR playbooks and automated response | Blocked on the security review in T-506 |
| T-605 | Multi-tenancy with per-tenant models | v1 shares one model pair |
| T-606 | Billing, metering, self-serve signup | Not a product goal |
| T-607 | MITRE ATT&CK mapping of detected families | High value, medium effort — first candidate for v1.1 |
| T-608 | Adversarial-evasion evaluation suite | Documented limitation in v1.0 |
| T-609 | Audit-log hash chaining for tamper evidence | Referenced in [architecture.md](architecture.md#12-security-of-the-system-itself) as post-v1 |
| T-610 | Per-analyst alert-routing and on-call schedules | |
| T-611 | Notebook-free AutoML retraining scheduler | Depends on T-211 drift signal maturing |
| T-612 | Modern-traffic retraining (2024+ captures) | Highest-value post-v1 task; the public datasets are 2015–2017 vintage |

## 12. Risk register

| Risk | Epic | Mitigation owner | Trigger to act |
|---|---|---|---|
| Data pipeline slips and compresses model time | E1 | Data lead | S1 ends with T-107 or T-109 incomplete → cut T-110 baselines to one model, keep the leakage audit |
| Transformer does not beat the baseline | E2 | Model lead | T-201 eval below baseline PR-AUC → investigate features before architecture; ship the baseline with the transformer behind a flag |
| Frontend effort underestimated | E4 | FE lead | T-404 not done by mid-S4 → cut T-408 and T-410 to v1.1 |
| Latency budget missed | E2/E5 | Platform | T-209 p95 > 150 ms → land T-210 (ONNX) early, before M3 |
| Datasets prove unusable (licence, size, corruption) | E1 | Data lead | T-101 checksum failure → fall back to T-106 synthetic for M1 and file the fetch issue |
| Single-engineer bus factor | all | Team | Any epic with one owner and no reviewer → pair on the critical-path task |

## 13. Working agreements

- **One task in progress per engineer.** Finished work beats half-done work.
- **Update this file in the same PR** that changes a task's status. A stale plan is worse than none.
- **Blocked for more than half a day** means it is raised, not silently absorbed.
- **No task starts without acceptance criteria.** If they are missing, writing them is the task.
- **Verification is stated, not implied.** A PR says what command was run and what it returned (R-92).
- **Weekly:** reconcile this file against reality on Friday; move the date, not the criteria.

## 14. Change log

| Date | Version | Change |
|---|---|---|
| 2026-10-02 | 0.1 | Initial work breakdown: 6 epics, 82 delivery tasks, 12 backlog items, plan through v1.0 on 2027-01-15. |
| 2026-10-03 | 0.2 | Added the E1 progress block: T-106 DONE with its verification evidence and the four injection tests; T-101…T-105 recorded as blocked by unreachable dataset hosts. Corrected the E0 test count to 99. |
| 2026-10-03 | 0.3 | T-107 DONE: `features@1` with a hash-pinned 23-feature contract. Recorded the two defects it exposed (out-of-order synthetic timelines; undeclared `import-linter`/`pytest-cov`) and corrected the 24-feature claim in `architecture.md`. |
| 2026-10-03 | 0.4 | T-108 DONE: sliding windowing with count and inactivity triggers, exact-boundary fixture tests, and D-013 closing Q-06. `extract_flow_window` gained a `key` parameter so destination-keyed windows are scorable. |
| 2026-10-03 | 0.5 | T-109 DONE: leakage-safe splits, and D-014 recording that evaluation requires entity churn. |
| 2026-10-03 | 0.6 | T-111 DONE: five-class leakage audit with hand-built bad splits, so it does not merely re-check the splitter. |
| 2026-10-03 | 0.7 | T-112 DONE: the `eval@1` evaluation harness. Corrected `architecture.md` §3 so the ml-service tree matches what is actually importable. |
| 2026-10-03 | 0.8 | The dashboard image ran nginx as root, and the privilege check could not see it because it only covered the two Python Dockerfiles. Check widened to all three; image moved to unprivileged nginx on 8080. Unverified without a daemon. |
| 2026-10-03 | 0.9 | T-001 DONE: `k8s/` manifests for the three workloads, plus `scripts/check_k8s.py` verifying probes, env vars, security context, pinning and HPA/Ingress targets against the real applications. Statically verified only — never applied to a cluster. |
