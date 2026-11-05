# Docker-managed network capture

The Compose `capture` service is part of the main stack. It supervises Zeek,
Suricata, tshark, their AEGIS bridges, and a backend heartbeat reporter. There is
no host-side Python setup and no synthetic traffic generator.

## Real data sources

| Engine   | Default AEGIS data                                                                                 | Duplicate prevention                                                                       |
| -------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Zeek     | `conn.log` records become the canonical `flow@1` connections.                                      | The only engine that writes flow records by default.                                       |
| Suricata | EVE alert, DNS, HTTP, and TLS events become `log@1` records.                                       | Suricata flow events are skipped while Zeek is enabled.                                    |
| tshark   | Selected SMB2, RDP, MQTT, Modbus, SSH, Kerberos, and NTLM packet metadata becomes `log@1` records. | Packet metadata is logged without payload/credential text and never becomes a flow record. |

The tshark protocol filter is intentionally limited to details not already covered
by the Zeek flow feed and Suricata's alert/DNS/HTTP/TLS bridge. A quiet interface
produces no fabricated flows or alerts. Sensor heartbeats are liveness metadata,
not network-traffic records.

## Run the stack

From the repository root, copy `docker/.env.example` to `docker/.env`, set a
random `AEGIS_SECRET_KEY` and a strong `AEGIS_BOOTSTRAP_ADMIN_PASSWORD`, then run:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Compose starts all three capture engines by default. The single capture image
keeps the engine processes together so a failed engine or bridge causes the
container to restart rather than leaving a partial sensor silently running.

## Capture health

The reporter sends an authenticated heartbeat every 15 seconds to
`POST /api/v1/capture/heartbeat`. The dashboard/API reads the latest real reports
from `GET /api/v1/capture/status`; a sensor becomes stale after 45 seconds with
no report. An empty sensor list is `unknown`, not `healthy`, and reports expire
in memory rather than being retained as traffic data.

The sensor identifier and heartbeat interval can be set with
`AEGIS_CAPTURE_SENSOR_ID` and `AEGIS_CAPTURE_HEARTBEAT_SECONDS` in `docker/.env`.
The interval accepts 1–30 seconds to stay below the backend's 45-second stale threshold.
The capture status endpoint is read-only for dashboard users; reporting requires
an ingest-capable backend account.

## Host and interface requirements

The Compose service uses host networking and the `NET_ADMIN`/`NET_RAW`
capabilities. On Linux it captures the named host interface. Zeek and Suricata
default to `eth0`; tshark defaults to `any`. To select an interface for all three,
set `AEGIS_CAPTURE_INTERFACE` in `docker/.env`; per-engine overrides are
`AEGIS_ZEEK_INTERFACE`, `AEGIS_SURICATA_INTERFACE`, and `AEGIS_TSHARK_INTERFACE`.

Docker Desktop runs Linux containers in a VM. Host networking there may expose
only VM traffic, not the Windows/macOS Wi-Fi or Ethernet adapter. This is a
platform limitation, not a reason to substitute generated traffic. For full
host-interface capture, run Compose on a Linux host with permission to capture
on the selected interface.
