# Coding Rules — AI-Enhanced Cybersecurity Threat Detector (AEGIS)

| | |
|---|---|
| **Document** | Engineering rules and conventions |
| **Version** | 0.1 |
| **Last updated** | 2026-10-02 |
| **Status** | Binding — these rules gate review and CI |
| **Related** | [prd.md](prd.md) · [architecture.md](architecture.md) · [design.md](design.md) · [task.md](task.md) · [memory.md](memory.md) |

---

## 0. How to use this document

Every rule has an ID, a statement, and an **enforcement** column telling you what stops a violation: `CI` (automated, blocks merge), `REVIEW` (a human must catch it), or `SELF` (your responsibility, spot-checked).

Rules are **binding**. If a rule is wrong or blocking good work, change the rule in a PR that says why — do not quietly ignore it. Rules marked **MUST** are hard; **SHOULD** may be broken with a one-line justification in the PR description.

Legend: 🔒 = security-relevant, break it and the PR is rejected regardless of quality.

---

## 1. Universal rules

| ID | Rule | Enforcement |
|---|---|---|
| R-01 | **MUST** Write code that a new engineer can read in one sitting. If a function needs a comment explaining *what* it does, rewrite the function. | REVIEW |
| R-02 | **MUST** Every public function has a docstring stating what it does, what it raises, and what it returns. No docstring restating the signature. | CI (ruff `D`) |
| R-03 | **MUST** No dead code, no commented-out code, no `TODO` without an owner and a task ID (`TODO(T-204): ...`). | CI |
| R-04 | **MUST** No magic numbers. Named constants live in a `constants.py` / `constants.ts` module with a comment on why the value is what it is. | REVIEW |
| R-05 | **MUST** Errors are raised as typed exceptions and handled at a boundary. Never swallow an exception with a bare `except: pass` or an empty `catch {}`. | CI |
| R-06 | **MUST** Fail loudly and honestly. A component that cannot do its job returns an explicit error state — never a silent empty result, a fabricated default, or a `null` that looks like success. | REVIEW |
| R-07 | **SHOULD** Prefer the standard library and existing dependencies over adding a new one. A new dependency requires a line in the PR description: what it replaces and why it is worth the supply-chain risk. | REVIEW |
| R-08 | **MUST** All dependency versions are pinned via lockfile. No floating ranges in deployed artifacts, no `latest` tags. | CI |
| R-09 | **MUST** Directory layout follows [architecture.md](architecture.md#3-repository-layout). New top-level directories require an architecture-doc update in the same PR. | REVIEW |
| R-10 | **MUST** Every file ends with a newline; UTF-8; LF line endings; max line length 100 (Python) / 100 (TS). | CI |

## 2. Python and backend rules

| ID | Rule | Enforcement |
|---|---|---|
| R-11 | **MUST** Python 3.11+ (3.11.2 is the verified baseline in the dev sandbox). Type hints on every public function signature, including return types. `mypy --strict` clean on `app/services` and `aegis_ml`. | CI |
| R-12 | **MUST** `ruff` and `black` clean. No `# noqa` without a trailing reason comment. | CI |
| R-13 | **MUST** FastAPI routers are thin: parse, call a service, serialise. No SQL, no business logic, no ML code in a router. | REVIEW |
| R-14 | **MUST** All request/response bodies are Pydantic models declared in `schemas/`. No `dict` in or out of a route. | CI |
| R-15 | **MUST** Services must not import FastAPI. Business logic is testable without an HTTP server. | CI (import-linter contract) |
| R-16 | **MUST** Database access goes through a repository/session helper; one transaction boundary per request, opened explicitly. No implicit session sharing across awaits. | REVIEW |
| R-17 | **MUST** All SQL uses bound parameters. String-formatted SQL is a 🔒 security defect. | CI (bandit) |
| R-18 | **MUST** Async I/O everywhere in the request path. Blocking calls (`requests`, sync DB drivers, `time.sleep`) in async code are defects — use `httpx`, `asyncpg`, `asyncio.sleep`. | REVIEW |
| R-19 | **MUST** Configuration is read from the environment through a single `core/config.py` with typed fields and validation. No `os.getenv` scattered through modules. | CI |

## 3. TypeScript and frontend rules

| ID | Rule | Enforcement |
|---|---|---|
| R-20 | **MUST** TypeScript strict mode. No `any`. `unknown` + narrowing, or a real type. | CI (`tsc --noEmit`) |
| R-21 | **MUST** `eslint` + `prettier` clean. No `eslint-disable` without a reason comment on the same line. | CI |
| R-22 | **MUST** Feature-sliced structure: components import from `components/ui`, `lib`, `hooks`, `api` — never from another feature's internals. | CI (import boundaries) |
| R-23 | **MUST** Components never call `fetch`/`axios` directly. All network access goes through a typed client in `src/api/`. | CI |
| R-24 | **MUST** Server state lives in TanStack Query; never in `useState` or a global store. Client-only UI state (open/closed, filters) lives in local state or Zustand. | REVIEW |
| R-25 | **MUST** No detection logic in the browser: no scoring, no severity derivation, no threshold math. Display, filter, format — nothing more. | REVIEW |
| R-26 | **MUST** Every interactive element is keyboard reachable and has an accessible name. Non-text content gets `aria-label` or `alt`. | CI (eslint-plugin-jsx-a11y) + REVIEW |
| R-27 | **MUST** No inline styles for anything covered by a design token. Colours, spacing, radii, and fonts come from the tokens in [design.md](design.md#5-design-tokens). | CI (stylelint) |
| R-28 | **MUST** Untrusted strings (log content, alert explanations, usernames) are rendered as text, never as HTML. No `dangerouslySetInnerHTML`. | CI 🔒 |
| R-29 | **MUST** Every list and async view has explicit loading, empty, and error states. A spinner that never resolves into one of the three is a defect. | REVIEW |

## 4. Data and persistence rules

| ID | Rule | Enforcement |
|---|---|---|
| R-30 | **MUST** Every table has `created_at` (timestamptz, UTC) and — where mutable — `updated_at`. Timestamps are always timezone-aware UTC. | REVIEW |
| R-31 | **MUST** `audit_log` is append-only. No ORM update/delete methods, no migration that alters existing audit rows. Editing history is a 🔒 defect. | REVIEW 🔒 |
| R-32 | **MUST** Schema changes go through a migration. No hand-edited production schemas, no ORM `create_all` outside tests. | CI |
| R-33 | **MUST** Migrations are reversible or explicitly documented as irreversible with the reason in the migration docstring. | REVIEW |
| R-34 | **MUST** Time-partitioned tables (`alerts`, `ingest_stats`) are only queried with a time-range predicate. Unbounded scans are defects. | REVIEW |
| R-35 | **MUST** No `SELECT *` in application code. Name the columns. | CI |
| R-36 | **MUST** Every new index ships with the query it serves, named in the migration comment. | REVIEW |
| R-37 | **MUST** Deletes of user data happen through the retention/erasure service, which cascades and logs. No ad-hoc `DELETE` for privacy requests. | REVIEW 🔒 |
| R-38 | **MUST** Enum values are defined once (Python enum + DB check constraint) and validated on both sides. Free-text status strings are defects. | CI |
| R-39 | **MUST** Money-free, but precision matters: scores are `numeric(5,4)`, never float, in the DB. | REVIEW |

## 5. Data assets and dataset rules

| ID | Rule | Enforcement |
|---|---|---|
| R-40 | **MUST** Datasets are **never** committed to Git. Raw and processed data live in `data/` which is gitignored. Fetch them with `scripts/fetch_datasets.py`, which verifies checksums. | CI (file-size + gitignore check) |
| R-41 | **MUST** Every dataset has a recorded source URL, licence, and SHA-256 in [memory.md](memory.md#data-sources) before it is used in any training run. | REVIEW |
| R-42 | **MUST** Synthetic data generators are seeded and deterministic. A test asserts the same seed produces the same bytes. | CI |
| R-43 | **MUST** No real customer, employee, or personal data in fixtures, tests, screenshots, or documentation. Use the documented fake identities. | REVIEW 🔒 |
| R-44 | **MUST** Data transformations are versioned (`features@1`). Changing a feature definition requires a version bump and a note in the training manifest — never an in-place edit. | REVIEW |
| R-45 | **MUST** Parsed datasets are stored as Parquet with a schema file. CSV is an interchange format, not a storage format, past the fetch step. | REVIEW |
| R-46 | **MUST** Nothing that looks like a secret, token, key, or credential may appear in any file, log line, or commit — including in datasets. The pre-commit secret scan is not bypassable. | CI 🔒 |

## 6. Security and privacy rules

| ID | Rule | Enforcement |
|---|---|---|
| R-50 | **MUST** 🔒 Secrets come from the environment or secret manager. Never hardcoded, never in images, never in compose files, never in Git history. `.env` is gitignored; `.env.example` holds placeholder values only. | CI 🔒 |
| R-51 | **MUST** 🔒 Passwords are hashed with Argon2id. Never MD5/SHA1/bcrypt-with-low-cost for new code. | CI (bandit) 🔒 |
| R-52 | **MUST** 🔒 Authorisation is checked server-side on every route via a dependency. Frontend route guards are cosmetic and never the control. | REVIEW 🔒 |
| R-53 | **MUST** 🔒 RBAC roles: `viewer` (read), `analyst` (read + verdict), `responder` (analyst + export + webhook config), `admin` (users, models, retention). Escalation paths are explicit. | CI (route-role matrix test) 🔒 |
| R-54 | **MUST** 🔒 No PII in logs. Usernames and hostnames are redacted or salted-hashed before logging. Structured log fields are allowlisted. | REVIEW 🔒 |
| R-55 | **MUST** 🔒 Outbound webhook URLs are validated against an allowlist; private/link-local IP ranges are rejected (SSRF control). | CI 🔒 |
| R-56 | **MUST** 🔒 Rate limiting on every unauthenticated and every write endpoint. | CI |
| R-57 | **MUST** 🔒 Dependency and image scanning runs in CI. Known-critical CVEs block merge. | CI |
| R-58 | **MUST** 🔒 Alert data is sensitive. No alert content in error messages, stack traces, or client-side telemetry. | REVIEW |
| R-59 | **MUST** 🔒 The `debug`/auto-reload server flags are never enabled in a deployed image. | CI |

## 7. Machine learning rules

| ID | Rule | Enforcement |
|---|---|---|
| R-60 | **MUST** **Temporal splits only.** Train/valid/test are split by timestamp, test strictly later. A random shuffle split is a defect — it leaks the future into the past. | CI (split test asserts monotonic time) |
| R-61 | **MUST** **Entity-disjoint folds.** Cross-validation folds must not share source entities, or the model memorises hosts instead of behaviour. | CI |
| R-62 | **MUST** No data leakage: scalers, vocabularies, and template dictionaries are **fit on train only** and applied to valid/test. Fitting on the full dataset is a defect. | CI (leak audit test) |
| R-63 | **MUST** Every model artifact ships a `training_manifest.json`: dataset names + SHA-256, git SHA, config, seeds, all metrics, and the baseline it was compared against. An artifact without a manifest cannot be promoted. | CI |
| R-64 | **MUST** A non-deep baseline (logistic regression or gradient boosting on the same features) is trained and recorded for every feature set. The transformer must beat it, or the PR says why it is still worth shipping. | REVIEW |
| R-65 | **MUST** Report **precision, recall, F1, ROC-AUC, and PR-AUC** on every evaluation. Accuracy alone is never an acceptable metric on this dataset's class imbalance. | CI (eval harness output schema) |
| R-66 | **MUST** Cross-dataset transfer is reported for every release: trained on UNSW-NB15, evaluated on CIC-IDS2017. A collapse in transfer recall is a release blocker, not a footnote. | REVIEW |
| R-67 | **MUST** Fixed seeds everywhere in training; inference is deterministic and side-effect free (NFR-10). No wall-clock reads, no `random` without an explicit seeded generator, no ambient config inside the scoring path. | CI (determinism test) |
| R-68 | **MUST** Model versions are immutable and content-addressed. No `latest`, no overwriting an artifact, no in-place weight edits. | REVIEW |
| R-69 | **MUST** Threshold changes are data and audited. No hardcoded thresholds in inference code; they are read from the `thresholds` table with the PRD defaults as the documented initial values. | REVIEW |
| R-70 | **MUST** Every alert carries an explanation. If explanation generation fails, the alert is still raised but marked `explanation_unavailable` — never silently dropped or blank-filled. | CI (contract test) |
| R-71 | **MUST** No hyperparameter tuning on the test set. Tuning uses the validation split; the test split is touched once per release and the result is recorded. | REVIEW |
| R-72 | **MUST** Feature definitions are code, not notebook state. Notebooks are for exploration and are not part of the shipped pipeline. | REVIEW |
| R-73 | **SHOULD** Track runs (config + metrics + manifest) in an experiment tracker; at minimum, a `runs/` append-only JSONL log committed outside Git or stored in the artifact store. | SELF |
| R-74 | **MUST** Never claim a metric you did not measure. Every number in the README, PRD, or release note must trace to a recorded run. Fabricated or "expected" numbers are treated as a 🔒 honesty defect. | REVIEW |

## 8. Testing rules

| ID | Rule | Enforcement |
|---|---|---|
| R-80 | **MUST** Backend line coverage ≥ 80%. Coverage is a floor, not a target — a covered assertion-free test counts as zero. | CI |
| R-81 | **MUST** Test names state behaviour: `test_ingest_rejects_batch_with_malformed_record`. No `test_1`, no `test_stuff`. | REVIEW |
| R-82 | **MUST** One behaviour per test. If you need "and" in the test name, split it. | REVIEW |
| R-83 | **MUST** Tests are deterministic and isolated: no network, no sleeping on wall clock (use a fake clock), no ordering dependencies, no shared mutable fixtures. | CI |
| R-84 | **MUST** Tests must not require the real datasets. Small generated fixtures (R-42) cover unit and integration tests; dataset-dependent tests are marked `@pytest.mark.dataset` and skipped by default. | CI |
| R-85 | **MUST** Every bug fix ships with a failing-first regression test. The PR shows the test failing before the fix. | REVIEW |
| R-86 | **MUST** API contract tests assert status code, response schema, and RBAC outcome for every route. A new route without a contract test fails CI. | CI |
| R-87 | **MUST** Frontend tests cover user-visible behaviour, not implementation details. Query by role/label, not by class name or test-id-only. | REVIEW |
| R-88 | **MUST** A golden end-to-end test runs the full path: synthetic traffic → ingest → score → alert appears via the API. It must pass in CI without Docker-in-Docker by using in-process fakes for Kafka/ES. | CI |
| R-89 | **SHOULD** Flaky tests are quarantined within 24 hours of first observation and fixed or deleted within a week. A test nobody trusts is worse than no test. | SELF |

## 9. Git, review and release rules

| ID | Rule | Enforcement |
|---|---|---|
| R-90 | **MUST** Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `perf:`. Subject ≤ 72 chars, imperative mood. | CI (commitlint) |
| R-91 | **MUST** One logical change per PR. Unrelated refactors go in their own PR. | REVIEW |
| R-92 | **MUST** PR description states: what changed, why, how it was verified (the actual command and its output), and any rule intentionally broken with justification. | REVIEW |
| R-93 | **MUST** No force-push to shared branches. `main` is protected; merges require green CI. | CI 🔒 |
| R-94 | **MUST** Every PR that changes behaviour updates the relevant doc: PRD for scope, architecture for structure, design for UI, memory for decisions. | REVIEW |
| R-95 | **MUST** Releases are tagged `vMAJOR.MINOR.PATCH` with a changelog generated from commits and a metrics section sourced from the recorded eval run (R-74). | REVIEW |
| R-96 | **MUST** Never commit build output, model artifacts, `.env`, caches, or editor config. `.gitignore` is authoritative. | CI |
| R-97 | **SHOULD** Squash-merge to keep history linear and readable. | SELF |

---

## 10. Definition of Done

A task is **done** only when all of the following are true. "It works on my machine" is not done.

- [ ] Acceptance criteria in [task.md](task.md) are met, each one demonstrably, not approximately.
- [ ] Code passes lint, typecheck, and the full test suite locally — and in CI.
- [ ] New behaviour has tests; coverage floor maintained (R-80).
- [ ] No new rule violation, or the exception is justified in the PR.
- [ ] Relevant doc updated (R-94).
- [ ] No secrets, PII, or dataset files in the diff (R-40, R-46, R-50, R-54).
- [ ] Error, loading, and empty states handled where UI is touched (R-29).
- [ ] Metrics/observability added where a new failure mode was introduced (NFR-07).
- [ ] The author has run the feature end to end and can name the code path the check executed.

## 11. Review checklist

Reviewers, check in this order — stop at the first failure:

1. **Correctness** — does it do what the task's acceptance criteria say? Did the author verify it, and is the verification evidence in the PR?
2. **Security** — any R-50…R-59 or R-40…R-46 issue? Any new input that crosses a trust boundary without validation?
3. **Data integrity** — leakage, mutation of history, missing migrations, unbounded queries (R-30…R-39, R-60…R-62).
4. **Honesty** — are errors surfaced or hidden? Are reported numbers real (R-06, R-74)?
5. **Readability** — could a newcomer follow this in one sitting?
6. **Tests** — do they assert behaviour, and would they fail if the code broke?
7. **Docs** — is the right document updated?

## 12. Change log

| Date | Version | Change |
|---|---|---|
| 2026-10-02 | 0.1 | Initial rule set established alongside the repository reset. |
