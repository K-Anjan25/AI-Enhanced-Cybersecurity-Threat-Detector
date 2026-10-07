# Contributing to AEGIS

How to set up, run, test, and extend the project. For _what_ we are building read
[prd.md](prd.md); for _why it is shaped this way_ read [architecture.md](architecture.md); for the
binding rules read [rules.md](rules.md).

## Setup

Requires Python 3.11+ (3.11.2 verified) and Node 22.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt          # ruff, black, mypy, bandit, pre-commit
pip install -e "backend[dev]" -e "ml-service[dev]"

cd dashboard && npm ci && cd ..

# Both hook types: the file hooks, and commitlint on the commit message.
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

The hooks run the linters from pinned mirrors, but prettier, stylelint and commitlint
run the binaries the dashboard pins — see the header of `.pre-commit-config.yaml` for why.
That is why `npm ci` is part of setup and not optional.

## Run everything

```bash
./scripts/check_all.sh              # every check CI runs
./scripts/check_all.sh backend      # one suite: docs|infra|backend|ml|dashboard|hooks
```

`check_all.sh` requires an activated virtualenv and refuses to install into the system
interpreter. It prints a pass/fail summary and exits non-zero on the first failure — read the
output; a clean exit code alone is not a pass.

Its `hooks` suite scans every file the commit will contain, untracked ones included. That is
deliberate: plain `pre-commit run --all-files` means `git ls-files` and therefore skips a file
that has not been `git add`ed yet, which CI — checking out the commit — does scan.

## Run one service

```bash
# backend — http://localhost:8000/healthz and /readyz
cd backend && cp .env.example .env      # then set AEGIS_SECRET_KEY
uvicorn app.main:app --reload

# ml-service — http://localhost:8001/internal/healthz
cd ml-service
uvicorn aegis_ml.serving.app:app --port 8001

# dashboard — http://localhost:5173
cd dashboard && npm run dev
```

`AEGIS_SECRET_KEY` is required and rejects placeholder and low-entropy values. Generate one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## The whole stack

```bash
docker compose -f docker/docker-compose.yml up
```

This needs Docker. **The compose file has not been executed in the current development
sandbox, where Docker is unavailable** — see [task.md](task.md) T-005. Its contents are
statically verified against the application code by `scripts/check_compose.py`.

## Before you open a PR

1. `./scripts/check_all.sh` passes.
2. Acceptance criteria in [task.md](task.md) are met, each one demonstrably.
3. The relevant document is updated — PRD for scope, architecture for structure, design for
   UI, memory for decisions (R-94).
4. Your PR description says what you ran and what it returned (R-92).

