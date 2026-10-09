#!/usr/bin/env python3
"""Suricata EVE JSON → AEGIS Ingestion Bridge.

Reads Suricata's eve.json output and converts events into AEGIS records.

UNIQUE ROLE (production):
  Suricata is the IDS/IPS layer. It applies 20,000+ ET Open signatures to
  detect known malware, C2 beacons, exploit attempts, and policy violations.
  This bridge sends:
    - alert events → /api/v1/ingest/logs (with severity, signature, category)
    - flow events  → /api/v1/ingest/flows (5-tuple + bytes + packets)
    - dns events   → /api/v1/ingest/logs (DNS query/response pairs)
    - http events  → /api/v1/ingest/logs (HTTP request metadata)
    - tls events   → /api/v1/ingest/logs (TLS handshake metadata)

  What makes Suricata unique vs other capture services:
    - Signature-based detection (ET Open rules) — catches known threats
    - Protocol parsing (HTTP, DNS, TLS, SMB, SMTP, FTP, SSH)
    - File extraction and hashing (MD5/SHA1/SHA256)
    - JA3/JA3S TLS fingerprinting
    - Anomaly detection (protocol violations, malformed packets)

Usage:
  # Tail eve.json in real-time:
  tail -f /var/log/suricata/eve.json | python3 suricata_bridge.py

  # Pipe directly from Suricata:
  suricata -i eth0 --set outputs.1.eve-log.filename=eve.json -l /var/log/suricata/

Environment:
  AEGIS_API_URL     - Backend URL (default: http://localhost:8000)
  AEGIS_API_TOKEN   - Bearer token (auto-obtained if not set)
"""

import argparse
import json
import os
import queue
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, TextIO

API_URL = os.environ.get("AEGIS_API_URL", "http://localhost:8000")
TOKEN = os.environ.get("AEGIS_API_TOKEN", "")
EMAIL = os.environ.get("AEGIS_EMAIL", "admin@aegis.local")
PASSWORD = os.environ.get("AEGIS_PASSWORD", "admin123456789")
BATCH_SIZE = 100
FLUSH_INTERVAL = 5


_EOF = object()


def iter_lines(source: TextIO) -> Iterator[str | None]:
    """Yield lines from ``source``, or None after FLUSH_INTERVAL seconds of silence.

    A reader thread does the blocking reads, so the caller can still flush
    pending batches when the sensor goes quiet (and on SIGTERM via finally).
    """
    lines: queue.Queue[object] = queue.Queue()

    def pump() -> None:
        for ln in source:
            lines.put(ln)
        lines.put(_EOF)

    threading.Thread(target=pump, daemon=True).start()
    while True:
        try:
            item = lines.get(timeout=FLUSH_INTERVAL)
        except queue.Empty:
            yield None
            continue
        if item is _EOF:
            return
        if isinstance(item, str):
            yield item


