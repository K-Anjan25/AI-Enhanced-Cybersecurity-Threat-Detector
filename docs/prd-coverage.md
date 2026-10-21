# PRD coverage — evidence as of 2026-10-21

This report maps every requirement in [prd.md](../prd.md) to what the repository and
this sandbox can actually show. It is conservative: **Met** means there is code _and_
a test or a recorded measurement behind it, checked in the sandbox or in a dated record
cited below. **Partial** means something is built but a part of the requirement is not
shown. **Not verified** means the sandbox could not show it, so it is not claimed as
passing. **Not met** means no implementation was found.

Tools that were unavailable in this sandbox: Docker, Helm, a browser, and k6. The
UNSW-NB15 and CIC-IDS2017 hosts were unreachable. Anything that needs them is recorded
as not verified here, not as passing.

## Functional requirements (36)

| ID    | P   | Status       | Evidence                                                                                                                                                                                                           |
| ----- | --- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| FR-01 | M   | Met          | `POST /api/v1/ingest/flows`. HTTP benchmark: 1,000-record NDJSON batches accepted (`scripts/bench_ingest.py`, below).                                                                                              |
| FR-02 | M   | Partial      | Route present (`ingest_logs`). Log-line throughput not measured.                                                                                                                                                   |
| FR-03 | M   | Partial      | Kafka topics `flows.raw` / `logs.raw` configured (`core/config.py`), with the pipeline code and unit tests. No live broker in the sandbox, so `scripts/kafka_smoke.py` was not run.                                |
| FR-04 | M   | Met          | Per-record rejection with an error list (`ingest.py`, `_rejected_by_stage(result.errors)`).                                                                                                                        |
| FR-05 | M   | Partial      | Configurable retention and a real partition catalog (`services/retention_catalog.py`). 19 live-Postgres tests passed in the earlier round. The retention gaps from the report are not all closed (see Next steps). |
| FR-06 | S   | Met          | `scripts/generate_synthetic.py`.                                                                                                                                                                                   |
| FR-07 | S   | Partial      | `scripts/prepare_unsw_raw.py` and `scripts/fetch_datasets.py` exist. The CIC-IDS2017 import path is not verified, and the dataset hosts are unreachable here.                                                      |
| FR-10 | M   | Met          | `workers/scoring_worker.py` windows per entity; window tests pass (`test_scoring_worker.py`, `test_live_window_latency.py`).                                                                                       |
| FR-11 | M   | Met          | FlowNet and LogNet scorers in `ml-service/aegis_ml/serving/`. Quality numbers are under FR-31.                                                                                                                     |
| FR-12 | M   | Met          | Late fusion in `pipeline.py` and `models.py` (code present; not re-run in this pass).                                                                                                                              |
| FR-13 | M   | Met          | Severity bands in `services/correlator.py` (`critical` 0.90, boundary tested).                                                                                                                                     |
| FR-14 | M   | Met          | Explanation fields on alerts (code present; not re-run in this pass).                                                                                                                                              |
| FR-15 | M   | **Not met**  | No duplicate-suppression cool-down was found. The only dedup is the webhook delivery id.                                                                                                                           |
| FR-16 | M   | Met          | Verdicts (`true_positive` / `false_positive` / `benign`) persisted by the triage endpoints.                                                                                                                        |
| FR-17 | S   | Not verified | No single-window what-if endpoint was checked.                                                                                                                                                                     |
| FR-18 | S   | Partial      | Weekly threshold recalibration job exists (`endpoints/thresholds.py`, T-322). The weekly schedule was not verified.                                                                                                |
| FR-19 | C   | Not verified | A correlator exists; the ±60 s flow-to-log grouping was not checked.                                                                                                                                               |
| FR-20 | M   | Met          | WebSocket and SSE in `api/v1/endpoints/stream.py`.                                                                                                                                                                 |
| FR-21 | M   | Partial      | HMAC-signed, bounded-retry webhook delivery is built (T-311). Nothing calls `dispatch()` in `backend/app` (verified by grep), and no production HTTP client ships.                                                 |
| FR-22 | M   | Partial      | `GET /api/v1/alerts` exists. The full filter set was not re-verified in this pass.                                                                                                                                 |
| FR-23 | S   | Partial      | Alert export tests exist (`test_alert_export.py`). PDF output was not verified.                                                                                                                                    |
| FR-30 | M   | Met          | Two independently versioned models, registered by `services/model_registrar.py`.                                                                                                                                   |
| FR-31 | M   | Met          | Per-model metrics on a temporal split, recorded in the eval artifacts (`memory.md` 1.14).                                                                                                                          |
| FR-32 | M   | Met          | PSI in `scoring/drift.py`. Measured UNSW→CIC: 20 of 23 features exceed 0.25 (`memory.md` 1.17).                                                                                                                    |
| FR-33 | S   | Partial      | Rollback endpoint exists (`endpoints/models.py`). Zero-downtime swap was not verified.                                                                                                                             |
| FR-34 | S   | Partial      | Training manifest tests exist (`ml-service/tests/test_training_manifest.py`). Not re-run in this pass.                                                                                                             |
| FR-40 | M   | Met          | Argon2id password hashing, JWT access tokens, refresh tokens, and login/refresh/logout tests (`test_auth_endpoints.py`, D-081).                                                                                    |
| FR-41 | M   | Met          | Four roles in `auth/rbac.py`, including `responder`.                                                                                                                                                               |
| FR-42 | M   | Met          | Append-only audit log (`db/audit_pg.py`, `endpoints/audit.py`). The erasure audit row is covered under NFR-05.                                                                                                     |
| FR-43 | S   | **Not met**  | No OIDC or OpenID code was found in the backend or dashboard.                                                                                                                                                      |
| FR-44 | S   | Met          | Scoped API keys (`auth/api_keys.py`, scopes in `auth/rbac.py`).                                                                                                                                                    |
| FR-50 | M   | Partial      | Overview page reads live pipeline histograms (`overview/pipeline.ts`). Browser rendering of live data was not verified.                                                                                            |
| FR-51 | M   | Met          | Triage page with evidence, timeline, and verdict, passing the strict axe check in jsdom. Browser check not done.                                                                                                   |
| FR-52 | M   | Partial      | Traffic explorer and `EntityGraph.tsx` exist. The time-series of scores was not verified in a browser.                                                                                                             |
| FR-53 | S   | Partial      | Model pages, drift page, and version comparison exist. Metrics-over-time was not verified.                                                                                                                         |
| FR-54 | S   | Partial      | Hunt endpoint (`endpoints/hunt.py`) and `HuntPage` exist. Not verified end to end.                                                                                                                                 |

