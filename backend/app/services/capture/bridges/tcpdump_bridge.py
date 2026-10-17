#!/usr/bin/env python3
"""tshark / tcpdump → AEGIS Flow Ingestion Bridge.

UNIQUE ROLE (production):
  tshark (Wireshark CLI) is the protocol dissection layer. It provides the
  deepest field-level protocol analysis available, with 3,000+ protocol
  dissectors. This bridge sends:
    - Flow records  → /api/v1/ingest/flows  (aggregated from packets)
    - Protocol logs → /api/v1/ingest/logs   (per-packet protocol details)

  What makes tshark unique vs other capture services:
    - 3,000+ protocol dissectors (the widest protocol coverage)
    - Field-level extraction (every protocol field is accessible)
    - Display filter language (Wireshark's powerful filtering)
    - Reassembly (TCP stream reassembly, HTTP chunked encoding, etc.)
    - Decryption support (with key log files for TLS)
    - Expert info (protocol warnings, errors, malformations)

  In production, tshark is used for:
    - Protocol-specific deep dives (SMB, RDP, MQTT, Modbus, etc.)
    - Forensic packet analysis (when you need to see every byte)
    - Custom protocol monitoring (extract specific fields)
    - Performance analysis (TCP retransmissions, window sizes, RTT)

  For basic flow capture, tcpdump is sufficient. tshark is used when you
  need protocol-level detail that neither Zeek nor Suricata provides.

Usage:
  # With tshark (Wireshark CLI):
  tshark -i eth0 -T fields -e frame.time_epoch -e ip.src -e ip.dst \
    -e tcp.srcport -e tcp.dstport -e ip.proto -e frame.len \
    -e tcp.flags.syn -e tcp.flags.ack -e tcp.flags.reset \
    -e tcp.flags.fin -e tcp.flags.push | python3 tcpdump_bridge.py --format tshark

  # With tcpdump (basic flow capture):
  tcpdump -i eth0 -l -n -tt | python3 tcpdump_bridge.py

  # Capture DNS queries specifically:
  tshark -i eth0 -Y "dns.qry.name" -T fields \
    -e frame.time_epoch -e ip.src -e ip.dst -e dns.qry.name -e dns.qry.type \
    | python3 tcpdump_bridge.py --format tshark-dns

Environment:
  AEGIS_API_URL   - Backend URL (default: http://localhost:8000)
  AEGIS_API_TOKEN - Bearer token (auto-obtained if not set)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

API_URL = os.environ.get("AEGIS_API_URL", "http://localhost:8000")
TOKEN = os.environ.get("AEGIS_API_TOKEN", "")
EMAIL = os.environ.get("AEGIS_EMAIL", "admin@aegis.local")
PASSWORD = os.environ.get("AEGIS_PASSWORD", "")
DEV_DEFAULT_PASSWORD = "admin123456789"  # noqa: S105  # nosec B105 - the development default, refused at startup
BATCH_SIZE = 100
FLUSH_INTERVAL = 5


def authenticate(force: bool = False) -> bool:
    """Obtain a bearer token by logging in (or bootstrapping the admin account).

    ``force`` discards the cached token first. A 401 means that token has expired
    (access tokens last 900 s), so the retry must log in again; returning early on
    the stale token is what left the bridge posting 401s until it was restarted.
    """
    global TOKEN
    if force:
        TOKEN = ""  # nosec B105 - clears the cached token; this is not a credential
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


# ── flow@1 contract ─────────────────────────────────────────────────────────────
#
# The ingest endpoint accepts only flow@1 and rejects any field outside it. This file is
# copied into its container on its own, so the mapping lives here.

_FLOW_V1_FIELDS = (
    "timestamp",
    "src_ip",
    "dst_ip",
    "src_port",
    "dst_port",
    "protocol",
    "direction",
    "service",
    "state",
    "packets",
    "src_packets",
    "dst_packets",
    "src_bytes",
    "dst_bytes",
    "duration",
    "syn",
    "ack",
    "rst",
    "fin",
    "psh",
    "urg",
    "label",
)
_FLOW_V1_PROTOCOLS = {
    "tcp": "tcp",
    "udp": "udp",
    "icmp": "icmp",
    "6": "tcp",
    "17": "udp",
    "1": "icmp",
}
_FLOW_V1_COUNTS = (
    "src_port",
    "dst_port",
    "packets",
    "src_packets",
    "dst_packets",
    "src_bytes",
    "dst_bytes",
    "syn",
    "ack",
    "rst",
    "fin",
    "psh",
    "urg",
)


def _ipv4(ip: object) -> bool:
    import ipaddress

    try:
        return isinstance(ipaddress.ip_address(str(ip)), ipaddress.IPv4Address)
    except ValueError:
        return False


def _direction(src_ip: str, dst_ip: str) -> str:
    import ipaddress

    def internal(ip: str) -> bool:
        a = ipaddress.ip_address(ip)
        return a.is_private or a.is_loopback or a.is_link_local

    src_in, dst_in = internal(src_ip), internal(dst_ip)
    if src_in and dst_in:
        return "internal"
    return "outbound" if src_in else "inbound"


def to_flow_v1(record: dict[str, Any]) -> dict[str, Any] | None:
    """Map a bridge flow record to flow@1, or None when it cannot be one.

    Records with a protocol outside tcp/udp/icmp or a non-IPv4 address are dropped, not
    rewritten: a rewritten value would be a claim the sensor did not observe.
    """
    proto = _FLOW_V1_PROTOCOLS.get(str(record.get("protocol", "")).lower())
    src_ip, dst_ip = str(record.get("src_ip", "")), str(record.get("dst_ip", ""))
    if proto is None or not (_ipv4(src_ip) and _ipv4(dst_ip)):
        return None
    out: dict[str, Any] = {k: record[k] for k in _FLOW_V1_FIELDS if record.get(k) is not None}
    for key in _FLOW_V1_COUNTS:
        out[key] = int(out.get(key) or 0)
    out.update(
        schema_version="flow@1",
        protocol=proto,
        direction=_direction(src_ip, dst_ip),
        duration=max(0.0, float(record.get("duration") or 0.0)),
    )
    out.setdefault("packets", out["src_packets"] + out["dst_packets"])
    return out


def send_batch(records: list[dict[str, Any]], modality: str = "flows") -> int:
    """Send records to the appropriate ingest endpoint."""
    if modality == "flows":
        records = [c for c in (to_flow_v1(r) for r in records) if c is not None]
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
            authenticate(force=True)
        return 0
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"[SEND] Error: {e}", file=sys.stderr)
        return 0


# ── tcpdump format ──────────────────────────────────────────────

TCPDUMP_RE = re.compile(r"(\d+\.\d+)\s+IP\s+(\S+)\s+>\s+(\S+):\s+(.*)")

TCPDUMP_DNS_RE = re.compile(
    r"(\d+\.\d+)\s+IP\s+(\S+)\.(\d+)\s+>\s+(\S+)\.53:\s+(\d+)\+ (A|AAAA|PTR|MX|TXT)\??\s+(\S+)"
)


def _split_addr(token: str) -> tuple[str, int]:
    """Split tcpdump's "a.b.c.d.port" into ("a.b.c.d", port). No port -> (token, 0)."""
    host, sep, port = token.rpartition(".")
    if sep and port.isdigit() and host.count(".") == 3:
        return host, int(port)
    return token, 0


