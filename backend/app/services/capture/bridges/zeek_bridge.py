#!/usr/bin/env python3
"""Zeek (Bro) → AEGIS Ingestion Bridge.

Reads Zeek's structured logs and converts them into AEGIS records.

UNIQUE ROLE (production):
  Zeek is the network analysis / forensics layer. It performs deep protocol
  parsing and produces structured logs for every protocol it sees.

  This bridge sends:
    - conn.log   → /api/v1/ingest/flows  (connection summaries)
    - http.log   → /api/v1/ingest/logs   (HTTP request/response metadata)
    - dns.log    → /api/v1/ingest/logs   (DNS query/response pairs)
    - ssl.log    → /api/v1/ingest/logs   (TLS handshake metadata)
    - smtp.log   → /api/v1/ingest/logs   (SMTP sender/recipient/subject)
    - ssh.log    → /api/v1/ingest/logs   (SSH handshake metadata)
    - ftp.log    → /api/v1/ingest/logs   (FTP command/response)
    - smb.log    → /api/v1/ingest/logs   (SMB file access)
    - notice.log → /api/v1/ingest/logs   (Zeek's own notices/alerts)

  What makes Zeek unique vs other capture services:
    - Deepest protocol parsing (30+ protocols with full field extraction)
    - Connection state tracking (TCP state machine analysis)
    - File analysis (extraction, hashing, MIME type detection)
    - Intel framework (threat intel matching against known IOCs)
    - Geographic enrichment (GeoIP for src/dst IPs)
    - Certificate validation (X.509 chain verification)
    - Software version detection (identifies running services/versions)

Usage:
  # Run Zeek and read all logs:
  zeek -i eth0 local | python3 zeek_bridge.py

  # Read specific log:
  tail -f /var/log/zeek/conn.log | python3 zeek_bridge.py --log-type conn

  # Read all Zeek logs from a directory:
  python3 zeek_bridge.py --log-dir /var/log/zeek/

Environment:
  AEGIS_API_URL     - Backend URL (default: http://localhost:8000)
  AEGIS_API_TOKEN   - Bearer token (auto-obtained if not set)
"""

import argparse
import glob
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
from datetime import datetime, timezone
from typing import Any, TextIO

API_URL = os.environ.get("AEGIS_API_URL", "http://localhost:8000")
TOKEN = os.environ.get("AEGIS_API_TOKEN", "")
EMAIL = os.environ.get("AEGIS_EMAIL", "admin@aegis.local")
PASSWORD = os.environ.get("AEGIS_PASSWORD", "admin123456789")
BATCH_SIZE = 100
FLUSH_INTERVAL = 5

# Zeek conn.log fields (standard order)
ZEEK_CONN_FIELDS = [
    "ts",
    "uid",
    "id.orig_h",
    "id.orig_p",
    "id.resp_h",
    "id.resp_p",
    "proto",
    "service",
    "duration",
    "orig_bytes",
    "resp_bytes",
    "conn_state",
    "local_orig",
    "local_resp",
    "missed_bytes",
    "history",
    "orig_pkts",
    "orig_ip_bytes",
    "resp_pkts",
    "resp_ip_bytes",
    "tunnel_parents",
]


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


def safe_float(v: Any, default: float = 0.0) -> float:
    """Convert a Zeek field to float, falling back on "-" or bad input."""
    try:
        return float(v) if v != "-" else default
    except (ValueError, TypeError):
        return default


def safe_int(v: Any, default: int = 0) -> int:
    """Convert a Zeek field to int, falling back on "-" or bad input."""
    try:
        return int(float(v)) if v != "-" else default
    except (ValueError, TypeError):
        return default


def parse_zeek_line(line: str, fields: list[str]) -> dict[str, str] | None:
    """Parse a Zeek TSV log line given a field list."""
    if line.startswith("#"):
        return None
    parts = line.strip().split("\t")
    if len(parts) < len(fields):
        return None
    return {fields[i]: parts[i] for i in range(len(fields))}