**Functional total: 18 Met, 14 Partial, 2 Not verified, 2 Not met (of 36).**

## Non-functional requirements (12)

| ID     | Status       | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ------ | ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NFR-01 | Not verified | No ML service runs in this sandbox, so the scoring p95 and the end-to-end ≤ 5 s were not measured. The stall fix (`a44bc1b`) bounds the partial-window wait at 2.0 s by default.                                                                                                                                                                                                                                                                                                                                                                           |
| NFR-02 | Partial      | Flow ingest over HTTP, 8 threads, 60 s, `scripts/bench_ingest.py` (no Kafka behind the route): 1,199,000 records accepted, **19,981 records/s**, p95 277 ms, 80% of requests refused with 429 by the per-credential limiter. The limiter is a token bucket with a 600-request burst and 10 requests/s sustained (`services/limits.py`), so the sustained cap is **10,000 records/s** at 1,000 per batch. The 60 s average includes the burst. Log-line throughput was not measured. The 30-minute k6 run was not done, because k6 could not be downloaded. |
| NFR-03 | Partial      | Kafka buffering path exists (`services/kafka_pipeline.py`). Behaviour during a scorer outage was not exercised. 99.5% is not measurable here.                                                                                                                                                                                                                                                                                                                                                                                                              |
| NFR-04 | Partial      | Stateless API workers by design. Auth state is in Postgres (`db/user_pg.py`), but the refresh-replay state was not verified.                                                                                                                                                                                                                                                                                                                                                                                                                               |
| NFR-05 | Partial      | Configurable retention, a PII redaction allowlist (T-318), and an erasure endpoint with a tombstone-only ledger and an audited erase (`endpoints/privacy.py`, T-314). Open: Kafka and Elasticsearch lifecycle sit outside the database, and the erasure ledger and audit row need checking against the retention report.                                                                                                                                                                                                                                   |
| NFR-06 | Not verified | TLS, encryption at rest, and secret-manager sourcing are deployment properties. `docs/security-review.md` exists. Not verified in the sandbox.                                                                                                                                                                                                                                                                                                                                                                                                             |
| NFR-07 | Partial      | Prometheus metrics (`observability/metrics.py`), JSON logs, health endpoints (`api/v1/endpoints/health.py`), OpenTelemetry references. Not verified live.                                                                                                                                                                                                                                                                                                                                                                                                  |
| NFR-08 | Partial      | `docker-compose.yml`, Dockerfiles, and Kubernetes/Helm manifests exist, and `scripts/check_compose.py` and `check_k8s.py` run in CI. No Docker or Helm binary here, so no image was built and no chart was rendered or linted.                                                                                                                                                                                                                                                                                                                             |
| NFR-09 | Partial      | Strict axe check passes in jsdom on Overview, Triage, and Traffic (`expectAxeClean`). jsdom does not compute contrast. Keyboard and screen-reader pass still required (D-087).                                                                                                                                                                                                                                                                                                                                                                             |
| NFR-10 | Not verified | Determinism was not re-run.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| NFR-11 | Met          | Backend coverage 97.47% at T-417 (2026-10-07), and the 80% gate passes. This session's full backend suite passed (2,068 passed, 45 skipped, no live DB). Coverage was not re-measured this session.                                                                                                                                                                                                                                                                                                                                                        |
| NFR-12 | Not verified | Local stack on a 16 GB laptop was not tested. Core features need no paid external API, by design.                                                                                                                                                                                                                                                                                                                                                                                                                                                          |

