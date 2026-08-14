# Load tests — NFR-PERF baseline

Automated load tests that verify the performance targets in
[`docs/non-functional-requirements.md`](../docs/non-functional-requirements.md).
Two suites cover the same scenarios: **[k6](https://k6.io)** (JS, CI-friendly,
thresholds fail the run) and **Locust** (Python, web UI + CSV/HTML reporting).

## Targets ↔ scenarios

| NFR | Scenario | Endpoint | Target |
| --- | --- | --- | --- |
| NFR-PERF-01 | Single-record analysis | `POST /api/v1/analyze` | p95 ≤ 500 ms |
| NFR-PERF-02 | Batch scan throughput | `POST /api/v1/upload-logs` (+ poll) | ≥ 100 lines/s |
| NFR-PERF-03 | Concurrent scans | background-task soak | no starvation at ≥ 10 |
| NFR-PERF-04 | Paginated alert listing | `GET /api/v1/alerts?limit=100` | p95 ≤ 200 ms @ 10k alerts |
| NFR-PERF-05 | ML prediction throughput | `POST /predict/*` on ml-service | ≥ 50 predictions/s/replica |

Both suites authenticate once (register + login), then reuse a bearer token, so
the measured numbers are for the analysed paths, not auth setup.

## Run (k6)

Requires [k6](https://grafana.com/docs/k6/latest/installation/) and a running
stack (docker compose or k8s):

```bash
k6 run -e BASE_HOST=http://localhost:8000 -e ML_HOST=http://localhost:8001  \
       -e TOKENPASS='ChangeMe#2026' threat-ai.js
```

`BASE_HOST` is any reachable API root (e.g. the k8s ingress
`https://dashboard.example.com/api/v1`). Thresholds are enforced by k6, so a
ratio that misses a target exits non-zero (CI-failing).

## Run (Locust)

```bash
python -m venv .venv && .venv\Scripts\activate   # or: source .venv/bin/activate
pip install locust

# backend NFR-PERF-01..04
locust -f locustfile.py -H http://localhost:8000 --headless \
       -u 20 -r 4 -t 90s --csv baseline-backend --html report-backend.html

# ml-service NFR-PERF-05 (steady arrival, 50+ req/s)
locust -f ml-locustfile.py -H http://localhost:8001 --headless \
       -u 50 -r 10 -t 30s --csv baseline-ml --html report-ml.html
```

Interactive mode (drop `--headless ...`) opens the web UI at http://0.0.0.0:8089.

## Reading a baseline

- p95 latencies per endpoint are in the CSV (`baseline-*.stats.csv`, column
  `95%`) and the HTML report.
- Throughput is the `rps` column; for NFR-PERF-05 compare `/predict/log` rps to
  ≥ 50.
- NFR-PERF-02/03: each `upload-logs` posts 100 lines; the poll loop confirms the
  background scan completes. Watch `uploads/{id}` failures and duration — a
  starvation would show up as tasks sitting in `processing`.

## Recorded baseline (2026-08-14, docker compose stack on an 8 GB laptop)

Host: Windows 11, 8 GB RAM / 4 GB VRAM, WSL2 (memory=2GB), Docker Desktop,
compose stack with `cpus: 0.5` per service. Locust 2.46 headless.

**Unloaded (1 user, single requests)** — reflects the per-request targets:

| NFR | Endpoint | latency | Target | Verdict |
| --- | --- | --- | --- | --- |
| NFR-PERF-01 | `analyze` | 48–85 ms | p95 ≤ 500 ms | PASS |
| NFR-PERF-04 | `alerts?limit=100` | 96 ms | p95 ≤ 200 ms | PASS |
| NFR-PERF-05 | `predict/log` | 34 ms | — | — |

**Under load (15 VUs, 45 s steady)** — CPU-capped containers (`cpus: 0.5` on a
2-CPU WSL2 VM) become the bottleneck; these are dev-hardware numbers, not the
production contract:

| NFR | Endpoint | p95 (ms) | req/s | Target | Verdict |
| --- | --- | --- | --- | --- | --- |
| NFR-PERF-01 | `analyze` | 3100 | 5.2 | p95 ≤ 500 ms | dev-hw: MISS |
| NFR-PERF-04 | `alerts?limit=100` | 1500 | 2.4 | p95 ≤ 200 ms | dev-hw: MISS |
| NFR-PERF-02 | `upload-logs` (100 lines) | 2800 | 0.9 | ≥ 100 lines/s | dev-hw: MISS |
| NFR-PERF-03 | background scan polling | completes (0 fails) | — | no starvation | PASS |
| NFR-PERF-05 | `predict/log` | 810 | **67–96** | ≥ 50/s | **PASS** |

Read: single-request latency is well within target; concurrent throughput on
this laptop is limited by the container CPU shares, so NFR-PERF-01..04 need a
multi-core/CI runner (and/or larger `cpus:` limits) to assert. The ML service
already sustains 67–96 predictions/s, beating the 50/s requirement.

Re-run the suites after onboarding CI compute of a suitable spec; the targets
are the authoritative contract.