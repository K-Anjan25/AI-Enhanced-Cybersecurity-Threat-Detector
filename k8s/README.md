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
| `training.yaml` | ML training CronJob (daily retrain trigger → `POST /retrain`; network model opt-in) |
| `dashboard.yaml` | Dashboard Deployment (×2) + Service (nginx static build, port 80) |
| `ingress.yaml` | TLS Ingress (nginx) routing `/` → dashboard, `/api/*` → backend; cert-manager issues `threat-ai-tls` |
| `tls/issuers.yaml` | cert-manager ClusterIssuers: self-signed (offline/kind demo) + Let's Encrypt staging/prod |

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

## Production: use a managed Postgres

`postgres.yaml` is the **demo** database (in-cluster, single replica, PVC
storage). For production, point the backend at a managed service instead —
the backend runs additive migrations on startup, so no manifest change is
needed beyond the Secret:

```bash
# e.g. AWS RDS / GCP Cloud SQL / Neon / Supabase
kubectl create secret generic threat-ai-secrets \
  --from-literal=database-url='postgresql://threat:CHANGE_ME@db.example.com:5432/threatdb?sslmode=require' \
  --from-literal=jwt-secret='...' \
  --from-literal=jwt-refresh-secret='...' \
  -n threat-ai

kubectl delete -f k8s/postgres.yaml   # drop the demo DB once managed one is wired
```

This avoids single-replica storage by replacing it with a HA/managed Postgres
(automated backups, failover) and let the backend HPA scale freely.

## Prerequisites

- Images `threat-ai/backend:latest`, `threat-ai/ml-service:latest`,
  `threat-ai/dashboard:latest` built from the repo Dockerfiles. The
  `ml-service` image is **self-contained**: its Dockerfile runs
  `python train.py` at build time, baking the log/email classifiers in, so the
  deployment serves real predictions and `/benchmark` + `/explain` work out of
  the box with no manual `/retrain`. The network model needs the CICIDS2017
  dataset and is skipped unless it is present at build/retrain time.
- A PostgreSQL instance reachable at the `database-url` (e.g. Helm chart or
  managed DB); the backend runs additive migrations on startup.
- Ingress-nginx controller + cert-manager (TLS) in the cluster.
- Metrics server for HPA autoscaling.

## TLS at the gateway (NFR-SEC-10)

The `ingress.yaml` terminates TLS: HTTP is force-redirected to HTTPS
(`ssl-redirect`/`force-ssl-redirect` + HSTS) and cert-manager provisions the
`threat-ai-tls` secret. Install the controllers once per cluster:

```bash
# 1. ingress-nginx controller (pin a release; see https://github.com/kubernetes/ingress-nginx/releases)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/v1.11.3/deploy/static/provider/kind/deploy.yaml

# 2. cert-manager (CRDs + controllers; pin a release; see https://cert-manager.io/docs/installation/)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
```

Then create the issuer set and point the DNS name at the ingress IP/load balancer:

```bash
kubectl apply -f k8s/tls/issuers.yaml
# set your domain in k8s/ingress.yaml (dashboard.example.com) and your ACME
# email in k8s/tls/issuers.yaml, then:
kubectl apply -f k8s/ingress.yaml
kubectl get certificate -n threat-ai threat-ai-tls   # becomes READY when issued
```

- **Internet + DNS:** use `letsencrypt-prod` (already the Ingress default).
- **Offline / kind demo:** swap the Ingress annotation to the bundled local CA:

  ```bash
  kubectl annotate ingress threat-ai-ingress -n threat-ai \
    cert-manager.io/cluster-issuer=threat-ai-selfsigned-ca --overwrite
  ```

  The self-signed CA issues an ECDSA cert for `dashboard.example.com` with no
  external calls; browsers will show an untrusted-CA warning, which is expected.
- With TLS in place the backend's `COOKIE_AUTH=true` + `COOKIE_SECURE=true`
  cookies are accepted by browsers (the same-origin `/api` proxy and the
  `https://dashboard.example.com` origin in the ConfigMap `CORS_ORIGINS`).

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
  Because `retrain` defaults to `require_network=false` and the build-time
  trained log/email models are already baked in, the CronJob mostly refreshes
  log/email classifiers with current request data. Network model training
  requires the CICIDS2017 dataset: build the image with the dataset in scope,
  or mount it into the running pods and call `/retrain` with
  `{"require_network": true}`. Hot-swaps are volatile (written to the container
  filesystem) and reset to the baked models on pod restart; for durable
  retrained artifacts mount a shared PVC at the `model/` volume. `concurrencyPolicy:
  Forbid` prevents overlapping runs.
- **Local verification on kind** — the full stack was rolled out on a `kind`
  cluster (`kubectl apply -f k8s/` after `kind load docker-image` of the three
  images + `kubectl create secret generic threat-ai-secrets ...`). Verified:
  register/login/analyze against in-cluster Postgres with real ML predictions
  (no fallback) and alert persistence with MITRE + threat-intel enrichment.