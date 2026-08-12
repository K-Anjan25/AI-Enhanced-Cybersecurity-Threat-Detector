# Kubernetes manifests (v3)

Deployments, Services, HPA, Ingress and ConfigMap/Secret templates for the
three services. Satisfies **NFR-PORT-03** (K8s-ready) and **NFR-PORT-02**
(containerized builds).

## Layout

| File | Resource |
| --- | --- |
| `namespace.yaml` | `threat-ai` namespace |
| `configmap.yaml` | env config (runtime, auth, engine) |
| `backend.yaml` | Backend Deployment (×2) + Service + liveness/readiness probes |
| `ml-service.yaml` | ML Service Deployment (×2) + Service + HPA (2→6 on CPU) |
| `dashboard.yaml` | Dashboard Deployment (×2) + Service |
| `ingress.yaml` | Ingress (nginx) routing `/` → dashboard, `/api/*` → backend + Secret template |

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
- `COOKIE_AUTH=true` + `COOKIE_SECURE=true` require TLS termination at the
  ingress for cookies to be accepted by browsers.