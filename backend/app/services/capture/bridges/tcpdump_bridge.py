#!/usr/bin/env python3
"""
tcpdump / tshark → AEGIS Flow Ingestion Bridge

Captures packets using tcpdump or tshark and converts them into
AEGIS flow records.

Usage:
  # With tcpdump (requires root):
  sudo tcpdump -i ethc0 -l -n -tt | python3 tcpdump_bridge.py

  # With tshark (Wireshark CLI):
  tshark -i ethc0 -T fields -e frame.time_epoch -e ip.src -e ip.dst \
    -e tcp.srcport -e tcp.dstport -e ip.proto -e frame.len \
    -e tcp.flags.syn -e tcp.flags.ack -e tcp.flags.reset \
    -e tcp.flags.fin -e tcp.flags.push | python3 tcpdump_bridge.py --format tshark

  # Capture for 60 seconds:
  timeout 60 tcpdump -i ethc0 -l -n -tt | python3 tcpdump_bridge.py

Environment:
  AEGIS_API_URL   - Backend URL (default: http://localhost:8000)
  AEGIS_API_TOKEN - Bearer token (auto-obtained if not set)
"""
import os
import sys
import re
import json
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from collections import defaultdict

API_URL = os.environ.get("AEGIS_API_URL", "http://localhost:8000")
TOKEN = os.environ.get("AEGIS_API_TOKEN", "")
EMAIL = os.environ.get("AEGIS_EMAIL", "admin@aegis.local")
PASSWORD = os.environ.get("AEGIS_PASSWORD", "admin123456789")
BATCH_SIZE = 100
FLUSH_INTERVAL = 5

# tcpdump line pattern:
# 1234567890.123456 IP src.port > dst.port: flags ...
TCPDUMP_RE = re.compile(
    r'(\d+\.\d+)\s+IP6?\s+'
    r'(\S+?)\.(\d+)\s+>\s+(\S+?)\.(\d+):\s+'
    r'(.*)'
)

# UDP pattern:
# 1234567890.123456 IP src.port > dst.port: UDP, length N
UDP_RE = re.compile(
    r'(\d+\.\d+)\s+IP6?\s+'
    r'(\S+?)\.(\d+)\s+>\s+(\S+?)\.(\d+):\s+'
    r'UDP,\s+length\s+(\d+)'
)


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
    return False


