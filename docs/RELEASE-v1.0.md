# AEGIS v1.0 Release Notes

## Release Information

| Field | Value |
|-------|-------|
| **Version** | 1.0.0 |
| **Date** | 2026-10-09 |
| **Tag** | v1.0.0 |
| **Git SHA** | (filled by CI) |

## Features

### Detection Pipeline
- Real-time network flow ingestion via REST API (5,000+ flows/s sustained)
- Log ingestion for syslog, auth, firewall, IDS, DNS sources
- Rule-based threat detection (port scans, brute force, data exfiltration, DNS tunneling)
- ML-based anomaly detection with IsolationForest model
- Alert correlation and severity scoring

### Model Operations
- Model registry with version tracking (T-315)
- Model promotion and rollback (FR-33)
- Feature drift detection via Population Stability Index (T-421)
- Per-feature PSI gauges published to /metrics

### Capture Services
- **tcpdump**: Raw packet capture → flow records
- **Zeek**: Network analysis → connection logs
- **Suricata**: IDS → EVE JSON alerts
- **tshark**: Protocol analysis → flow summaries

### Dashboard
- Cyberpunk-themed UI with 3D globe for traffic visualization
- Real-time alert feed with WebSocket push
- Traffic page with source/destination flow visualization
- Models page with version table and metrics
- Drift page with per-feature PSI bars
- Threat intelligence hunt console

### Infrastructure
- Docker Compose for development
- Kubernetes manifests for production
- Helm chart with HPA for scoring workers
- Grafana dashboards and alert rules
- CI/CD pipeline with tagged image releases

## Model Metrics (R-74)

| Metric | Value | Source |
|--------|-------|--------|
| Precision | 0.92 | runs/flownet/eval@2.json |
| Recall | 0.87 | runs/flownet/eval@2.json |
| F1 | 0.89 | runs/flownet/eval@2.json |
| ROC AUC | 0.95 | runs/flownet/eval@2.json |
| PR AUC | 0.91 | runs/flownet/eval@2.json |

## Performance (NFR-01)

| Stage | Measured p95 | Budget |
|-------|-------------|--------|
| Ingest validate + Kafka produce | TBD | 40ms |
| Kafka → worker consume | TBD | 100ms |
| Window assembly | TBD | 20ms |
| Feature extraction | TBD | 15ms |
| Transformer inference | TBD | 90ms |
| Fusion + correlate + persist | TBD | 30ms |
| WebSocket delivery | TBD | 20ms |
| **Total** | **TBD** | **315ms** |

## Rollback Procedure

```bash
# Helm rollback
helm rollback aegis -n aegis

# Docker Compose rollback
git checkout <previous-tag>
docker compose down
docker compose up -d --build
```

Rollback has been rehearsed and timed (T-510 acceptance criteria).

## Breaking Changes

None (initial release).

## Known Issues

- Capture services require `NET_RAW` capability (Docker) or `NET_RAW` + `NET_ADMIN` (Kubernetes)
- Audit trail hash-chaining deferred to post-v1 (T-511)
- Mutual TLS between backend and ML service deferred to post-v1 (T-512)

## Upgrade Path

From Docker Compose to Kubernetes:
1. Backup PostgreSQL using `ops/backup-restore.sh backup`
2. Deploy Kubernetes using Helm chart
3. Restore PostgreSQL using `ops/backup-restore.sh restore`
4. Verify with `ops/backup-restore.sh verify`
