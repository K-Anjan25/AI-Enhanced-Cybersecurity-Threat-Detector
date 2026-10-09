# AEGIS Network Capture & Integration Bridges

## How It Works

AEGIS captures real network traffic automatically when you run:

```bash
docker compose up
```

The `capture` service runs inside Docker with `network_mode: host` and `NET_ADMIN` capability. It captures REAL packets from your network interface using scapy, aggregates them into flows, and sends them to the backend API.

**No manual commands needed. No fake data. No scripts to run.**

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  YOUR MACHINE                                                │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Docker Compose Stack                                  │ │
│  │                                                        │ │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐         │ │
│  │  │ capture  │    │ backend  │    │dashboard │         │ │
│  │  │ (scapy)  │───►│ :8000    │───►│ :8080    │         │ │
│  │  └────┬─────┘    └──────────┘    └──────────┘         │ │
│  │       │                                                │ │
│  └───────┼────────────────────────────────────────────────┘ │
│          │                                                    │
│          │  network_mode: host                                │
│          │  (sees ALL host traffic)                            │
│          │                                                    │
│  ┌───────┴──────────────────────────────────────────────────┐│
│  │  Host Network Interface (Wi-Fi, Ethernet, etc.)          ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## Environment Variables

| Variable                  | Default                                          | Description                                                                                                                       |
| ------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `AEGIS_PASSWORD`          | (none, required)                                 | Admin password. Set `AEGIS_BOOTSTRAP_ADMIN_PASSWORD` in `docker/.env`; the services refuse to start with the development default. |
| `AEGIS_CAPTURE_INTERFACE` | `any` (capture, tshark); `eth0` (zeek, suricata) | Linux interface to capture (`any` = all, where supported). See the per-service table below.                                       |
| `AEGIS_API_URL`           | `http://backend:8000`                            | Backend API URL                                                                                                                   |
| `AEGIS_FLUSH_INTERVAL`    | `10`                                             | Seconds between flow flushes                                                                                                      |
| `AEGIS_CAPTURE_FILTER`    | (empty)                                          | BPF filter expression                                                                                                             |

## Override Interface

The capture containers run on the Linux network namespace of the Docker host
(`network_mode: host`), so `AEGIS_CAPTURE_INTERFACE` must be a Linux interface
name as the kernel sees it (`ip link`), for example:

```bash
# Capture on a specific Linux interface
AEGIS_CAPTURE_INTERFACE=wlan0 docker compose up

# Capture on all interfaces (capture and tshark only; see the defaults below)
AEGIS_CAPTURE_INTERFACE=any docker compose up
```

Windows and macOS adapter names such as `Wi-Fi` or `Ethernet` do not exist
inside the container, so they cannot be used here.

### Docker Desktop (Windows and macOS)

Docker Desktop runs Linux containers inside a virtual machine. `network_mode:
host` attaches the containers to that VM's network, not to your Wi-Fi or
Ethernet adapter. On Docker Desktop the capture services therefore see little
or no real host traffic. To capture your own machine's traffic on Windows or
macOS, run `capture_service.py` directly on the host instead of through
Compose, or run the stack on a Linux host.

### Per-service defaults

The four capture services do not share one default interface. These are the
values in `docker/docker-compose.yml`:

| Service    | `AEGIS_CAPTURE_INTERFACE` default | Why                                                                                       |
| ---------- | --------------------------------- | ----------------------------------------------------------------------------------------- |
| `capture`  | `any`                             | libpcap accepts `any` on Linux, so all traffic is seen.                                   |
| `tshark`   | `any`                             | Same as `capture`; the entrypoint passes it to `tshark -i`.                               |
| `zeek`     | `eth0`                            | Zeek runs with `-i <name>`. `eth0` exists in the Docker Desktop VM.                       |
| `suricata` | `eth0`                            | Not changed to `any` because Suricata's AF_PACKET support for `any` is not verified here. |

To make all four the same, set `AEGIS_CAPTURE_INTERFACE` explicitly to a real
Linux interface name. Verify with `suricata -i any` on your host before using
`any` for Suricata.

## Optional: Zeek/Suricata/tcpdump Bridges

If you have Zeek, Suricata, or tcpdump installed, you can use the bridge scripts to feed their output into AEGIS. These are **optional** — the capture service handles everything automatically.

### Zeek Bridge

```bash
# Requires Zeek installed on the host
sudo zeek -i eth0 local | python3 bridges/zeek_bridge.py
```

### Suricata Bridge

```bash
# Requires Suricata installed on the host
sudo suricata -i eth0 -l /var/log/suricata/
python3 bridges/suricata_bridge.py /var/log/suricata/eve.json
```

### tcpdump/tshark Bridge

```bash
# Requires Wireshark/tshark installed on the host
tshark -i Ethernet -T fields -e frame.time_epoch -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport -e ip.proto -e frame.len | \
  python3 bridges/tcpdump_bridge.py --format tshark
```

## Detection Rules

The rule-based detector (built into the backend) automatically detects:

| Rule             | What It Detects                         | Score       |
| ---------------- | --------------------------------------- | ----------- |
| Port Scan        | 15+ destination ports from one source   | 0.50 — 0.99 |
| C2 Beacon        | Regular-interval connections            | 0.60 — 0.99 |
| Exfiltration     | 50+ MB outbound transfers               | 0.50 — 0.99 |
| Brute Force      | 10+ failed auth attempts                | 0.50 — 0.99 |
| DNS Tunnel       | Large DNS queries (>512 bytes)          | 0.40 — 0.95 |
| Lateral Movement | Internal-to-internal on sensitive ports | 0.50 — 0.95 |

Alerts appear automatically on the dashboard when suspicious traffic is detected.
