# AEGIS Operations Guide

## Health Monitoring

### Endpoints

- `GET /healthz` — Liveness probe. Returns 200 if the process is up.
- `GET /readyz` — Readiness probe. Returns 200 when DB, Kafka, and ML service are reachable.
- `GET /metrics` — Prometheus scrape endpoint. All AEGIS golden signals.
- `GET /api/v1/detection/status` — Rule engine, drift monitor, model registrar stats.

### Key Metrics

| Metric                                 | Description               | Alert threshold |
| -------------------------------------- | ------------------------- | --------------- |
| `aegis_flows_ingested_total`           | Cumulative flows accepted | —               |
| `aegis_score_latency_seconds`          | Scoring latency histogram | p95 > 1s        |
| `aegis_alerts_created_total{severity}` | Alerts by severity        | —               |
| `aegis_consumer_lag`                   | Kafka consumer lag        | > 10,000        |
| `aegis_drift_psi{feature}`             | Feature drift PSI         | > 0.25          |
| `aegis_errors_total`                   | Error count               | rate > 1%       |

## Scaling

### Horizontal Scaling

- **Backend**: Add replicas behind load balancer. Stateless; scales linearly.
- **ML Service**: Add replicas. Shared model artifacts must be accessible.
- **Scoring Workers**: Scale on Kafka consumer lag. HPA target: lag < 1,000 per partition.

### Vertical Scaling

- Backend: 1 CPU, 1GB RAM per replica handles ~2,000 flows/s
- ML Service: 2 CPU, 2GB RAM per replica (model inference)
- PostgreSQL: Scale with connection pooling (PgBouncer recommended)

## Routine Operations

### Check System Health

```bash
# Docker Compose
docker compose ps
docker compose logs backend --tail=20

# Kubernetes
kubectl get pods -n aegis
kubectl top pods -n aegis
```

### View Recent Alerts

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/alerts?limit=10
```

### Check Model Drift

```bash
curl http://localhost:8000/metrics | grep aegis_drift_psi
```

### Restart a Service

```bash
# Docker Compose
docker compose restart backend

# Kubernetes
kubectl rollout restart deployment/aegis-backend -n aegis
```

## Log Management

Backend logs are structured JSON to stdout. In Docker, use:

```bash
docker compose logs backend | jq 'select(.event | contains("error"))'
```

In Kubernetes, use:

```bash
kubectl logs -n aegis -l app=aegis-backend -f | jq 'select(.level=="error")'
```

## Backup

See `ops/backup-restore.sh`:

```bash
./ops/backup-restore.sh backup    # Create backups
./ops/backup-restore.sh restore   # Restore from backup
./ops/backup-restore.sh verify    # Verify restored data
```

## Kafka flow path (D-085)

With `AEGIS_KAFKA_BOOTSTRAP_SERVERS` set (compose sets `kafka:9092`), flows take this path:

1. `POST /api/v1/ingest/flows` publishes each accepted record to `flows.raw` (6 partitions, keyed by `src_ip`, `acks=all`, idempotent producer). The route answers only after the broker has acknowledged the batch; a refused batch returns an error and the client retries.
2. A live consumer thread in the backend reads each partition, windows the flows per source, and scores each 50-flow window with the ML service. Partial windows are scored after 5 s with no new flows.
3. A window whose score cannot be obtained (ML service down, no checkpoint) is not committed. It is retried, not reported as clean.
4. The in-process rule engine is not fed in this mode, so every flow is scored once.

Check it on a running stack:

```
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml ps        # kafka healthy, backend healthy (topic is created by the backend)
python scripts/kafka_smoke.py                          # PASS when the broker, consumer and ML service all worked
```

Limits, stated so they are not mistaken for guarantees:

- Committed offsets are held in memory. A backend restart replays `flows.raw` from its earliest retained offset and rebuilds alerts from it. Retention (Kafka default 7 days) decides how far back that goes.
- Records are not deduplicated at the broker; the correlator's duplicate handling covers replays.
- The consumer is one thread per backend replica, and every replica consumes every partition. Run one backend replica until offsets are persisted.