The Definition of Done is [rules.md §10](rules.md#10-definition-of-done).

## How to add an API endpoint

1. **Schema first.** Add request and response models in `backend/app/schemas/`. No `dict` crosses
   a route boundary (R-14).
2. **Logic in a service.** Put behaviour in `backend/app/services/`. Services must not import
   FastAPI — an import-linter contract fails the build if they do (R-15).
3. **Thin router.** Add the route under `backend/app/api/v1/endpoints/`. Parse, call the service,
   serialise. Nothing else (R-13).
4. **Authorisation.** Apply the RBAC dependency. Add the route to the route-role matrix test; a
   route missing from the matrix fails CI (R-53).
5. **Contract test.** Assert status code, response schema, and the RBAC outcome (R-86).

Verify: `./scripts/check_all.sh backend`.

## How to add a model

1. **Features are code.** Feature definitions live in `ml-service/aegis_ml/features/` and are
   versioned (`features@1`). Changing a definition means a version bump, never an in-place edit
   (R-44).
2. **Model module.** Add it under `ml-service/aegis_ml/models/`. Inference must be deterministic:
   no clock reads, no unseeded randomness, no ambient config (R-67).
3. **Register it.** Load it through `ModelRegistry`. Versions are immutable and content-addressed;
   there is no `latest`, and only one version per kind may be `active` (R-68).
4. **Record the manifest.** `training_manifest.json` with dataset hashes, git SHA, config, seeds,
   and metrics. An artifact without a manifest cannot be promoted (R-63).
5. **Beat the baseline.** Train and record the non-deep baseline for the same features. Report
   precision, recall, F1, ROC-AUC **and** PR-AUC; accuracy alone is never acceptable here (R-65).

Verify: `./scripts/check_all.sh ml`, then record real numbers in
[memory.md](memory.md#ledger--measurements).

## How to add a page

1. **Feature folder.** Create `dashboard/src/features/<domain>/pages/`. Never import from another
   feature's internals (R-22).
2. **Route.** Register it in `dashboard/src/App.tsx`. A route with no screen renders the explicit
   "not built" state — never a blank panel (design.md §8.1).
3. **Tokens only.** Colours, spacing, radii, and fonts come from the design tokens. No inline
   styles for anything a token covers (R-27).
4. **Data through the API layer.** Components never call `fetch` directly; eslint enforces this
   (R-23).
5. **States.** Loading, empty, error, partial, and stale are all required (R-29).
6. **Accessibility.** Interactive elements need an accessible name and keyboard reach. The WCAG
   contrast suite in `src/theme/tokens.test.ts` fails if a token drops below 4.5:1.

Verify: `./scripts/check_all.sh dashboard`.

## Datasets

Datasets are never committed (R-40). Fetch them into `data/raw/` and record the source, licence,
and SHA-256 in [memory.md](memory.md#data-sources) before using them in a training run.

The public datasets cannot be downloaded from the current development sandbox, whose network is
allowlisted to package registries. See the sandbox note in
[memory.md](memory.md#environment-and-setup).

## Synthetic data

Until the public datasets are reachable, generate labelled telemetry locally:

```bash
python scripts/generate_synthetic.py --per-scenario 500 --seed 7   # balanced set
python scripts/generate_synthetic.py --scenario beaconing --count 100
```

Output is NDJSON under `data/synthetic/`, which is gitignored. Records validate against the
`flow@1` and `log@1` models in `ml-service/aegis_ml/data/records.py`; the same seed always
produces byte-identical files (R-42), so a test can pin an expected checksum.

Seven scenarios are available: `normal`, `port_scan`, `ddos`, `brute_force`, `beaconing`,
`exfiltration`, `insider_threat`. Only `brute_force` and `insider_threat` produce log records;
asking for another scenario's logs raises rather than returning an empty list, because an empty
list would read as "nothing anomalous".

Two things to keep in mind when you use this data:

- **Scores on synthetic data measure the pipeline, not field performance.** The scenarios are
  shaped to be separable by the features the PRD names. Say so wherever a number is reported.
- **Derived quantities are not fields.** Byte ratio, port entropy and destination counts are
  computed during feature extraction (T-107) so a feature change never rewrites stored data.

### How to add a scenario

1. Add a member to `Scenario` in `ml-service/aegis_ml/data/synthetic.py` and its label in
   `LABELS`. The label must be one of the threat families in [prd.md](prd.md), not a new name.
2. Write a `_your_scenario(spec) -> list[FlowRecord]` builder using `_flow`, and register it in
   `_BUILDERS`. Every call must draw from `_rng(spec)` — never the global `random` — or
   determinism is lost.
3. Offsets passed to `_flow` must be non-negative; it raises otherwise, so a scenario can never
   emit records dated before `spec.start`.
4. If the scenario has a log-side signature, add a `_your_scenario_logs` builder and register it
   in `_LOG_BUILDERS` — that table is what `generate_logs` and the CLI branch on.
5. Add tests in `ml-service/tests/test_synthetic.py` for the features that make the scenario
   detectable, then confirm they can fail: inject a violation, watch the test go red, revert.

## Conventions that catch people out

- **Timestamps** are timezone-aware UTC, always (R-30).
- **`audit_log` is append-only.** There is no update or delete path, by design (R-31).
- **Splits are temporal and entity-disjoint.** A random shuffle split is a defect — it leaks the
  future into the past (R-60, R-61).
- **Never fabricate a number.** Every metric traces to a recorded run (R-74).
- **Never hide a failure.** A component that cannot do its job says so (R-06).
