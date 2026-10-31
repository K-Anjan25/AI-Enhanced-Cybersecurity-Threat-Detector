# Replay a capture file through Suricata (Phase 1)

Replay runs a saved `.pcap` through Suricata and sends the results to AEGIS. It needs no
network access and no special hardware, so it is the first test of the pipeline.

What it does:

1. `suricata -r <file>.pcap` reads the file offline and writes `eve.json`.
2. `suricata_bridge.py --flows --file eve.json` sends `flow` events as flows and alert, DNS,
   HTTP and TLS events as logs, to `/api/v1/ingest/flows` and `/api/v1/ingest/logs`.

The sample capture is **synthetic**. `scripts/make_sample_pcap.py` writes DNS lookups, normal
TLS-style sessions and a port scan. It tests the pipeline, not detection quality.

## Windows (PowerShell), from the repository root

```powershell
# 1. Make the sample capture (needs Python and scapy on Windows)
pip install scapy
python scripts\make_sample_pcap.py samples\synthetic_home.pcap

# 2. Start the stack and make sure migrations ran
cd docker
docker compose up -d --build
docker compose logs migrate

# 3. Replay the capture inside the capture image, on the compose network
docker run --rm --network aegis_default `
  -v "${PWD}\..\samples:/pcaps:ro" `
  -e AEGIS_API_URL=http://backend:8000 `
  -e AEGIS_EMAIL=admin@aegis.local `
  -e AEGIS_PASSWORD="<AEGIS_BOOTSTRAP_ADMIN_PASSWORD from docker\.env>" `
  --entrypoint /app/replay_pcap.sh aegis-capture:latest /pcaps/synthetic_home.pcap
```

Expected output: a `replay: N eve events` line, then `[SURICATA] Done.` with flow and alert
counts. Replace the password placeholder with the value from `docker\.env`. Do not paste it
into chat.

## What was checked, and where

- The bridge-to-API path was tested against a local backend with a Suricata-format `eve.json`
  (flow, alert and DNS events). Flows came back with the expected totals: 4 flows,
  50,820 bytes, 68 packets. The alert and DNS events were accepted (HTTP 200).
- The logs and alerts read-back needs PostgreSQL (`AEGIS_DATABASE_URL`). The Docker stack
  sets it, so verify there. A process without a database only keeps a short in-memory tail.
- **Not run yet:** `suricata -r` itself. Suricata is not installed in the development sandbox.
  The first real replay happens in the capture image.

## Notes

- Replay times come from the capture file, so old captures land in old time windows.
  Query them by event time, not by "now".
- `samples/` is not committed. Regenerate it with the script.
