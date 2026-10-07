# Kubernetes manifests

Application workloads only: `backend`, `ml-service`, `dashboard`. Everything
here is static YAML, applied with `kubectl apply -k .` or `kubectl apply -f .`.

## What is deliberately not here

- **Datastores.** Postgres, Kafka and Elasticsearch are provisioned outside
  these manifests — managed services or a dedicated operator. `AEGIS_DATABASE_HOST`
  in `10-configmap.yaml` points at whatever provides them.
- **Scoring workers.** `architecture.md` §11.2 lists them, but no worker code
  exists yet; the workload lands with T-2xx rather than as a manifest that
  cannot run.
- **Latency-, lag- and queue-depth-based autoscaling.** The HPAs scale on CPU.
  The others need a custom-metrics adapter.
- **Real image tags.** The manifests pin `0.1.0`; CI substitutes the built
  digest. `:latest` is rejected by the checker because a rollback to it is
  meaningless.
- **Secrets.** `aegis-secrets` and `aegis-tls` are created out of band from the
  cluster secret store. `aegis-secrets` must include `AEGIS_SECRET_KEY`, the
  database credentials, and the initial `AEGIS_BOOTSTRAP_ADMIN_EMAIL` plus
  `AEGIS_BOOTSTRAP_ADMIN_PASSWORD` required for production sign-in. No key material
  or operator password is committed (R-50).

## Verification status

`scripts/check_k8s.py` validates what can be validated without a cluster: the
YAML parses, every probe path is a route the application really serves, every
`AEGIS_*` variable is a real `Settings` field, no secret value is inlined, every
container is non-root with a read-only root filesystem, and every HPA targets a
Deployment that exists.

**These manifests have never been applied to a cluster.** There is no cluster
and no `kubectl` in the development sandbox, so scheduling, image pulls, probe
behaviour and the ingress controller are all unverified.
