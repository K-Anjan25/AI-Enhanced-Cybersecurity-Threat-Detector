#!/usr/bin/env python3
"""
network_feeder.py — Captures real network connections and feeds them as
flow records to the AEGIS ingest API.

Reads from /proc/net/tcp and /proc/net/tcp6 for actual system connections,
then generates realistic flow records with proper byte/packet counts.
"""

import json
import time
import random
import socket
import struct
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "http://localhost:8000"
INGEST_URL = f"{API_BASE}/api/v1/ingest/flows"

# Well-known threat IPs for simulation variety
THREAT_IPS = [
    "185.220.101.34", "45.33.32.156", "198.51.100.23",
    "203.0.113.45", "91.219.236.174", "103.235.46.39",
    "176.111.174.26", "62.210.105.116", "162.247.74.27",
    "185.56.83.83", "77.247.181.162", "199.249.230.163",
]

PROTOCOLS = ["tcp", "tcp", "tcp", "udp", "tcp"]
SERVICES = ["http", "https", "ssh", "dns", "smtp", "ftp", "rdp", "smb", "unknown"]
DIRECTIONS = ["inbound", "outbound"]
STATES = ["ESTABLISHED", "SYN_SENT", "TIME_WAIT", "CLOSE_WAIT", "FIN_WAIT"]

THREAT_FAMILIES = [
    "port_scan", "brute_force", "ddos", "data_exfiltration",
    "c2_beacon", "lateral_movement", "reconnaissance",
]


def hex_to_ip(hex_str: str) -> str:
    """Convert hex IP from /proc/net/tcp to dotted notation."""
    try:
        addr_int = int(hex_str, 16)
        return socket.inet_ntoa(struct.pack("<I", addr_int))
    except (ValueError, OSError):
        return "0.0.0.0"


def hex_to_port(hex_str: str) -> int:
    """Convert hex port to int."""
    try:
        return int(hex_str, 16)
    except ValueError:
        return 0


def read_proc_connections():
    """Read real connections from /proc/net/tcp and /proc/net/tcp6."""
    connections = []
    for proc_file in ["/proc/net/tcp", "/proc/net/tcp6"]:
        try:
            with open(proc_file) as f:
                lines = f.readlines()[1:]  # skip header
            for line in lines:
                parts = line.strip().split()
                if len(parts) < 4:
                    continue
                local = parts[1].split(":")
                remote = parts[2].split(":")
                state = parts[3]

                if len(local) >= 2 and len(remote) >= 2:
                    connections.append({
                        "local_ip": hex_to_ip(local[0]) if len(local[0]) == 8 else "127.0.0.1",
                        "local_port": hex_to_port(local[1]),
                        "remote_ip": hex_to_ip(remote[0]) if len(remote[0]) == 8 else "127.0.0.1",
                        "remote_port": hex_to_port(remote[1]),
                        "state": state,
                    })
        except (FileNotFoundError, PermissionError):
            continue
    return connections


def state_from_hex(state_hex: str) -> str:
    """Convert TCP state hex to name."""
    states = {
        "01": "ESTABLISHED", "02": "SYN_SENT", "03": "SYN_RECV",
        "04": "FIN_WAIT1", "05": "FIN_WAIT2", "06": "TIME_WAIT",
        "07": "CLOSE", "08": "CLOSE_WAIT", "09": "LAST_ACK",
        "0A": "LISTEN", "0B": "CLOSING",
    }
    return states.get(state_hex, "UNKNOWN")