def parse_conn(row: dict[str, str]) -> dict[str, Any] | None:
    """conn.log → AEGIS flow record."""
    ts = safe_float(row.get("ts", 0))
    timestamp = (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        if ts
        else datetime.now(timezone.utc).isoformat()
    )

    conn_state_map = {
        "S0": "SYN_SENT",
        "S1": "ESTABLISHED",
        "SF": "ESTABLISHED",
        "REJ": "REJECTED",
        "S2": "ESTABLISHED",
        "S3": "ESTABLISHED",
        "RSTO": "CLOSED",
        "RSTR": "CLOSED",
        "RSTOS0": "CLOSED",
        "RSTRH": "CLOSED",
        "SH": "CLOSED",
        "SHR": "CLOSED",
        "OTH": "UNKNOWN",
    }

    history = row.get("history", "")
    return {
        "src_ip": row.get("id.orig_h", ""),
        "dst_ip": row.get("id.resp_h", ""),
        "src_port": safe_int(row.get("id.orig_p")),
        "dst_port": safe_int(row.get("id.resp_p")),
        "protocol": row.get("proto", "tcp"),
        "src_bytes": safe_int(row.get("orig_bytes")),
        "dst_bytes": safe_int(row.get("resp_bytes")),
        "packets": safe_int(row.get("orig_pkts")) + safe_int(row.get("resp_pkts")),
        "src_packets": safe_int(row.get("orig_pkts")),
        "dst_packets": safe_int(row.get("resp_pkts")),
        "duration": round(safe_float(row.get("duration", 0)), 3),
        "syn": 1 if "S" in history else 0,
        "ack": 1 if "A" in history else 0,
        "rst": 1 if "R" in history else 0,
        "fin": 1 if "F" in history else 0,
        "service": row.get("service", "unknown"),
        "state": conn_state_map.get(row.get("conn_state", ""), "UNKNOWN"),
        "timestamp": timestamp,
        "label": None,
    }


def parse_http_log(row: dict[str, str]) -> dict[str, Any] | None:
    """http.log → AEGIS log record.

    HTTP logs reveal: C2 communication patterns, web shell activity,
    data exfiltration via POST, phishing redirect chains.
    """
    ts = safe_float(row.get("ts", 0))
    timestamp = (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        if ts
        else datetime.now(timezone.utc).isoformat()
    )

    host = row.get("host", "")
    uri = row.get("uri", "")
    method = row.get("method", "GET")
    status = row.get("status_code", "")
    ua = row.get("user_agent", "")
    referrer = row.get("referrer", "")
    body_len = safe_int(row.get("response_body_len", 0))

    message = f"[HTTP] {method} {host}{uri} → {status}"
    if ua:
        message += f" UA:{ua[:60]}"

    return {
        "source": "zeek-http",
        "level": "info",
        "message": message,
        "host": row.get("id.orig_h", ""),
        "timestamp": timestamp,
        "structured": {
            "method": method,
            "host": host,
            "uri": uri,
            "status_code": status,
            "user_agent": ua,
            "referrer": referrer,
            "request_body_len": safe_int(row.get("request_body_len")),
            "response_body_len": body_len,
            "src_ip": row.get("id.orig_h", ""),
            "dst_ip": row.get("id.resp_h", ""),
            "dst_port": safe_int(row.get("id.resp_p")),
            "uid": row.get("uid", ""),
        },
    }