def parse_tcpdump_line(line: str) -> dict[str, Any] | None:
    """Parse tcpdump -n -tt output into a basic flow record."""
    # DNS query pattern
    m = TCPDUMP_DNS_RE.match(line)
    if m:
        ts, src, sport, dst, tid, qtype, qname = m.groups()
        return {
            "type": "flow",
            "record": {
                "src_ip": src,
                "dst_ip": dst,
                "src_port": int(sport),
                "dst_port": 53,
                "protocol": "udp",
                "src_bytes": 0,
                "dst_bytes": 0,
                "packets": 1,
                "duration": 0,
                "timestamp": datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat(),
                "label": None,
            },
        }

    # Generic IP pattern
    m = TCPDUMP_RE.match(line)
    if m:
        ts = m.group(1)
        # Basic: just record src > dst
        # Groups: 1 = timestamp, 2 = "src.port", 3 = "dst.port" (the regex drops the ">").
        src, dst = m.group(2).rstrip(":"), m.group(3).rstrip(":")
        return {
            "type": "flow",
            "record": {
                "src_ip": _split_addr(src)[0],
                "dst_ip": _split_addr(dst)[0],
                "src_port": _split_addr(src)[1],
                "dst_port": _split_addr(dst)[1],
                "protocol": "tcp",
                "src_bytes": 0,
                "dst_bytes": 0,
                "packets": 1,
                "duration": 0,
                "timestamp": datetime.fromtimestamp(float(m.group(1)), tz=timezone.utc).isoformat(),
                "label": None,
            },
        }

    return None


# ── tshark fields format ────────────────────────────────────────


