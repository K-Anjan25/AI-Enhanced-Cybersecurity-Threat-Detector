#!/usr/bin/env python3
"""
Zeek (Bro) → AEGIS Flow Ingestion Bridge

Reads Zeek's conn.log (tab-separated) and converts each entry into an
AEGIS flow record, then POSTs batches to /api/v1/ingest/flows.

Usage:
  # Pipe from zeek in real-time:
  zeek -i eth0 local | python3 zeek_bridge.py

  # Read existing conn.log:
  tail -f /var/log/zeek/conn.log | python3 zeek_bridge.py

  # One-shot import:
  python3 zeek_bridge.py --file /var/log/zeek/conn.log

Environment:
  AEGIS_API_URL     - Backend URL (default: http://localhost:8000)
  AEGIS_API_TOKEN   - Bearer token (auto-obtained if not set)
  AEGIS_EMAIL       - Login email (default: admin@aegis.local)
  AEGIS_PASSWORD    - Login password (default: admin123456789)
"""
import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone

API_URL = os.environ.get("AEGIS_API_URL", "http://localhost:8000")
TOKEN = os.environ.get("AEGIS_API_TOKEN", "")
EMAIL = os.environ.get("AEGIS_EMAIL", "admin@aegis.local")
PASSWORD = os.environ.get("AEGIS_PASSWORD", "admin123456789")
BATCH_SIZE = 100
FLUSH_INTERVAL = 5  # seconds

# Zeek conn.log fields (standard order)
ZEEK_FIELDS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "service", "duration", "orig_bytes", "resp_bytes",
    "conn_state", "local_orig", "local_resp", "missed_bytes",
    "history", "orig_pkts", "orig_ip_bytes", "resp_pkts", "resp_ip_bytes",
    "tunnel_parents"
]


def authenticate():
    global TOKEN
    if TOKEN:
        return True
    for endpoint, body in [
        ("/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD}),
        ("/api/v1/auth/setup", {"email": EMAIL, "password": PASSWORD}),
    ]:
        try:
            data = json.dumps(body).encode()
            req = urllib.request.Request(
                f"{API_URL}{endpoint}", data=data,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read())
                TOKEN = result["access_token"]
                print(f"[AUTH] ✓ {result['subject']}", file=sys.stderr)
                return True
        except Exception:
            continue
    print("[AUTH] ✗ Failed", file=sys.stderr)
    return False


def send_batch(records):
    if not records or not TOKEN:
        return 0
    ndjson = "\n".join(json.dumps(r) for r in records)
    req = urllib.request.Request(
        f"{API_URL}/api/v1/ingest/flows",
        data=ndjson.encode(),
        headers={
            "Content-Type": "application/x-ndjson",
            "Authorization": f"Bearer {TOKEN}",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            return body.get("accepted", 0)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            authenticate()
        return 0
    except Exception as e:
        print(f"[SEND] Error: {e}", file=sys.stderr)
        return 0


def parse_zeek_line(line):
    """Parse one Zeek conn.log line into an AEGIS flow record."""
    if line.startswith("#"):
        return None
    parts = line.strip().split("\t")
    if len(parts) < 19:
        return None

    try:
        def safe_float(v, default=0.0):
            try:
                return float(v) if v != "-" else default
            except (ValueError, TypeError):
                return default

        def safe_int(v, default=0):
            try:
                return int(float(v)) if v != "-" else default
            except (ValueError, TypeError):
                return default

        ts = safe_float(parts[0])
        timestamp = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else datetime.now(timezone.utc).isoformat()

        proto = parts[6] if parts[6] != "-" else "tcp"
        service = parts[7] if parts[7] != "-" else "unknown"
        duration = safe_float(parts[8], 0.001)

        # Zeek conn_state mapping to TCP state
        conn_state_map = {
            "S0": "SYN_SENT", "S1": "ESTABLISHED", "SF": "ESTABLISHED",
            "REJ": "REJECTED", "S2": "ESTABLISHED", "S3": "ESTABLISHED",
            "RSTO": "CLOSED", "RSTR": "CLOSED", "RSTOS0": "CLOSED",
            "RSTRH": "CLOSED", "SH": "CLOSED", "SHR": "CLOSED",
            "OTH": "UNKNOWN",
        }
        conn_state = conn_state_map.get(parts[11], "UNKNOWN")

        return {
            "src_ip": parts[2],
            "dst_ip": parts[4],
            "src_port": safe_int(parts[3]),
            "dst_port": safe_int(parts[5]),
            "protocol": proto,
            "src_bytes": safe_int(parts[9]),
            "dst_bytes": safe_int(parts[10]),
            "packets": safe_int(parts[16]) + safe_int(parts[18]),
            "src_packets": safe_int(parts[16]),
            "dst_packets": safe_int(parts[18]),
            "duration": round(duration, 3),
            "syn": 1 if "S" in parts[15] else 0,
            "ack": 1 if "A" in parts[15] else 0,
            "rst": 1 if "R" in parts[15] else 0,
            "fin": 1 if "F" in parts[15] else 0,
            "psh": 1 if "D" in parts[15] else 0,  # Zeek uses 'D' for data
            "urg": 0,
            "direction": "inbound" if safe_int(parts[3]) > safe_int(parts[5]) else "outbound",
            "service": service,
            "state": conn_state,
            "timestamp": timestamp,
            "label": None,
        }
    except (IndexError, ValueError) as e:
        print(f"[PARSE] Skipping malformed line: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Zeek → AEGIS bridge")
    parser.add_argument("--file", "-f", help="Read from file instead of stdin")
    parser.add_argument("--batch-size", "-b", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    if not authenticate():
        sys.exit(1)

    print(f"[ZEEK] Bridge started. API={API_URL}", file=sys.stderr)
    print(f"[ZEEK] Reading from {'file: ' + args.file if args.file else 'stdin'}", file=sys.stderr)

    batch = []
    last_flush = time.time()
    total_sent = 0

    source = open(args.file, "r") if args.file else sys.stdin

    try:
        for line in source:
            record = parse_zeek_line(line)
            if record:
                batch.append(record)

            now = time.time()
            if len(batch) >= args.batch_size or (batch and now - last_flush >= FLUSH_INTERVAL):
                accepted = send_batch(batch)
                total_sent += accepted
                print(f"[ZEEK] Sent {len(batch)} → {accepted} accepted (total: {total_sent})", file=sys.stderr)
                batch = []
                last_flush = now
    except KeyboardInterrupt:
        pass
    finally:
        if batch:
            send_batch(batch)
        if args.file:
            source.close()

    print(f"[ZEEK] Done. Total sent: {total_sent}", file=sys.stderr)


if __name__ == "__main__":
    main()