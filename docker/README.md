# Docker Compose — Threat AI stack

Runs the complete application with a single command, sized for low-memory hosts.

## Services (default: `docker compose up -d`)

| Service | Container | Exposed | Memory limit |
| --- | --- | --- | --- |
| `dashboard` | nginx + React SPA | `http://localhost:3000` | 96 MiB |
| `backend` | FastAPI API (migrations auto-run) | `http://localhost:8000` | 320 MiB |
| `ml-service` | ML detection microservice | `http://localhost:8001` | 320 MiB |
| `postgres` | PostgreSQL 15 | `localhost:5431` | 192 MiB |

Sum of limits: **~928 MiB** (fits a 1 GiB container budget).

## Start

```bash
cd docker
docker compose up -d --build   # --build bakes fresh models on ml-service rebuild
```

Then open **http://localhost:3000** (login/register → analyze logs → alerts).

## ML models: baked at build time (no manual retrain)

The ml-service `Dockerfile` trains the log/email classifiers during the image
build (`RUN python train.py`), so `/benchmark` and `/explain` show real model
results out of the box and predictions use the trained classifiers — no manual
`POST /retrain` required.

The **network (IsolationForest) model needs the CICIDS2017 dataset**
(`datasets/CICIDS2017/*.csv`), which is not part of the build context. It is
gracefully skipped at build time, and the service falls back to deterministic
heuristics for network flows until you either:

- trigger the in-service retrain: `curl -X POST http://localhost:8001/retrain -H 'Content-Type: application/json' -d '{"require_network": true}'` (with data mounted), or
- build the image with the dataset in scope so it trains during the build.

## Streaming (Kafka) — opt-in

Kafka + Zookeeper need ~2 GiB on their own, so they are excluded by default.
To run the streaming event chain (`raw-logs`, `alerts.raised`,
`actions.executed` topics), start the profile **and** enable the backend
producer:

```bash
docker compose --profile stream up -d
# enable Kubernetes-less streaming end to end:
echo "ENABLE_KAFKA=true" > .env
docker compose up -d --no-deps backend
```

`ENABLE_KAFKA` defaults to `false` in `docker-compose.yml` (so the
no-stream stack works without a broker); the backend reads
`KAFKA_BOOTSTRAP_SERVERS=kafka:9092`.

**Dual listener:** the broker advertises two listeners so both containers and
the host can connect —

- in-network (`kafka:9092`) — used by the backend producer,
- host (`localhost:29092`) — for host-side tools/consumers, e.g.:

  ```bash
  docker exec threatai-kafka kafka-console-consumer --bootstrap-server \
    localhost:29092 --topic alerts.raised --from-beginning
  ```

  A single advertised listener (e.g. `localhost:9092`) is unreachable from
  inside the compose network — the backend would throw
  `KafkaTimeoutError: Failed to update metadata` on every send.

Verify the chain end-to-end: log in, `POST /api/v1/analyze`, then consume the
three topics above — each should show a JSON event keyed by `org_id`, with the
alert carrying MITRE + threat-intel enrichment.

## Authentication mode

The dashboard authenticates via the backend's httpOnly `access_token` /
`refresh_token` cookies (tokens never reach JavaScript), so the stack sets
`COOKIE_AUTH=true` and `COOKIE_SECURE=false` (plain `http://localhost:3000`).
If you expose the stack over HTTPS use `COOKIE_SECURE=true`.

## Troubleshooting memory hangs on 8 GB laptops

Docker Desktop runs its engine inside a WSL2 VM. On 8 GB hosts cap the VM via
`%UserProfile%\.wslconfig` so it can never starve Windows:

```ini
[wsl2]
memory=2GB
processors=2
swap=2GB
localhostForwarding=true

[experimental]
autoMemoryReclaim=gradual
```

Then run `wsl --shutdown` once and restart Docker Desktop. Do **not** run the
kind Kubernetes cluster at the same time as this stack on such a machine.
