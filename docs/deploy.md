# AEGIS Deployment Guide

## Quick Start (Docker Compose)

```bash
cd docker

# Set required secrets
export AEGIS_SECRET_KEY=$(openssl rand -hex 32)
export AEGIS_DEV_AUTH_SETUP_ENABLED=true

# Start everything
docker compose up -d --build

# Verify
docker compose ps
curl http://localhost:8000/healthz
curl http://localhost:8080
```

Dashboard: http://localhost:8080
Backend API: http://localhost:8000/docs
ML Service: http://localhost:8001/docs

Default admin: `admin@aegis.local` / `admin123456789`. The capture services (`capture`, `zeek`, `suricata`, `tshark`) refuse to start while the password is this default. Set `AEGIS_BOOTSTRAP_ADMIN_PASSWORD` in `docker/.env` first; see `docker/.env.example`.

## Production (Kubernetes)

### Prerequisites

- Kubernetes 1.27+
- Helm 3.12+
- PostgreSQL 15+ (managed or self-hosted)
- Kafka 3.5+ (managed or self-hosted)
- Container registry access

### Install

```bash
# Create namespace
kubectl create namespace aegis

# Create secrets (from cluster secret store)
kubectl create secret generic aegis-secrets -n aegis \
  --from-literal=AEGIS_SECRET_KEY=<32+ random chars> \
  --from-literal=AEGIS_DATABASE_URL='postgresql+psycopg://aegis:<password>@<host>:5432/aegis' \
  --from-literal=AEGIS_BOOTSTRAP_ADMIN_EMAIL=admin@aegis.local \
  --from-literal=AEGIS_BOOTSTRAP_ADMIN_PASSWORD=<secure-password>

# Deploy with Helm
helm install aegis ./helm/aegis \
  -n aegis \
  -f helm/aegis/values-production.yaml

# Verify
kubectl get pods -n aegis
kubectl logs -n aegis -l app=aegis-backend --tail=50
```

### Upgrading

```bash
helm upgrade aegis ./helm/aegis -n aegis \
  --set backend.image.tag=<new-version> \
  --set mlService.image.tag=<new-version> \
  --set dashboard.image.tag=<new-version>
```

### Rollback

```bash
helm rollback aegis -n aegis
```

## Configuration

All configuration via environment variables prefixed with `AEGIS_`:

| Variable                         | Required | Description                             |
| -------------------------------- | -------- | --------------------------------------- |
| `AEGIS_SECRET_KEY`               | Yes      | 32+ char random secret for JWT signing  |
| `AEGIS_DATABASE_URL`             | Yes      | PostgreSQL connection string            |
| `AEGIS_ENV`                      | No       | `development`, `staging`, `production`  |
| `AEGIS_LOG_LEVEL`                | No       | `DEBUG`, `INFO`, `WARNING`, `ERROR`     |
| `AEGIS_ML_SERVICE_URL`           | No       | ML service URL (default: auto-detected) |
| `AEGIS_DEV_AUTH_SETUP_ENABLED`   | No       | Enable initial admin creation           |
| `AEGIS_BOOTSTRAP_ADMIN_EMAIL`    | No       | Initial admin email                     |
| `AEGIS_BOOTSTRAP_ADMIN_PASSWORD` | No       | Initial admin password                  |
