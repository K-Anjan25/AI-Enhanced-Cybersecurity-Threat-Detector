#!/usr/bin/env python3
"""
Suricata EVE JSON → AEGIS Ingestion Bridge

Reads Suricata's eve.json output and converts flow/alert events into
AEGIS flow and log records.

Usage:
  # Tail eve.json in real-time:
  tail -f /var/log/suricata/eve.json | python3 suricata_bridge.py

  # Pipe directly from Suricata:
  suricata -i ethc0 --set outputs.1.eve-log.filename=eve.json -l /var/log/suricata/
  tail -f /var/log/suricata/eve.json | python3 suricata_bridge.py

  # One-shot:
  python3 suricata_bridge.py --file /var/log/suricata/eve.json

Environment:
  AEGIS_API_URL     - Backend URL (default: http://localhost:8000)
  AEGIS_API_TOKEN   - Bearer token (auto-obtained if not set)
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
FLUSH_INTERVAL = 5


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
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            return body.get("accepted", 0)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            authenticate()
        return 0
    except Exception:
        return 0


def parse_flow_event(event):
    """Convert a Suricata flow event to an AEGIS flow record."""
    flow = event.get("flow", {})
    src = event.get("src_ip", "")
    dst = event.get("dest_ip", "")
    sp = event.get("src_port", 0)
    dp = event.get("dest_port", 0)

    pkts_toserver = flow.get("pkts_toserver", 0)
    pkts_toclient = flow.get("pkts_toclient", 0)
    bytes_toserver = flow.get("bytes_toserver", 0)
    bytes_toclient = flow.get("bytes_toclient", 0)

    state_map = {
        "new": "SYN_SENT", "established": "ESTABLISHED",
        "closed": "CLOSED", "not_found": "UNKNOWN",
    }

    return {
        "src_ip": src, "dst_ip": dst,
        "src_port": int(sp) if sp else 0,
        "dst_port": int(dp) if dp else 0,
        "protocol": event.get("proto", "tcp"),
        "src_bytes": bytes_toserver,
        "dst_bytes": bytes_toclient,
        "packets": pkts_toserver + pkts_toclient,
        "src_packets": pkts_toserver,
        "dst_packets": pkts_toclient,
        "duration": round(float(flow.get("age", 0.001)), 3),
        "syn": 1 if flow.get("state", "") in ("new",) else 0,
        "ack": 1 if flow.get("state", "") in ("established", "closed") else 0,
        "rst": 1 if "RST" in flow.get("reason", "").upper() else 0,
        "fin": 1 if flow.get("state", "") == "closed" else 0,
        "psh": 0, "urg": 0,
        "direction": "inbound" if int(dp) < int(sp) else "outbound",
        "service": event.get("app_proto", "unknown"),
        "state": state_map.get(flow.get("state", ""), "UNKNOWN"),
        "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "label": None,
    }


def parse_alert_event(event):
    """Convert a Suricata alert event to an AEGIS log record."""
    alert = event.get("alert", {})
    severity_map = {1: "error", 2: "warn", 3: "info"}

    return {
        "host": event.get("host", "suricata-sensor"),
        "service": "suricata",
        "level": severity_map.get(alert.get("severity", 3), "warn"),
        "message": f"{alert.get('signature', 'Unknown alert')} | "
                   f"{event.get('src_ip', '')}:{event.get('src_port', '')} -> "
                   f"{event.get('dest_ip', '')}:{event.get('dest_port', '')} "
                   f"[{alert.get('category', '')}] {alert.get('action', 'allowed')}",
        "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "parameters": [],
        "template_id": None,
        "label": None,
    }


def parse_dns_event(event):
    """Convert Suricata DNS event to AEGIS log record."""
    dns = event.get("dns", {})
    return {
        "host": event.get("host", "suricata-sensor"),
        "service": "dns-sensor",
        "level": "info",
        "message": f"DNS {dns.get('type', 'query')} {dns.get('rrname', '')} "
                   f"→ {dns.get('rdata', '')} [{dns.get('rrtype', '')}]",
        "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "parameters": [],
        "template_id": None,
        "label": None,
    }


def main():
    parser = argparse.ArgumentParser(description="Suricata → AEGIS bridge")
    parser.add_argument("--file", "-f", help="Read from file instead of stdin")
    parser.add_argument("--batch-size", "-b", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    if not authenticate():
        sys.exit(1)

    print(f"[SURICATA] Bridge started. API={API_URL}", file=sys.stderr)

    flow_batch = []
    log_batch = []
    last_flush = time.time()
    total_flows = 0
    total_logs = 0

    source = open(args.file, "r") if args.file else sys.stdin

    try:
        for line in source:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("event_type", "")

            if event_type == "flow":
                record = parse_flow_event(event)
                flow_batch.append(record)
            elif event_type == "alert":
                record = parse_alert_event(event)
                log_batch.append(record)
            elif event_type == "dns":
                record = parse_dns_event(event)
                log_batch.append(record)

            now = time.time()
            if now - last_flush >= FLUSH_INTERVAL or len(flow_batch) >= args.batch_size:
                if flow_batch:
                    accepted = send_ndjson(flow_batch, f"{API_URL}/api/v1/ingest/flows")
                    total_flows += accepted
                    print(f"[SURICATA] Flows: {len(flow_batch)} → {accepted} accepted (total: {total_flows})", file=sys.stderr)
                    flow_batch = []
                if log_batch:
                    accepted = send_ndjson(log_batch, f"{API_URL}/api/v1/ingest/logs")
                    total_logs += accepted
                    print(f"[SURICATA] Logs: {len(log_batch)} → {accepted} accepted (total: {total_logs})", file=sys.stderr)
                    log_batch = []
                last_flush = now

    except KeyboardInterrupt:
        pass
    finally:
        if flow_batch:
            send_ndjson(flow_batch, f"{API_URL}/api/v1/ingest/flows")
        if log_batch:
            send_ndjson(log_batch, f"{API_URL}/api/v1/ingest/logs")
        if args.file:
            source.close()

    print(f"[SURICATA] Done. Flows={total_flows}, Logs={total_logs}", file=sys.stderr)


if __name__ == "__main__":
    main()