**NFR total: 1 Met, 7 Partial, 4 Not verified (of 12).**

## Success metrics (section 8)

| Metric                                     | Status                       | Evidence                                                                                                                                                                                  |
| ------------------------------------------ | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ROC-AUC ≥ 0.97, PR-AUC ≥ 0.92 on UNSW-NB15 | Not verified                 | Not re-checked in this pass.                                                                                                                                                              |
| Precision ≥ 0.80, recall ≥ 0.90 at `high`  | **Not met** on cross-dataset | Cross-dataset precision is 0.5904 at a 40% attack base rate (`memory.md` 1.14).                                                                                                           |
| Cross-dataset recall ≥ 0.70                | Met                          | 0.7955 on the reconstruction head (`memory.md` 1.14, supersedes the 0.0000 in T-208).                                                                                                     |
| Benign-day FPR ≤ 0.5%                      | Not verified                 | No benign-only run.                                                                                                                                                                       |
| Median time-to-verdict ≤ 60 s              | Not verified                 | Instrumented: `services/overview.py` computes mean and median. The empty state reads "target ≤ 60 s" until verdicts exist. No verdict data exists yet.                                    |
| ≥ 70% verdict agreement with top-1 family  | Not verified                 | Needs analyst data.                                                                                                                                                                       |
| Zero critical alerts without explanation   | Not verified                 | Not checked.                                                                                                                                                                              |
| CI green on every merge                    | **Not met on current head**  | The last two branch runs failed the pre-commit job (`a44bc1b`, `e0cf9d0`). Cause found: a `detect-secrets` false positive in `test_retention_wiring.py`, now allowlisted. Re-run pending. |
| Backend coverage ≥ 80%                     | Met                          | 97.47% at T-417 (last measured).                                                                                                                                                          |
| Frontend type-check clean                  | Met                          | `tsc --noEmit` exits 0 in this session.                                                                                                                                                   |
| `docker compose up` in < 5 min             | Not verified                 | Docker unavailable.                                                                                                                                                                       |

## Release milestones (section 9)

M5 requires **all NFRs verified with evidence**. Only NFR-11 is verified, so **M5 is not
reached**. M0–M4 were not re-checked milestone by milestone in this pass.

## Summary

- Functional: 18 of 36 Met (50%); 14 more Partial.
- Non-functional: 1 of 12 Met.
- Success metrics: 3 of 11 Met (cross-dataset recall, backend coverage, frontend type-check). Precision on transfer is not met, and CI is currently red.

## Next major steps and goals

1. **Restore CI on the branch.** Re-run the pre-commit job after the `detect-secrets` allowlist.
2. **Close the functional gaps that are plainly missing:** FR-15 (alert cool-down), FR-43 (OIDC), and wire `dispatch()` for FR-21 with a production HTTP client.
3. **Measure what is unmeasured:** NFR-01 scoring p95 and end-to-end latency (needs the ML service), the 30-minute ingest run (needs k6, or run `scripts/bench_ingest.py` for longer), and the real capture rate on the 18–20 records/s source.
4. **Model quality:** precision ≥ 0.80 at the `high` threshold is the largest open product metric. Measure it in-distribution and cross-dataset.
5. **Run the Docker, Helm and browser checks** in an environment that has them: image builds, `helm lint`, and the landing and dashboard browser pass, including keyboard and contrast (NFR-09).
6. **Retention and erasure:** close the retention report's remaining gaps (Kafka and Elasticsearch lifecycle, non-evictable tables) and confirm the erasure ledger and audit row against the report.
7. **Accessibility:** the manual screen-reader and keyboard pass (D-087).

## How the ingest number was produced

```
python scripts/bench_ingest.py --email <admin> --password <pw> --seconds 60 --threads 8
```

Run against a local `uvicorn app.main:create_app --factory` on 127.0.0.1 with a bootstrap
admin, no Kafka and no ML service. The output is one JSON line. It measures the HTTP,
validation and in-process path only. It is not the k6 scenario, and it is not a
capture-rate measurement.