def send_batch(records):
    if not records or not TOKEN:
        return 0
    ndjson = "\n".join(json.dumps(r) for r in records)
    req = urllib.request.Request(
        f"{API_URL}/api/v1/ingest/flows",
        data=ndjson.encode(),
        headers={"Content-Type": "application/x-ndjson", "Authorization": f"Bearer {TOKEN}"},
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
    except Exception:
        return 0


def guess_service(port):
    return {80: "http", 443: "https", 22: "ssh", 53: "dns", 25: "smtp",
            3306: "mysql", 5432: "postgres", 6379: "redis"}.get(port, "unknown")


class FlowAggregator:
    """Aggregates packets into flows by 5-tuple, flushing periodically."""

    def __init__(self):
        self.flows = defaultdict(lambda: {
            "packets": 0, "src_bytes": 0, "dst_bytes": 0,
            "src_packets": 0, "dst_packets": 0,
            "syn": 0, "ack": 0, "rst": 0, "fin": 0, "psh": 0, "urg": 0,
            "first_ts": None, "last_ts": None,
        })

    def add(self, ts, src_ip, dst_ip, src_port, dst_port, proto, length, flags=None):
        key = (src_ip, dst_ip, src_port, dst_port, proto)
        flow = self.flows[key]
        if flow["first_ts"] is None:
            flow["first_ts"] = ts
            flow["src_ip"] = src_ip
            flow["dst_ip"] = dst_ip
            flow["src_port"] = src_port
            flow["dst_port"] = dst_port
            flow["protocol"] = proto
        flow["last_ts"] = ts
        flow["packets"] += 1
        flow["src_bytes"] += length
        flow["src_packets"] += 1
        if flags:
            for f in ["syn", "ack", "rst", "fin", "psh", "urg"]:
                if flags.get(f):
                    flow[f] += 1

    def flush(self):
        records = []
        for key, flow in self.flows.items():
            if flow["first_ts"] is None:
                continue
            duration = max(0.001, flow["last_ts"] - flow["first_ts"])
            records.append({
                "src_ip": flow["src_ip"], "dst_ip": flow["dst_ip"],
                "src_port": flow["src_port"], "dst_port": flow["dst_port"],
                "protocol": flow["protocol"],
                "src_bytes": flow["src_bytes"], "dst_bytes": flow["dst_bytes"],
                "packets": flow["packets"],
                "src_packets": flow["src_packets"], "dst_packets": flow["dst_packets"],
                "duration": round(duration, 3),
                "syn": flow["syn"], "ack": flow["ack"],
                "rst": flow["rst"], "fin": flow["fin"],
                "psh": flow["psh"], "urg": flow["urg"],
                "direction": "outbound",
                "service": guess_service(flow["dst_port"]),
                "state": "ESTABLISHED",
                "timestamp": datetime.fromtimestamp(flow["first_ts"], tz=timezone.utc).isoformat(),
                "label": None,
            })
        self.flows.clear()
        return records


def parse_tcpdump_line(line, aggregator):
    """Parse one tcpdump line and add to aggregator."""
    # Try UDP first
    m = UDP_RE.match(line)
    if m:
        ts, src_ip, src_port, dst_ip, dst_port, length = m.groups()
        aggregator.add(
            float(ts), src_ip, dst_ip,
            int(src_port), int(dst_port), "udp", int(length)
        )
        return

    # Try TCP
    m = TCPDUMP_RE.match(line)
    if m:
        ts, src_ip, src_port, dst_ip, dst_port, payload = m.groups()
        flags = {
            "syn": "S" in payload.split(":")[0] and "SA" not in payload.split(":")[0],
            "ack": "A" in payload.split(":")[0],
            "rst": "R" in payload.split(":")[0],
            "fin": "F" in payload.split(":")[0],
            "psh": "P" in payload.split(":")[0],
            "urg": "U" in payload.split(":")[0],
        }
        # Estimate length from payload
        length = len(payload.encode())
        aggregator.add(
            float(ts), src_ip, dst_ip,
            int(src_port), int(dst_port), "tcp", max(40, length), flags
        )


def parse_tshark_line(line, aggregator):
    """Parse one tshark -T fields line."""
    parts = line.strip().split("\t")
    if len(parts) < 7:
        return
    try:
        ts = float(parts[0]) if parts[0] else time.time()
        src_ip = parts[1] or "0.0.0.0"
        dst_ip = parts[2] or "0.0.0.0"
        src_port = int(parts[3]) if parts[3] else 0
        dst_port = int(parts[4]) if parts[4] else 0
        proto = "tcp" if parts[5] == "6" else "udp" if parts[5] == "17" else "other"
        length = int(parts[6]) if parts[6] else 0
        flags = {
            "syn": parts[7] == "1" if len(parts) > 7 else False,
            "ack": parts[8] == "1" if len(parts) > 8 else False,
            "rst": parts[9] == "1" if len(parts) > 9 else False,
            "fin": parts[10] == "1" if len(parts) > 10 else False,
            "psh": parts[11] == "1" if len(parts) > 11 else False,
            "urg": False,
        }
        aggregator.add(ts, src_ip, dst_ip, src_port, dst_port, proto, length, flags)
    except (ValueError, IndexError):
        pass


def main():
    parser = argparse.ArgumentParser(description="tcpdump/tshark → AEGIS bridge")
    parser.add_argument("--format", choices=["tcpdump", "tshark"], default="tcpdump")
    parser.add_argument("--file", "-f", help="Read from file instead of stdin")
    parser.add_argument("--batch-size", "-b", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    if not authenticate():
        sys.exit(1)

    print(f"[TCPDUMP] Bridge started. API={API_URL} format={args.format}", file=sys.stderr)

    aggregator = FlowAggregator()
    last_flush = time.time()
    total_sent = 0
    source = open(args.file, "r") if args.file else sys.stdin

    parse_fn = parse_tshark_line if args.format == "tshark" else parse_tcpdump_line

    try:
        for line in source:
            line = line.strip()
            if not line or line.startswith("tcpdump"):
                continue
            parse_fn(line, aggregator)

            now = time.time()
            if now - last_flush >= FLUSH_INTERVAL:
                records = aggregator.flush()
                if records:
                    for i in range(0, len(records), args.batch_size):
                        accepted = send_batch(records[i:i + args.batch_size])
                        total_sent += accepted
                    print(f"[TCPDUMP] Flows: {len(records)} (total: {total_sent})", file=sys.stderr)
                last_flush = now

    except KeyboardInterrupt:
        pass
    finally:
        records = aggregator.flush()
        if records:
            send_batch(records)
        if args.file:
            source.close()

    print(f"[TCPDUMP] Done. Total sent: {total_sent}", file=sys.stderr)


if __name__ == "__main__":
    main()