def parse_tshark_line(line: str) -> dict[str, Any] | None:
    """Parse tshark -T fields output.

    Default fields: frame.time_epoch, ip.src, ip.dst, tcp.srcport,
    tcp.dstport, ip.proto, frame.len, tcp.flags.syn, tcp.flags.ack,
    tcp.flags.reset, tcp.flags.fin, tcp.flags.push
    """
    parts = line.strip().split("\t")
    if len(parts) < 6:
        return None

    try:
        ts = float(parts[0]) if parts[0] else 0
        src_ip = parts[1] if len(parts) > 1 else ""
        dst_ip = parts[2] if len(parts) > 2 else ""
        src_port = int(parts[3]) if len(parts) > 3 and parts[3] else 0
        dst_port = int(parts[4]) if len(parts) > 4 and parts[4] else 0
        proto = parts[5] if len(parts) > 5 else "tcp"
        frame_len = int(parts[6]) if len(parts) > 6 and parts[6] else 0

        # TCP flags
        syn = int(parts[7]) if len(parts) > 7 and parts[7] else 0
        ack = int(parts[8]) if len(parts) > 8 and parts[8] else 0
        rst = int(parts[9]) if len(parts) > 9 and parts[9] else 0
        fin = int(parts[10]) if len(parts) > 10 and parts[10] else 0
        psh = int(parts[11]) if len(parts) > 11 and parts[11] else 0

        timestamp = (
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            if ts
            else datetime.now(timezone.utc).isoformat()
        )

        return {
            "type": "flow",
            "record": {
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "src_port": src_port,
                "dst_port": dst_port,
                "protocol": proto.lower(),
                "src_bytes": frame_len,
                "dst_bytes": 0,
                "packets": 1,
                "syn": syn,
                "ack": ack,
                "rst": rst,
                "fin": fin,
                "psh": psh,
                "duration": 0,
                "timestamp": timestamp,
                "label": None,
            },
        }
    except (ValueError, IndexError):
        return None


def parse_tshark_dns_line(line: str) -> dict[str, Any] | None:
    """Parse tshark DNS query fields output.

    Fields: frame.time_epoch, ip.src, ip.dst, dns.qry.name, dns.qry.type
    """
    parts = line.strip().split("\t")
    if len(parts) < 5:
        return None

    try:
        ts = float(parts[0]) if parts[0] else 0
        src_ip = parts[1]
        dst_ip = parts[2]
        qname = parts[3]
        qtype = parts[4] if parts[4] else "A"

        timestamp = (
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            if ts
            else datetime.now(timezone.utc).isoformat()
        )

        return {
            "type": "log",
            "record": {
                "source": "tshark-dns",
                "level": "info",
                "message": f"[DNS] {qtype} query: {qname} from {src_ip} → {dst_ip}",
                "host": src_ip,
                "timestamp": timestamp,
                "structured": {
                    "query": qname,
                    "qtype": qtype,
                    "src_ip": src_ip,
                    "dst_ip": dst_ip,
                },
            },
        }
    except (ValueError, IndexError):
        return None


def main() -> None:
    """Parse arguments, authenticate, and stream tcpdump/tshark output to AEGIS."""
    global API_URL, EMAIL, PASSWORD

    parser = argparse.ArgumentParser(
        description="tshark/tcpdump → AEGIS bridge", allow_abbrev=False
    )
    parser.add_argument(
        "--format",
        choices=["tcpdump", "tshark", "tshark-dns"],
        default="tcpdump",
        help="Input format",
    )
    parser.add_argument("--api", help="AEGIS API URL", default=API_URL)
    parser.add_argument("--email", help="Login email", default=EMAIL)
    parser.add_argument("--password", help="Login password", default=PASSWORD)
    parser.add_argument("--batch-size", "-b", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    API_URL = args.api
    EMAIL = args.email
    PASSWORD = args.password

    if not PASSWORD or PASSWORD == DEV_DEFAULT_PASSWORD:
        print(
            "refusing to start: set AEGIS_PASSWORD (AEGIS_BOOTSTRAP_ADMIN_PASSWORD in "
            "docker/.env) to a value other than the development default",
            file=sys.stderr,
        )
        sys.exit(2)

    if not authenticate():
        sys.exit(1)

    print(f"[TSHARK] Bridge started. API={API_URL} format={args.format}", file=sys.stderr)

    # Select parser
    if args.format == "tshark-dns":
        parse_fn = parse_tshark_dns_line
    elif args.format == "tshark":
        parse_fn = parse_tshark_line
    else:
        parse_fn = parse_tcpdump_line

    flow_batch: list[dict[str, Any]] = []
    log_batch: list[dict[str, Any]] = []
    last_flush = time.time()
    total_flows = 0
    total_logs = 0

    try:
        for line in sys.stdin:
            result = parse_fn(line)
            if not result:
                continue

            if result["type"] == "flow":
                flow_batch.append(result["record"])
                total_flows += 1
            else:
                log_batch.append(result["record"])
                total_logs += 1

            now = time.time()
            if now - last_flush >= FLUSH_INTERVAL:
                if flow_batch:
                    send_batch(flow_batch, "flows")
                    flow_batch = []
                if log_batch:
                    send_batch(log_batch, "logs")
                    log_batch = []
                print(f"[TSHARK] flows:{total_flows} logs:{total_logs}", file=sys.stderr)
                last_flush = now

    except KeyboardInterrupt:
        pass

    if flow_batch:
        send_batch(flow_batch, "flows")
    if log_batch:
        send_batch(log_batch, "logs")

    print(f"[TSHARK] Done. flows:{total_flows} logs:{total_logs}", file=sys.stderr)


if __name__ == "__main__":
    main()
