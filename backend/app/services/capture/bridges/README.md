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

| Variable | Default | Description |
|----------|---------|-------------|
| `AEGIS_CAPTURE_INTERFACE` | `any` | Network interface to capture (`any` = all) |
| `AEGIS_API_URL` | `http://backend:8000` | Backend API URL |
| `AEGIS_FLUSH_INTERVAL` | `10` | Seconds between flow flushes |
| `AEGIS_CAPTURE_FILTER` | (empty) | BPF filter expression |

## Override Interface

```bash
# Capture only on Wi-Fi
AEGIS_CAPTURE_INTERFACE=Wi-Fi docker compose up

# Capture only on Ethernet
AEGIS_CAPTURE_INTERFACE=Ethernet docker compose up

# Capture on Linux interface
AEGIS_CAPTURE_INTERFACE=wlan0 docker compose up
```

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

| Rule | What It Detects | Score |
|------|----------------|-------|
| Port Scan | 15+ destination ports from one source | 0.50 — 0.99 |
| C2 Beacon | Regular-interval connections | 0.60 — 0.99 |
| Exfiltration | 50+ MB outbound transfers | 0.50 — 0.99 |
| Brute Force | 10+ failed auth attempts | 0.50 — 0.99 |
| DNS Tunnel | Large DNS queries (>512 bytes) | 0.40 — 0.95 |
| Lateral Movement | Internal-to-internal on sensitive ports | 0.50 — 0.95 |

Alerts appear automatically on the dashboard when suspicious traffic is detected.