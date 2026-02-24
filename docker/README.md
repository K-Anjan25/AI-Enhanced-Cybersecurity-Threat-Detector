# Docker Infrastructure

This setup provides local infrastructure for the AI-Enhanced Cybersecurity Threat Detector.

## Services

- **Zookeeper** – Kafka coordination
- **Kafka** – Streaming logs & alerts
- **PostgreSQL** – Persistent storage for logs & alerts

## How to start

From the project root:

```bash
cd docker
docker compose up -d
```
