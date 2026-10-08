# AEGIS Network Integration Bridges

Production-ready bridges that connect real network monitoring tools to the AEGIS threat detection API.

## Quick Start

```bash
# Set your AEGIS backend URL and credentials
export AEGIS_API_URL="http://your-aegis-server:8000"
export AEGIS_EMAIL="admin@aegis.local"
export AEGIS_PASSWORD="your-password"
```

## 1. Zeek (Bro) Integration

Zeek produces structured `conn.log` files with detailed flow metadata.

```bash
# Real-time: pipe Zeek output directly
zeek -i eth0 local | python3 zeek_bridge.py

# Tail existing log
tail -f /var/log/zeek/conn.log | python3 zeek_bridge.py

# Import historical data
python3 zeek_bridge.py --file /var/log/zeek/conn.log
```

**What it captures:** Full flow metadata — bytes, packets, duration, TCP flags, connection state, service detection.

## 2. Suricata Integration

Suricata produces EVE JSON with flows, alerts, and DNS events.

```bash
# Real-time: tail eve.json
tail -f /var/log/suricata/eve.json | python3 suricata_bridge.py

# With Suricata running:
suricata -i eth0 --set outputs.1.eve-log.filename=eve.json -l /var/log/suricata/
tail -f /var/log/suricata/eve.json | python3 suricata_bridge.py

# Import historical
python3 suricata_bridge.py --file /var/log/suricata/eve.json
```

**What it captures:**
- **Flow events** → `/api/v1/ingest/flows` (network flows)
- **Alert events** → `/api/v1/ingest/logs` (IDS alerts with signatures)
- **DNS events** → `/api/v1/ingest/logs` (DNS queries)

## 3. tcpdump / tshark Integration

Raw packet capture converted to flow records.

```bash
# With tcpdump (requires root):
sudo tcpdump -i eth0 -l -n -tt | python3 tcpdump_bridge.py

# With tshark (Wireshark CLI):
tshark -i eth0 -T fields -e frame.time_epoch -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport -e ip.proto -e frame.len \
  -e tcp.flags.syn -e tcp.flags.ack -e tcp.flags.reset \
  -e tcp.flags.fin -e tcp.flags.push | python3 tcpdump_bridge.py --format tshark

# Capture for specific duration:
timeout 300 tcpdump -i eth0 -l -n -tt | python3 tcpdump_bridge.py
```

**What it captures:** Raw packet headers aggregated into flow records by 5-tuple.

## 4. Network Tap / SPAN Port

For passive monitoring of all network traffic:

```bash
# On a mirrored port or network tap device:
sudo tcpdump -i eth1 -l -n -tt -s 96 | python3 tcpdump_bridge.py

# With VLAN filtering:
sudo tcpdump -i eth1 -l -n -tt -s 96 vlan | python3 tcpdump_bridge.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AEGIS_API_URL` | `http://localhost:8000` | Backend API URL |
| `AEGIS_API_TOKEN` | (auto) | Bearer token (auto-obtained if not set) |
| `AEGIS_EMAIL` | `admin@aegis.local` | Login email |
| `AEGIS_PASSWORD` | `admin123456789` | Login password |

## Running as a Service (systemd)

```ini
# /etc/systemd/system/aegis-zeek-bridge.service
[Unit]
Description=AEGIS Zeek Bridge
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/tail -f /var/log/zeek/conn.log | /usr/bin/python3 /opt/aegis/zeek_bridge.py
Environment=AEGIS_API_URL=http://aegis-server:8000
Environment=AEGIS_EMAIL=admin@aegis.local
Environment=AEGIS_PASSWORD=your-secure-password
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable aegis-zeek-bridge
sudo systemctl start aegis-zeek-bridge
```

## Docker Deployment

```bash
# Run Zeek + bridge in Docker
docker run --net=host --rm -v /var/log/zeek:/var/log/zeek \
  -e AEGIS_API_URL=http://host.docker.internal:8000 \
  aegis/zeek-bridge:latest

# Run Suricata + bridge in Docker
docker run --net=host --rm -v /var/log/suricata:/var/log/suricata \
  -e AEGIS_API_URL=http://host.docker.internal:8000 \
  aegis/suricata-bridge:latest
```