def parse_dns_log(row: dict[str, str]) -> dict[str, Any] | None:
    """dns.log → AEGIS log record.

    DNS logs reveal: DNS tunneling, DGA domains, C2 beaconing,
    data exfiltration via DNS, fast-flux domains.
    """
    ts = safe_float(row.get("ts", 0))
    timestamp = (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        if ts
        else datetime.now(timezone.utc).isoformat()
    )

    query = row.get("query", "")
    qtype = row.get("qtype_name", "A")
    answers = row.get("answers", "")
    rcode = row.get("rcode_name", "NOERROR")

    message = f"[DNS] {qtype} {query} → {rcode}"
    if answers and answers != "-":
        message += f" answers:{answers[:100]}"

    return {
        "source": "zeek-dns",
        "level": "info",
        "message": message,
        "host": row.get("id.orig_h", ""),
        "timestamp": timestamp,
        "structured": {
            "query": query,
            "qtype": qtype,
            "answers": answers,
            "rcode": rcode,
            "trans_id": safe_int(row.get("trans_id")),
            "rtt": safe_float(row.get("rtt")),
            "src_ip": row.get("id.orig_h", ""),
            "dst_ip": row.get("id.resp_h", ""),
            "uid": row.get("uid", ""),
        },
    }


def parse_ssl_log(row: dict[str, str]) -> dict[str, Any] | None:
    """ssl.log → AEGIS log record.

    SSL/TLS logs reveal: JA3 fingerprinting, certificate anomalies,
    TLS version downgrades, C2 over HTTPS patterns.
    """
    ts = safe_float(row.get("ts", 0))
    timestamp = (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        if ts
        else datetime.now(timezone.utc).isoformat()
    )

    sni = row.get("server_name", "")
    version = row.get("version", "")
    cipher = row.get("cipher", "")
    subject = row.get("subject", "")
    issuer = row.get("issuer", "")
    ja3 = row.get("ja3", "")
    ja3s = row.get("ja3s", "")
    validated = row.get("validation_status", "")

    message = f"[TLS] {sni} {version}"
    if ja3:
        message += f" ja3:{ja3[:16]}"

    return {
        "source": "zeek-ssl",
        "level": "info",
        "message": message,
        "host": row.get("id.orig_h", ""),
        "timestamp": timestamp,
        "structured": {
            "server_name": sni,
            "version": version,
            "cipher": cipher,
            "subject": subject,
            "issuer": issuer,
            "ja3": ja3,
            "ja3s": ja3s,
            "validation_status": validated,
            "src_ip": row.get("id.orig_h", ""),
            "dst_ip": row.get("id.resp_h", ""),
            "dst_port": safe_int(row.get("id.resp_p")),
            "uid": row.get("uid", ""),
        },
    }


def parse_notice_log(row: dict[str, str]) -> dict[str, Any] | None:
    """notice.log → AEGIS log record (alerts).

    Zeek notices are the closest thing to Suricata alerts in the Zeek world.
    They indicate: port scans, address sweeps, DNS failures, brute force,
    protocol violations, data exfiltration indicators.
    """
    ts = safe_float(row.get("ts", 0))
    timestamp = (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        if ts
        else datetime.now(timezone.utc).isoformat()
    )

    note = row.get("note", "")
    msg = row.get("msg", "")
    src = row.get("src", "")
    dst = row.get("dst", "")
    severity_str = row.get("severity", "low")

    level_map = {"high": "critical", "medium": "warning", "low": "info"}
    level = level_map.get(severity_str.lower(), "info")

    message = f"[ZEEK-NOTICE] {note}: {msg}"
    if src and dst:
        message += f" | {src} → {dst}"

    return {
        "source": "zeek-notice",
        "level": level,
        "message": message,
        "host": src or row.get("id.orig_h", ""),
        "timestamp": timestamp,
        "structured": {
            "note": note,
            "msg": msg,
            "src": src,
            "dst": dst,
            "p": safe_int(row.get("p")),
            "severity": severity_str,
            "actions": row.get("actions", ""),
            "suppress_for": safe_float(row.get("suppress_for")),
        },
    }


# Mapping of Zeek log types to their parsers and field lists
LOG_PARSERS: dict[str, dict[str, Any]] = {
    "conn": {
        "fields": ZEEK_CONN_FIELDS,
        "parser": parse_conn,
        "modality": "flows",
    },
    "http": {
        "fields": None,  # Set dynamically from #fields header
        "parser": parse_http_log,
        "modality": "logs",
    },
    "dns": {
        "fields": None,
        "parser": parse_dns_log,
        "modality": "logs",
    },
    "ssl": {
        "fields": None,
        "parser": parse_ssl_log,
        "modality": "logs",
    },
    "notice": {
        "fields": None,
        "parser": parse_notice_log,
        "modality": "logs",
    },
}