def generate_flow_from_connection(conn):
    """Generate a flow record from a real connection."""
    now = datetime.now(timezone.utc)
    is_inbound = conn["remote_port"] < conn["local_port"]
    direction = "inbound" if is_inbound else "outbound"

    src_ip = conn["remote_ip"] if is_inbound else conn["local_ip"]
    dst_ip = conn["local_ip"] if is_inbound else conn["remote_ip"]
    src_port = conn["remote_port"] if is_inbound else conn["local_port"]
    dst_port = conn["local_port"] if is_inbound else conn["remote_port"]

    # Simulate realistic byte/packet counts based on port
    if dst_port in (80, 443, 8080):
        src_bytes = random.randint(200, 50000)
        dst_bytes = random.randint(500, 200000)
        packets = random.randint(5, 200)
    elif dst_port == 22:
        src_bytes = random.randint(100, 5000)
        dst_bytes = random.randint(200, 10000)
        packets = random.randint(3, 50)
    elif dst_port == 53:
        src_bytes = random.randint(20, 200)
        dst_bytes = random.randint(40, 500)
        packets = random.randint(1, 5)
    else:
        src_bytes = random.randint(50, 10000)
        dst_bytes = random.randint(50, 10000)
        packets = random.randint(2, 100)

    protocol = "tcp" if dst_port != 53 else random.choice(["tcp", "udp"])

    return {
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "src_port": src_port,
        "dst_port": dst_port,
        "protocol": protocol,
        "src_bytes": src_bytes,
        "dst_bytes": dst_bytes,
        "packets": packets,
        "src_packets": max(1, packets // 3),
        "dst_packets": max(1, packets - packets // 3),
        "duration": round(random.uniform(0.01, 30.0), 3),
        "syn": random.choice([0, 1]),
        "ack": random.choice([0, 1, 1, 1]),
        "rst": 0,
        "fin": random.choice([0, 0, 0, 1]),
        "psh": random.choice([0, 0, 1]),
        "urg": 0,
        "direction": direction,
        "service": _service_name(dst_port),
        "state": _tcp_state(conn.get("state", "01")),
        "timestamp": now.isoformat(),
        "label": None,
    }


def generate_suspicious_flow():
    """Generate a flow that looks suspicious — for the ML to detect."""
    now = datetime.now(timezone.utc)
    src_ip = random.choice(THREAT_IPS)
    dst_ip = f"10.0.{random.randint(0, 255)}.{random.randint(1, 254)}"
    dst_port = random.choice([22, 23, 3389, 445, 1433, 3306, 8080, 8443])
    attack = random.choice(THREAT_FAMILIES)

    if attack == "port_scan":
        return {
            "src_ip": src_ip, "dst_ip": dst_ip,
            "src_port": random.randint(40000, 65535), "dst_port": dst_port,
            "protocol": "tcp", "src_bytes": 44, "dst_bytes": 0,
            "packets": 1, "src_packets": 1, "dst_packets": 0,
            "duration": 0.001, "syn": 1, "ack": 0, "rst": 1, "fin": 0,
            "psh": 0, "urg": 0, "direction": "inbound",
            "service": "unknown", "state": "REJECTED",
            "timestamp": now.isoformat(), "label": "port_scan",
        }
    elif attack == "brute_force":
        return {
            "src_ip": src_ip, "dst_ip": dst_ip,
            "src_port": random.randint(40000, 65535), "dst_port": 22,
            "protocol": "tcp", "src_bytes": random.randint(1000, 5000),
            "dst_bytes": random.randint(100, 500),
            "packets": random.randint(20, 100), "src_packets": 10, "dst_packets": 10,
            "duration": round(random.uniform(0.5, 5.0), 3),
            "syn": 1, "ack": 1, "rst": random.choice([0, 0, 1]), "fin": 0,
            "psh": 1, "urg": 0, "direction": "inbound",
            "service": "ssh", "state": "ESTABLISHED",
            "timestamp": now.isoformat(), "label": "brute_force",
        }
    elif attack == "data_exfiltration":
        return {
            "src_ip": dst_ip, "dst_ip": src_ip,
            "src_port": random.randint(40000, 65535), "dst_port": random.choice([443, 8443, 53]),
            "protocol": "tcp", "src_bytes": random.randint(500000, 5000000),
            "dst_bytes": random.randint(100, 1000),
            "packets": random.randint(500, 5000), "src_packets": 400, "dst_packets": 100,
            "duration": round(random.uniform(10, 120), 3),
            "syn": 1, "ack": 1, "rst": 0, "fin": 1,
            "psh": 1, "urg": 0, "direction": "outbound",
            "service": "https", "state": "ESTABLISHED",
            "timestamp": now.isoformat(), "label": "data_exfiltration",
        }
    else:  # c2_bacon, ddos, etc
        return {
            "src_ip": src_ip, "dst_ip": dst_ip,
            "src_port": random.randint(40000, 65535), "dst_port": random.choice([80, 443, 8080]),
            "protocol": "tcp", "src_bytes": random.randint(50, 500),
            "dst_bytes": random.randint(50, 500),
            "packets": random.randint(5, 20), "src_packets": 5, "dst_packets": 5,
            "duration": round(random.uniform(0.1, 2.0), 3),
            "syn": 1, "ack": 1, "rst": 0, "fin": 0,
            "psh": 0, "urg": 0, "direction": "inbound",
            "service": "https", "state": "ESTABLISHED",
            "timestamp": now.isoformat(), "label": attack,
        }


def _service_name(port: int) -> str:
    mapping = {80: "http", 443: "https", 22: "ssh", 53: "dns", 25: "smtp",
               21: "ftp", 3389: "rdp", 445: "smb", 3306: "mysql", 5432: "postgres",
               8080: "http", 8443: "https", 6379: "redis", 9200: "elasticsearch"}
    return mapping.get(port, "unknown")


def _tcp_state(hex_state: str) -> str:
    return state_from_hex(hex_state)


def send_flows(flows: list[dict]) -> bool:
    """Send flow records to the AEGIS ingest API as NDJSON."""
    if not flows:
        return False
    ndjson = "\n".join(json.dumps(f) for f in flows)
    data = ndjson.encode("utf-8")

    req = urllib.request.Request(
        INGEST_URL,
        data=data,
        headers={"Content-Type": "application/x-ndjson"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
            accepted = body.get("accepted", 0)
            rejected = body.get("rejected", 0)
            print(f"  ✓ Sent {len(flows)} flows → accepted={accepted}, rejected={rejected}")
            return accepted > 0
    except urllib.error.URLError as e:
        print(f"  ✗ API not reachable: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    print("=" * 60)
    print("AEGIS Network Traffic Feeder")
    print("=" * 60)
    print(f"Target: {INGEST_URL}")
    print()

    round_num = 0
    while True:
        round_num += 1
        print(f"\n[Round {round_num}] {datetime.now().strftime('%H:%M:%S')}")

        # Read real connections
        conns = read_proc_connections()
        active = [c for c in conns if c.get("state") != "0A"]  # exclude LISTEN
        print(f"  Real connections found: {len(active)}")

        # Generate flows from real connections
        real_flows = [generate_flow_from_connection(c) for c in active[:30]]

        # Add some suspicious traffic (30% of the batch)
        suspicious_count = max(2, len(real_flows) // 3)
        suspicious_flows = [generate_suspicious_flow() for _ in range(suspicious_count)]

        all_flows = real_flows + suspicious_flows
        random.shuffle(all_flows)

        # Send in batches of 50
        for i in range(0, len(all_flows), 50):
            batch = all_flows[i:i + 50]
            send_flows(batch)

        # Also generate some log records
        generate_and_send_logs()

        print(f"  Sleeping 10s...")
        time.sleep(10)


def generate_and_send_logs():
    """Generate log records from system activity."""
    now = datetime.now(timezone.utc)
    logs = []

    log_templates = [
        {"host": "web-server-01", "service": "nginx", "level": "info",
         "message": f"GET /api/v1/alerts 200 {random.randint(10, 200)}ms"},
        {"host": "web-server-01", "service": "nginx", "level": "warn",
         "message": f"Rate limit exceeded for {random.choice(THREAT_IPS)}"},
        {"host": "db-server-01", "service": "postgres", "level": "info",
         "message": f"connection authorized: user=aegis database=aegis"},
        {"host": "auth-server-01", "service": "sshd", "level": "warn",
         "message": f"Failed password for invalid user admin from {random.choice(THREAT_IPS)}"},
        {"host": "auth-server-01", "service": "sshd", "level": "error",
         "message": f"Maximum authentication attempts exceeded for user root from {random.choice(THREAT_IPS)}"},
        {"host": "firewall-01", "service": "iptables", "level": "warn",
         "message": f"DROP IN=eth0 SRC={random.choice(THREAT_IPS)} DST=10.0.0.1 PROTO=TCP DPT={random.choice([22, 3389, 445])}"},
        {"host": "app-server-01", "service": "aegis-backend", "level": "info",
         "message": f"ingest batch accepted={random.randint(10, 100)} rejected=0"},
        {"host": "dns-server-01", "service": "bind", "level": "info",
         "message": f"query: {random.choice(['evil-domain.com', 'c2-server.net', 'malware-drop.cc'])} IN A"},
    ]

    for template in log_templates:
        logs.append({
            "host": template["host"],
            "service": template["service"],
            "level": template["level"],
            "message": template["message"],
            "timestamp": now.isoformat(),
            "parameters": [],
            "template_id": None,
            "label": None,
        })

    ndjson = "\n".join(json.dumps(l) for l in logs)
    data = ndjson.encode("utf-8")
    url = f"{API_BASE}/api/v1/ingest/logs"
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/x-ndjson"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
            print(f"  ✓ Logs sent: accepted={body.get('accepted', 0)}")
    except Exception:
        pass


if __name__ == "__main__":
    main()