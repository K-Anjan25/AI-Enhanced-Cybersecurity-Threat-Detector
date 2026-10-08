#!/usr/bin/env python3
"""
Live network traffic simulator + real packet capture for AEGIS.

Generates diverse, realistic network traffic:
- Normal web browsing (HTTP/HTTPS to various sites)
- DNS queries
- SSH connections
- Database traffic
- Email traffic
- Suspicious traffic (port scans, brute force, exfiltration, C2 beacons)

All traffic is sent as flow records to the AEGIS ingest API.
"""
import json
import time
import random
import socket
import struct
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "http://localhost:8000"
INGEST_FLOWS = f"{API_BASE}/api/v1/ingest/flows"
INGEST_LOGS = f"{API_BASE}/api/v1/ingest/logs"
TOKEN = None

# Real-world IP ranges for realistic traffic
NORMAL_IPS = [
    "142.250.185.78",    # Google
    "151.101.1.69",      # Reddit/CDN
    "104.16.132.229",    # Cloudflare
    "13.107.42.14",      # Microsoft
    "52.96.108.10",      # Office365
    "17.253.144.10",     # Apple
    "157.240.1.35",      # Facebook
    "104.244.42.65",     # Twitter
    "34.117.59.81",      # YouTube
    "198.41.128.100",    # CDN
    "93.184.216.34",     # Example.com
    "8.8.8.8",           # Google DNS
    "1.1.1.1",           # Cloudflare DNS
    "208.67.222.222",    # OpenDNS
]

INTERNAL_IPS = [
    "10.0.0.10", "10.0.0.11", "10.0.0.12", "10.0.0.20",
    "10.0.0.50", "10.0.0.100", "10.0.1.5", "10.0.1.10",
    "192.168.1.1", "192.168.1.10", "192.168.1.50",
    "192.168.0.1", "172.16.0.5", "172.16.0.10",
]

ATTACKER_IPS = [
    "185.220.101.34", "45.33.32.156", "198.51.100.23",
    "203.0.113.45", "91.219.236.174", "103.235.46.39",
    "176.111.174.26", "62.210.105.116", "162.247.74.27",
    "185.56.83.83", "77.247.181.162", "199.249.230.163",
    "5.188.86.24", "45.155.205.233", "89.248.167.131",
]

SERVER_IPS = [
    "10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.5",
    "10.0.0.8", "10.0.0.15", "10.0.0.25",
]


def authenticate():
    global TOKEN
    for attempt in range(3):
        for url, body in [
            (f"{API_BASE}/api/v1/auth/login", {"email": "admin@aegis.local", "password": "admin123456789"}),
            (f"{API_BASE}/api/v1/auth/setup", {"email": "admin@aegis.local", "password": "admin123456789"}),
        ]:
            try:
                data = json.dumps(body).encode()
                req = urllib.request.Request(url, data=data,
                                             headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read())
                    TOKEN = result["access_token"]
                    print(f"[AUTH] ✓ {result['subject']} (role={result['role']})")
                    return True
            except Exception:
                continue
        time.sleep(2)
    print("[AUTH] ✗ Failed after 3 attempts")
    return False