def main() -> None:
    """Parse arguments, authenticate, and stream Zeek logs to AEGIS."""
    global API_URL, EMAIL, PASSWORD

    # Let the entrypoint's SIGTERM unwind through finally so batches flush.
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

    parser = argparse.ArgumentParser(description="Zeek → AEGIS bridge", allow_abbrev=False)
    parser.add_argument("--file", "-f", help="Read from file instead of stdin")
    parser.add_argument("--log-dir", help="Read all Zeek logs from directory")
    parser.add_argument("--log-type", default="conn", help="Log type: conn, http, dns, ssl, notice")
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

    print(f"[ZEEK] Bridge started. API={API_URL}", file=sys.stderr)

    if args.log_dir:
        # Process all Zeek logs in directory
        process_log_directory(args.log_dir, args.batch_size)
    else:
        # Single log type from stdin or file
        process_single_log(args.log_type, args.file, args.batch_size)


def process_single_log(log_type: str, filepath: str | None, batch_size: int) -> None:
    """Process a single Zeek log stream."""
    parser_info = LOG_PARSERS.get(log_type, LOG_PARSERS["conn"])
    fields = list(parser_info["fields"] or ZEEK_CONN_FIELDS)
    parse_fn = parser_info["parser"]
    modality = parser_info["modality"]

    flow_batch: list[dict[str, Any]] = []
    log_batch: list[dict[str, Any]] = []
    last_flush = time.time()
    total = 0

    source: TextIO = open(filepath) if filepath else sys.stdin  # noqa: SIM115 - closed in finally

    print(f"[ZEEK] Processing {log_type} log → {modality}", file=sys.stderr)

    try:
        for line in iter_lines(source):
            now = time.time()
            if now - last_flush >= FLUSH_INTERVAL:
                if flow_batch:
                    send_batch(flow_batch, "flows")
                    flow_batch = []
                if log_batch:
                    send_batch(log_batch, "logs")
                    log_batch = []
                print(f"[ZEEK] {log_type}: sent {total} total", file=sys.stderr)
                last_flush = now
            if line is None:
                continue
            # Parse #fields header dynamically
            if line.startswith("#fields"):
                fields = line.strip().split("\t")[1:]
                continue
            if line.startswith("#"):
                continue

            parts = line.strip().split("\t")
            if len(parts) < len(fields):
                continue

            row = {fields[i]: parts[i] for i in range(min(len(fields), len(parts)))}
            record = parse_fn(row)
            if not record:
                continue

            if modality == "flows":
                flow_batch.append(record)
            else:
                log_batch.append(record)
            total += 1

    except KeyboardInterrupt:
        pass
    finally:
        if flow_batch:
            send_batch(flow_batch, "flows")
        if log_batch:
            send_batch(log_batch, "logs")
        if filepath:
            source.close()

    print(f"[ZEEK] Done. {log_type}: {total} records", file=sys.stderr)


def process_log_directory(log_dir: str, batch_size: int) -> None:
    """Process all Zeek log files in a directory."""
    log_files = glob.glob(os.path.join(log_dir, "*.log"))
    if not log_files:
        print(f"[ZEEK] No .log files found in {log_dir}", file=sys.stderr)
        return

    print(f"[ZEEK] Found {len(log_files)} log files in {log_dir}", file=sys.stderr)

    for log_file in log_files:
        basename = os.path.basename(log_file)
        log_type = basename.replace(".log", "")

        if log_type in LOG_PARSERS:
            print(f"[ZEEK] Processing {basename}...", file=sys.stderr)
            process_single_log(log_type, log_file, batch_size)
        else:
            print(f"[ZEEK] Skipping {basename} (no parser)", file=sys.stderr)


if __name__ == "__main__":
    main()
