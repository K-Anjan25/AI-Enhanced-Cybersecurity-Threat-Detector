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