def send_ndjson(records, url):
    if not records or not TOKEN:
        return 0
    ndjson = "\n".join(json.dumps(r) for r in records)
    req = urllib.request.Request(
        url, data=ndjson.encode(),
        headers={"Content-Type": "application/x-ndjson", "Authorization": f"Bearer {TOKEN}"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
            return body.get("accepted", 0)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            authenticate()
        return 0
    except Exception:
        return 0


def ts():
    return datetime.now(timezone.utc).isoformat()


def generate_normal_traffic(count=15):
    """Normal web browsing, DNS, email, database traffic."""
    records = []
    now = ts()
    for _ in range(count):
        src = random.choice(INTERNAL_IPS)
        dst = random.choice(NORMAL_IPS)
        dst_port = random.choice([80, 443, 443, 443, 8080])
        src_port = random.randint(32768, 65535)
        proto = "tcp"

        if dst_port in (80, 8080):
            service = "http"
            src_bytes = random.randint(200, 3000)
            dst_bytes = random.randint(1000, 50000)
            pkts = random.randint(5, 30)
        elif dst_port == 443:
            service = "https"
            src_bytes = random.randint(300, 5000)
            dst_bytes = random.randint(2000, 100000)
            pkts = random.randint(8, 80)
        else:
            service = "unknown"
            src_bytes = random.randint(100, 2000)
            dst_bytes = random.randint(100, 2000)
            pkts = random.randint(2, 20)

        records.append({
            "src_ip": src, "dst_ip": dst,
            "src_port": src_port, "dst_port": dst_port,
            "protocol": proto, "src_bytes": src_bytes, "dst_bytes": dst_bytes,
            "packets": pkts, "src_packets": max(1, pkts // 3),
            "dst_packets": max(1, pkts - pkts // 3),
            "duration": round(random.uniform(0.05, 15.0), 3),
            "syn": 1, "ack": 1, "rst": 0, "fin": random.choice([0, 0, 1]),
            "psh": random.choice([0, 1]), "urg": 0,
            "direction": "outbound", "service": service,
            "state": "ESTABLISHED", "timestamp": now, "label": None,
        })

    # DNS queries
    for _ in range(5):
        src = random.choice(INTERNAL_IPS)
        records.append({
            "src_ip": src, "dst_ip": "8.8.8.8",
            "src_port": random.randint(32768, 65535), "dst_port": 53,
            "protocol": "udp", "src_bytes": random.randint(20, 100),
            "dst_bytes": random.randint(40, 300),
            "packets": 2, "src_packets": 1, "dst_packets": 1,
            "duration": round(random.uniform(0.001, 0.1), 3),
            "syn": 0, "ack": 0, "rst": 0, "fin": 0, "psh": 0, "urg": 0,
            "direction": "outbound", "service": "dns",
            "state": "ESTABLISHED", "timestamp": now, "label": None,
        })

    # SSH between internal hosts
    for _ in range(3):
        src = random.choice(INTERNAL_IPS)
        dst = random.choice(SERVER_IPS)
        records.append({
            "src_ip": src, "dst_ip": dst,
            "src_port": random.randint(32768, 65535), "dst_port": 22,
            "protocol": "tcp", "src_bytes": random.randint(500, 10000),
            "dst_bytes": random.randint(1000, 20000),
            "packets": random.randint(10, 100),
            "src_packets": random.randint(5, 50), "dst_packets": random.randint(5, 50),
            "duration": round(random.uniform(1.0, 60.0), 3),
            "syn": 1, "ack": 1, "rst": 0, "fin": 1, "psh": 1, "urg": 0,
            "direction": "outbound", "service": "ssh",
            "state": "ESTABLISHED", "timestamp": now, "label": None,
        })

    # Database traffic
    for _ in range(4):
        src = random.choice(["10.0.0.5", "10.0.0.8", "10.0.0.15"])
        dst = random.choice(["10.0.0.2", "10.0.0.3"])
        records.append({
            "src_ip": src, "dst_ip": dst,
            "src_port": random.randint(32768, 65535), "dst_port": random.choice([5432, 3306, 6379]),
            "protocol": "tcp", "src_bytes": random.randint(200, 5000),
            "dst_bytes": random.randint(500, 50000),
            "packets": random.randint(5, 50),
            "src_packets": random.randint(2, 25), "dst_packets": random.randint(2, 25),
            "duration": round(random.uniform(0.01, 2.0), 3),
            "syn": 1, "ack": 1, "rst": 0, "fin": 0, "psh": 1, "urg": 0,
            "direction": "internal", "service": "database",
            "state": "ESTABLISHED", "timestamp": now, "label": None,
        })

    return records


def generate_suspicious_traffic():
    """Attack traffic that the ML model should detect."""
    records = []
    now = ts()
    attack = random.choice([
        "port_scan", "port_scan", "brute_force", "brute_force",
        "data_exfiltration", "c2_beacon", "ddos", "lateral_movement",
        "reconnaissance", "sql_injection",
    ])

    attacker = random.choice(ATTACKER_IPS)
    target = random.choice(SERVER_IPS + INTERNAL_IPS)

    if attack == "port_scan":
        # Rapid connections to many ports
        for port in random.sample([21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 993, 995, 1433, 3306, 3389, 5432, 5900, 8080, 8443], 8):
            records.append({
                "src_ip": attacker, "dst_ip": target,
                "src_port": random.randint(40000, 65535), "dst_port": port,
                "protocol": "tcp", "src_bytes": 44, "dst_bytes": 0,
                "packets": 1, "src_packets": 1, "dst_packets": 0,
                "duration": 0.001, "syn": 1, "ack": 0, "rst": 1, "fin": 0,
                "psh": 0, "urg": 0, "direction": "inbound",
                "service": "unknown", "state": "REJECTED",
                "timestamp": now, "label": "port_scan",
            })

    elif attack == "brute_force":
        # Many rapid auth attempts to SSH
        for _ in range(random.randint(20, 60)):
            records.append({
                "src_ip": attacker, "dst_ip": target,
                "src_port": random.randint(40000, 65535), "dst_port": 22,
                "protocol": "tcp", "src_bytes": random.randint(1000, 3000),
                "dst_bytes": random.randint(50, 500),
                "packets": random.randint(10, 30),
                "src_packets": random.randint(5, 15), "dst_packets": random.randint(5, 15),
                "duration": round(random.uniform(0.1, 2.0), 3),
                "syn": 1, "ack": 1, "rst": random.choice([0, 0, 1]), "fin": 0,
                "psh": 1, "urg": 0, "direction": "inbound",
                "service": "ssh", "state": "ESTABLISHED",
                "timestamp": now, "label": "brute_force",
            })

    elif attack == "data_exfiltration":
        # Large outbound transfer to suspicious IP
        records.append({
            "src_ip": random.choice(INTERNAL_IPS), "dst_ip": attacker,
            "src_port": random.randint(40000, 65535), "dst_port": random.choice([443, 8443, 53, 80]),
            "protocol": "tcp",
            "src_bytes": random.randint(500000, 10000000),
            "dst_bytes": random.randint(100, 1000),
            "packets": random.randint(500, 10000),
            "src_packets": random.randint(400, 8000), "dst_packets": random.randint(100, 2000),
            "duration": round(random.uniform(30, 300), 3),
            "syn": 1, "ack": 1, "rst": 0, "fin": 1, "psh": 1, "urg": 0,
            "direction": "outbound", "service": "https",
            "state": "ESTABLISHED", "timestamp": now, "label": "data_exfiltration",
        })

    elif attack == "c2_beacon":
        # Regular small packets at intervals (beacon pattern)
        for i in range(random.randint(5, 15)):
            records.append({
                "src_ip": random.choice(INTERNAL_IPS), "dst_ip": attacker,
                "src_port": random.randint(40000, 65535), "dst_port": random.choice([443, 80, 8080]),
                "protocol": "tcp", "src_bytes": random.randint(50, 300),
                "dst_bytes": random.randint(50, 500),
                "packets": random.randint(2, 5),
                "src_packets": 1, "dst_packets": 1,
                "duration": round(random.uniform(0.1, 1.0), 3),
                "syn": 1, "ack": 1, "rst": 0, "fin": 0, "psh": 0, "urg": 0,
                "direction": "outbound", "service": "https",
                "state": "ESTABLISHED", "timestamp": now, "label": "c2_beacon",
            })

    elif attack == "ddos":
        # Many connections from multiple sources
        for _ in range(random.randint(30, 80)):
            src = random.choice(ATTACKER_IPS)
            records.append({
                "src_ip": src, "dst_ip": target,
                "src_port": random.randint(1024, 65535), "dst_port": random.choice([80, 443]),
                "protocol": "tcp", "src_bytes": random.randint(40, 200),
                "dst_bytes": random.randint(0, 100),
                "packets": random.randint(1, 5),
                "src_packets": random.randint(1, 3), "dst_packets": random.randint(0, 2),
                "duration": round(random.uniform(0.001, 0.5), 3),
                "syn": 1, "ack": random.choice([0, 0, 1]), "rst": random.choice([0, 1]),
                "fin": 0, "psh": 0, "urg": 0,
                "direction": "inbound", "service": "http",
                "state": "SYN_SENT", "timestamp": now, "label": "ddos",
            })

    elif attack == "lateral_movement":
        # Internal host scanning other internal hosts
        src = random.choice(INTERNAL_IPS)
        for dst in random.sample([ip for ip in INTERNAL_IPS if ip != src], min(5, len(INTERNAL_IPS) - 1)):
            for port in [22, 445, 3389, 1433, 5985]:
                records.append({
                    "src_ip": src, "dst_ip": dst,
                    "src_port": random.randint(40000, 65535), "dst_port": port,
                    "protocol": "tcp", "src_bytes": random.randint(100, 2000),
                    "dst_bytes": random.randint(100, 2000),
                    "packets": random.randint(2, 10),
                    "src_packets": 1, "dst_packets": 1,
                    "duration": round(random.uniform(0.01, 5.0), 3),
                    "syn": 1, "ack": 1, "rst": random.choice([0, 0, 1]), "fin": 0,
                    "psh": 0, "urg": 0, "direction": "internal",
                    "service": "unknown", "state": "ESTABLISHED",
                    "timestamp": now, "label": "lateral_movement",
                })

    elif attack == "sql_injection":
        # Suspicious database traffic
        records.append({
            "src_ip": attacker, "dst_ip": random.choice(SERVER_IPS),
            "src_port": random.randint(40000, 65535), "dst_port": random.choice([3306, 5432, 1433]),
            "protocol": "tcp", "src_bytes": random.randint(5000, 20000),
            "dst_bytes": random.randint(50000, 500000),
            "packets": random.randint(50, 200),
            "src_packets": random.randint(25, 100), "dst_packets": random.randint(25, 100),
            "duration": round(random.uniform(1.0, 30.0), 3),
            "syn": 1, "ack": 1, "rst": 0, "fin": 1, "psh": 1, "urg": 0,
            "direction": "inbound", "service": "database",
            "state": "ESTABLISHED", "timestamp": now, "label": "sql_injection",
        })

    else:  # reconnaissance
        for port in [80, 443, 22, 8080, 8443]:
            records.append({
                "src_ip": attacker, "dst_ip": target,
                "src_port": random.randint(40000, 65535), "dst_port": port,
                "protocol": "tcp", "src_bytes": random.randint(200, 1000),
                "dst_bytes": random.randint(200, 5000),
                "packets": random.randint(3, 15),
                "src_packets": random.randint(1, 7), "dst_packets": random.randint(1, 7),
                "duration": round(random.uniform(0.1, 5.0), 3),
                "syn": 1, "ack": 1, "rst": 0, "fin": random.choice([0, 1]),
                "psh": 0, "urg": 0, "direction": "inbound",
                "service": "unknown", "state": "ESTABLISHED",
                "timestamp": now, "label": "reconnaissance",
            })

    return records


def generate_logs():
    """Generate realistic system log entries."""
    now = ts()
    logs = []
    templates = [
        {"host": "web-01", "service": "nginx", "level": "info",
         "msg": lambda: f"GET /api/v1/overview 200 {random.randint(5, 200)}ms"},
        {"host": "web-01", "service": "nginx", "level": "info",
         "msg": lambda: f"POST /api/v1/ingest/flows 200 {random.randint(1, 50)}ms"},
        {"host": "auth-01", "service": "sshd", "level": "warn",
         "msg": lambda: f"Failed password for root from {random.choice(ATTACKER_IPS)} port {random.randint(40000,65535)}"},
        {"host": "auth-01", "service": "sshd", "level": "error",
         "msg": lambda: f"Maximum authentication attempts exceeded for invalid user admin from {random.choice(ATTACKER_IPS)}"},
        {"host": "fw-01", "service": "iptables", "level": "warn",
         "msg": lambda: f"DROP IN=eth0 SRC={random.choice(ATTACKER_IPS)} DST=10.0.0.1 PROTO=TCP DPT={random.choice([22,3389,445])}"},
        {"host": "db-01", "service": "postgres", "level": "info",
         "msg": lambda: f"connection authorized: user=aegis database=aegis host={random.choice(INTERNAL_IPS)}"},
        {"host": "app-01", "service": "aegis-backend", "level": "info",
         "msg": lambda: f"ingest batch accepted={random.randint(10,500)} rejected={random.randint(0,5)}"},
        {"host": "dns-01", "service": "bind", "level": "warn",
         "msg": lambda: f"query: {random.choice(['evil-domain.cc','c2-server.net','malware-drop.xyz','phish-site.com'])} IN A from {random.choice(ATTACKER_IPS)}"},
        {"host": "ids-01", "service": "suricata", "level": "warn",
         "msg": lambda: f"ALERT: {random.choice(['ET MALWARE','ET SCAN','GPL ATTACK','ET TROJAN'])} {random.choice(ATTACKER_IPS)} -> {random.choice(SERVER_IPS)}"},
        {"host": "mail-01", "service": "postfix", "level": "warn",
         "msg": lambda: f"reject: RCPT from unknown[{random.choice(ATTACKER_IPS)}]: 550 User not found"},
    ]
    for t in random.sample(templates, min(6, len(templates))):
        logs.append({
            "host": t["host"], "service": t["service"], "level": t["level"],
            "message": t["msg"](), "timestamp": now,
            "parameters": [], "template_id": None, "label": None,
        })
    return logs


def main():
    print("=" * 60)
    print("AEGIS Live Network Traffic Generator")
    print("=" * 60)
    print(f"API: {API_BASE}")
    print()

    if not authenticate():
        return

    round_num = 0
    while True:
        round_num += 1
        now = datetime.now()
        print(f"\n[{now.strftime('%H:%M:%S')}] Round {round_num}")

        # Generate normal traffic
        normal = generate_normal_traffic(count=random.randint(10, 25))
        accepted = send_ndjson(normal, INGEST_FLOWS)
        print(f"  Normal traffic: {len(normal)} flows → {accepted} accepted")

        # Generate suspicious traffic (every round)
        suspicious = generate_suspicious_traffic()
        accepted = send_ndjson(suspicious, INGEST_FLOWS)
        attack_type = suspicious[0].get("label", "unknown") if suspicious else "none"
        print(f"  Suspicious [{attack_type}]: {len(suspicious)} flows → {accepted} accepted")

        # Generate logs
        logs = generate_logs()
        accepted = send_ndjson(logs, INGEST_LOGS)
        print(f"  Logs: {len(logs)} entries → {accepted} accepted")

        # Vary the interval
        sleep_time = random.uniform(3, 8)
        print(f"  Next in {sleep_time:.1f}s...")
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()