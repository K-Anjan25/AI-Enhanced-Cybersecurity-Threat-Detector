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
docker compose up -d
```

Then open **http://localhost:3000** (login/register → analyze logs → alerts).

## Streaming (Kafka) — opt-in

Kafka + Zookeeper need ~2 GiB on their own, so they are excluded by default:

```bash
docker compose --profile stream up -d
```

Backend reads `ENABLE_KAFKA` (default `false` in this stack).

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