def authenticate() -> bool:
    """Obtain a bearer token by logging in (or bootstrapping the admin account)."""
    global TOKEN
    if TOKEN:
        return True
    for endpoint, body in [
        ("/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD}),
        ("/api/v1/auth/setup", {"email": EMAIL, "password": PASSWORD}),
    ]:
        try:
            data = json.dumps(body).encode()
            req = urllib.request.Request(  # noqa: S310 - API_URL is operator-configured
                f"{API_URL}{endpoint}",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310  # nosec B310
                result = json.loads(resp.read())
                TOKEN = result["access_token"]
                print(f"[AUTH] ✓ {result['subject']}", file=sys.stderr)
                return True
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            continue
    print("[AUTH] ✗ Failed", file=sys.stderr)
    return False


def send_batch(records: list[dict[str, Any]], modality: str = "flows") -> int:
    """Send records to the appropriate ingest endpoint."""
    if not records or not TOKEN:
        return 0
    endpoint = f"/api/v1/ingest/{modality}"
    ndjson = "\n".join(json.dumps(r) for r in records)
    req = urllib.request.Request(  # noqa: S310 - API_URL is operator-configured
        f"{API_URL}{endpoint}",
        data=ndjson.encode(),
        headers={
            "Content-Type": "application/x-ndjson",
            "Authorization": f"Bearer {TOKEN}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310
            body = json.loads(resp.read())
            return int(body.get("accepted", 0))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            authenticate()
        return 0
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"[SEND] Error: {e}", file=sys.stderr)
        return 0


def parse_alert(event: dict[str, Any]) -> dict[str, Any]:
    """Suricata alert event → AEGIS log record."""
    """Convert Suricata alert event → AEGIS log record with severity mapping.

    Suricata alerts are the PRIMARY reason to run Suricata in production.
    Each alert carries:
      - signature_id + revision (ET Open rule tracking)
      - severity (1=high, 2=medium, 3=low)
      - category (malware, exploit, policy, etc.)
      - action (allowed/blocked)
      - src/dst with ports
    """
    alert = event.get("alert", {})
    severity = alert.get("severity", 3)

    # Map Suricata severity to AEGIS log level
    level_map = {1: "critical", 2: "warning", 3: "info"}
    level = level_map.get(severity, "info")

    # Build a structured message with signature details
    sig_id = alert.get("signature_id", 0)
    signature = alert.get("signature", "unknown")
    category = alert.get("category", "unknown")
    action = alert.get("action", "allowed")

    src_ip = event.get("src_ip", "")
    dst_ip = event.get("dest_ip", "")
    src_port = event.get("src_port", 0)
    dst_port = event.get("dest_ip", 0)
    proto = event.get("proto", "TCP")

    message = (
        f"[IDS] {signature} | "
        f"sid:{sig_id} cat:{category} action:{action} | "
        f"{src_ip}:{src_port} → {dst_ip}:{dst_port} {proto}"
    )

    return {
        "source": "suricata-alert",
        "level": level,
        "message": message,
        "host": src_ip,
        "timestamp": event.get("timestamp", datetime.now(UTC).isoformat()),
        "structured": {
            "signature_id": sig_id,
            "signature": signature,
            "category": category,
            "severity": severity,
            "action": action,
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "src_port": src_port,
            "dst_port": dst_port,
            "proto": proto,
        },
    }


def parse_flow(event: dict[str, Any]) -> dict[str, Any]:
    """Suricata flow event → AEGIS flow record."""
    """Convert Suricata flow event → AEGIS flow record."""
    return {
        "src_ip": event.get("src_ip", ""),
        "dst_ip": event.get("dest_ip", ""),
        "src_port": event.get("src_port", 0),
        "dst_port": event.get("dest_port", 0),
        "protocol": event.get("proto", "tcp").lower(),
        "src_bytes": event.get("bytes_toserver", 0),
        "dst_bytes": event.get("bytes_toclient", 0),
        "packets": event.get("pkts_toserver", 0) + event.get("pkts_toclient", 0),
        "src_packets": event.get("pkts_toserver", 0),
        "dst_packets": event.get("pkts_toclient", 0),
        "duration": event.get("flow", {}).get("duration", 0),
        "state": event.get("flow", {}).get("state", "unknown"),
        "timestamp": event.get("timestamp", datetime.now(UTC).isoformat()),
        "label": None,
    }


def parse_dns(event: dict[str, Any]) -> dict[str, Any]:
    """Suricata DNS event → AEGIS log record."""
    """Convert Suricata DNS event → AEGIS log record.

    DNS logs are critical for detecting:
    - DNS tunneling (high query volume, large responses)
    - DGA domains (algorithmically generated)
    - C2 beaconing (regular DNS lookups to suspicious domains)
    - Data exfiltration via DNS
    """
    dns = event.get("dns", {})
    query = dns.get("rrname", "")
    rtype = dns.get("rrtype", "A")
    answers = dns.get("answers", [])

    message = f"[DNS] {rtype} query: {query}"
    if answers:
        answer_strs = [a.get("rdata", "") for a in answers[:5]]
        message += f" → {', '.join(answer_strs)}"

    return {
        "source": "suricata-dns",
        "level": "info",
        "message": message,
        "host": event.get("src_ip", ""),
        "timestamp": event.get("timestamp", datetime.now(UTC).isoformat()),
        "structured": {
            "query": query,
            "type": rtype,
            "answers": [a.get("rdata", "") for a in answers],
            "src_ip": event.get("src_ip", ""),
        },
    }


def parse_http(event: dict[str, Any]) -> dict[str, Any]:
    """Suricata HTTP event → AEGIS log record."""
    """Convert Suricata HTTP event → AEGIS log record.

    HTTP logs enable detection of:
    - C2 communication (beaconing patterns, suspicious User-Agents)
    - Data exfiltration (large POST requests, unusual content types)
    - Phishing (URL patterns, redirect chains)
    - Web shell activity (suspicious URL parameters)
    """
    http = event.get("http", {})
    method = http.get("method", "GET")
    url = http.get("url", "")
    host = http.get("hostname", "")
    status = http.get("status", 0)
    ua = http.get("http_user_agent", "")

    message = f"[HTTP] {method} {host}{url} → {status}"
    if ua:
        message += f" UA:{ua[:80]}"

    return {
        "source": "suricata-http",
        "level": "info",
        "message": message,
        "host": event.get("src_ip", ""),
        "timestamp": event.get("timestamp", datetime.now(UTC).isoformat()),
        "structured": {
            "method": method,
            "url": url,
            "hostname": host,
            "status": status,
            "user_agent": ua,
            "content_type": http.get("content_type", ""),
            "length": http.get("length", 0),
            "src_ip": event.get("src_ip", ""),
        },
    }


def parse_tls(event: dict[str, Any]) -> dict[str, Any]:
    """Suricata TLS event → AEGIS log record."""
    """Convert Suricata TLS event → AEGIS log record.

    TLS logs enable detection of:
    - JA3/JA3S fingerprinting (known malware TLS signatures)
    - Certificate anomalies (self-signed, expired, suspicious CN)
    - TLS version downgrade attacks
    - C2 over HTTPS (beaconing patterns in TLS handshakes)
    """
    tls = event.get("tls", {})
    sni = tls.get("sni", "")
    version = tls.get("version", "")
    ja3 = tls.get("ja3", {})
    subject = tls.get("subject", "")
    issuer = tls.get("issuerdn", "")

    message = f"[TLS] {sni} version:{version}"
    if ja3:
        message += f" ja3:{ja3.get('hash', '')[:16]}..."

    return {
        "source": "suricata-tls",
        "level": "info",
        "message": message,
        "host": event.get("src_ip", ""),
        "timestamp": event.get("timestamp", datetime.now(UTC).isoformat()),
        "structured": {
            "sni": sni,
            "version": version,
            "subject": subject,
            "issuer": issuer,
            "ja3_hash": ja3.get("hash", ""),
            "ja3_str": ja3.get("string", ""),
            "not_before": tls.get("notbefore", ""),
            "not_after": tls.get("notafter", ""),
            "src_ip": event.get("src_ip", ""),
        },
    }


def main() -> None:
    """Parse arguments, authenticate, and stream Suricata EVE events to AEGIS."""
    global API_URL, EMAIL, PASSWORD

    # Let the entrypoint's SIGTERM unwind through finally so batches flush.
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

    parser = argparse.ArgumentParser(description="Suricata EVE → AEGIS bridge")
    parser.add_argument("--file", "-f", help="Read from file instead of stdin")
    parser.add_argument("--api", help="AEGIS API URL", default=API_URL)
    parser.add_argument("--email", help="Login email", default=EMAIL)
    parser.add_argument("--password", help="Login password", default=PASSWORD)
    parser.add_argument("--batch-size", "-b", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    API_URL = args.api
    EMAIL = args.email
    PASSWORD = args.password

    if not authenticate():
        sys.exit(1)

    print(f"[SURICATA] Bridge started. API={API_URL}", file=sys.stderr)
    print("[SURICATA] Sending: alerts→logs, flows→flows, dns/http/tls→logs", file=sys.stderr)

    flow_batch: list[dict[str, Any]] = []
    log_batch: list[dict[str, Any]] = []
    last_flush = time.time()
    counts: dict[str, int] = {"alerts": 0, "flows": 0, "dns": 0, "http": 0, "tls": 0}

    source: TextIO = open(args.file) if args.file else sys.stdin  # noqa: SIM115 - closed in finally

    try:
        for raw in iter_lines(source):
            now = time.time()
            if now - last_flush >= FLUSH_INTERVAL:
                if flow_batch:
                    send_batch(flow_batch, "flows")
                    flow_batch = []
                if log_batch:
                    send_batch(log_batch, "logs")
                    log_batch = []
                print(f"[SURICATA] stats: {counts}", file=sys.stderr)
                last_flush = now
            if raw is None:
                continue
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("event_type", "")

            if event_type == "alert":
                log_batch.append(parse_alert(event))
                counts["alerts"] += 1
            elif event_type == "flow":
                flow_batch.append(parse_flow(event))
                counts["flows"] += 1
            elif event_type == "dns":
                log_batch.append(parse_dns(event))
                counts["dns"] += 1
            elif event_type == "http":
                log_batch.append(parse_http(event))
                counts["http"] += 1
            elif event_type == "tls":
                log_batch.append(parse_tls(event))
                counts["tls"] += 1

    except KeyboardInterrupt:
        pass
    finally:
        if flow_batch:
            send_batch(flow_batch, "flows")
        if log_batch:
            send_batch(log_batch, "logs")
        if args.file:
            source.close()

    print(f"[SURICATA] Done. {counts}", file=sys.stderr)


if __name__ == "__main__":
    main()
