# Kubernetes manifests (v3)

Deployments, Services, HPA, Ingress and ConfigMap/Secret templates for the
three services. Satisfies **NFR-PORT-03** (K8s-ready) and **NFR-PORT-02**
(containerized builds).

## Layout

| File | Resource |
| --- | --- |
| `namespace.yaml` | `threat-ai` namespace |
| `configmap.yaml` | env config (runtime, auth, engine) |
| `postgres.yaml` | In-cluster PostgreSQL Deployment + PVC + Service (demo; use a managed DB in production) |
| `backend.yaml` | Backend Deployment (×2) + initContainer wait-for-postgres + Service + liveness/readiness probes |
| `ml-service.yaml` | ML Service Deployment (×2) + Service + HPA (2→6 on CPU) |
| `training.yaml` | ML training CronJob (daily retrain trigger → `POST /retrain`) |
| `dashboard.yaml` | Dashboard Deployment (×2) + Service (nginx static build, port 80) |
| `ingress.yaml` | Ingress (nginx) routing `/` → dashboard, `/api/*` → backend |

The dashboard image (`dashboard/Dockerfile`) builds the Vite SPA with
`REACT_APP_BASE_URL=/api/v1` and serves it from nginx, which reverse-proxies
`/api/*` to the backend Service (same-origin, so the httpOnly auth cookie works
without CORS).

## Apply

```bash
kubectl create namespace threat-ai   # if namespace.yaml not used
kubectl apply -f k8s/

# Secret must hold real values before deploy:
kubectl create secret generic threat-ai-secrets \
  --from-literal=database-url='postgresql://...' \
  --from-literal=jwt-secret='...' \
  --from-literal=jwt-refresh-secret='...' \
  -n threat-ai
```

## Prerequisites

- Images `threat-ai/backend:latest`, `threat-ai/ml-service:latest`,
  `threat-ai/dashboard:latest` built from the repo Dockerfiles.
- A PostgreSQL instance reachable at the `database-url` (e.g. Helm chart or
  managed DB); the backend runs additive migrations on startup.
- Ingress-nginx controller + cert-manager (TLS) in the cluster.
- Metrics server for HPA autoscaling.

## Notes

- `ENABLE_KAFKA=false` by default (ConfigMap); switch on when a Kafka broker is
  deployed and set `KAFKA_BOOTSTRAP_SERVERS`.
- The backend's `startup_event` runs additive migrations + `create_all` once; the
  `wait-for-postgres` initContainer ensures Postgres is up first, so tables are
  always created.
- `COOKIE_AUTH=true` + `COOKIE_SECURE=true` require TLS termination at the
  ingress for cookies to be accepted by browsers.
- `training.yaml` runs daily (03:00 UTC) and triggers the in-service
  `POST /retrain` endpoint; models are hot-swapped in place (no pod restart).
  Artifacts are written to the ml-service container filesystem, so for durable
  model storage mount a shared PVC at the ml-service `model/` volume and copy
  the `model/manifest.json` artifacts into it. `concurrencyPolicy: Forbid`
  prevents overlapping runs.
- **Local verification on kind** — the full stack was rolled out on a `kind`
  cluster (`kubectl apply -f k8s/` after `kind load docker-image` of the three
  images + `kubectl create secret generic threat-ai-secrets ...`). Verified:
  register/login/analyze against in-cluster Postgres with real ML predictions
  (no fallback) and alert persistence with MITRE + threat-intel enrichment.