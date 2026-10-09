"""Network capture service — captures REAL traffic from the host network interface.

This runs as a Docker container with network_mode: host so it can see
actual packets on the host's network interface. No simulated data.

Uses scapy to capture packets, aggregates them into flow records,
and sends them to the AEGIS backend ingest API.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from typing import Any

try:
    from scapy.all import DNS, IP, TCP, UDP, sniff

    HAS_SCAPY = True
except ImportError:
    HAS_SCAPY = False

import urllib.error
import urllib.request

__all__ = ["FlowAggregator", "CaptureService"]

API_BASE = os.environ.get("AEGIS_API_URL", "http://backend:8000")
API_EMAIL = os.environ.get("AEGIS_EMAIL", "admin@aegis.local")
API_PASSWORD = os.environ.get("AEGIS_PASSWORD", "admin123456789")
INTERFACE = os.environ.get("AEGIS_CAPTURE_INTERFACE", "eth0")
FLUSH_INTERVAL = int(os.environ.get("AEGIS_FLUSH_INTERVAL", "10"))
BATCH_SIZE = int(os.environ.get("AEGIS_BATCH_SIZE", "200"))
FILTER_EXPR = os.environ.get("AEGIS_CAPTURE_FILTER", "")


class FlowAggregator:
    """Aggregates raw packets into flow records by 5-tuple.

    A flow is keyed by (src_ip, dst_ip, src_port, dst_port, proto).
    Packets are accumulated and flushed as flow records.
    """

    def __init__(self, max_flows: int = 50_000, timeout: int = 120) -> None:
        """Create an empty flow table bounded by max_flows and idle timeout (seconds)."""
        self._flows: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._max_flows = max_flows
        self._timeout = timeout
        self._lock = threading.Lock()
        self._packet_count = 0
        self._flow_count = 0

    @property
    def stats(self) -> dict[str, int]:
        """Return packet and flow counters."""
        with self._lock:
            return {
                "packets": self._packet_count,
                "active_flows": len(self._flows),
                "total_flows": self._flow_count,
            }

    def add_packet(
        self,
        src_ip: str,
        dst_ip: str,
        src_port: int,
        dst_port: int,
        proto: str,
        length: int,
        ts: float,
        *,
        is_outbound: bool = True,
        dns_query: str | None = None,
    ) -> None:
        """Add one packet to the aggregator."""
        key = (src_ip, dst_ip, src_port, dst_port, proto)

        with self._lock:
            self._packet_count += 1

            if key not in self._flows:
                if len(self._flows) >= self._max_flows:
                    self._evict_oldest()
                self._flows[key] = {
                    "ts": ts,
                    "src_ip": src_ip,
                    "dst_ip": dst_ip,
                    "src_port": src_port,
                    "dst_port": dst_port,
                    "proto": proto,
                    "service": self._guess_service(dst_port, dns_query),
                    "orig_bytes": 0,
                    "resp_bytes": 0,
                    "orig_pkts": 0,
                    "resp_pkts": 0,
                    "conn_state": "SF",
                    "last_seen": ts,
                    "source": "capture",
                }

            flow = self._flows[key]
            if is_outbound:
                flow["orig_bytes"] += length
                flow["orig_pkts"] += 1
            else:
                flow["resp_bytes"] += length
                flow["resp_pkts"] += 1
            flow["last_seen"] = ts
            flow["duration"] = ts - flow["ts"]

    def flush(self) -> list[dict[str, Any]]:
        """Flush all accumulated flows as a list of dicts."""
        with self._lock:
            flows = list(self._flows.values())
            self._flows.clear()
            self._flow_count += len(flows)
            return flows

    def _evict_oldest(self) -> None:
        """Evict the oldest flow when at capacity."""
        if not self._flows:
            return
        oldest_key = min(self._flows, key=lambda k: self._flows[k]["last_seen"])
        del self._flows[oldest_key]

    @staticmethod
    def _guess_service(port: int, dns_query: str | None = None) -> str:
        """Guess service name from port number."""
        if dns_query:
            return "dns"
        services = {
            80: "http",
            443: "https",
            22: "ssh",
            21: "ftp",
            25: "smtp",
            53: "dns",
            3306: "mysql",
            5432: "postgresql",
            6379: "redis",
            27017: "mongodb",
            3389: "rdp",
            445: "smb",
            139: "netbios",
            8080: "http-proxy",
            8443: "https-alt",
            9090: "webcache",
        }
        return services.get(port, "")


class CaptureService:
    """Main capture service — sniffs packets and sends flows to AEGIS."""

    def __init__(self) -> None:
        """Create the aggregator and reset the auth token and counters."""
        self._aggregator = FlowAggregator()
        self._token: str | None = None
        self._running = False
        self._send_thread: threading.Thread | None = None
        self._capture_thread: threading.Thread | None = None
        self._flownet_stats: dict[str, int] = {
            "packets_captured": 0,
            "flows_sent": 0,
            "send_errors": 0,
        }
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum: int, frame: Any) -> None:
        print(f"\n[CORE] Signal {signum} received, shutting down...")
        self._running = False

    def _auth(self) -> str | None:
        """Authenticate with the AEGIS backend."""
        if self._token:
            return self._token
        data = json.dumps({"email": API_EMAIL, "password": API_PASSWORD}).encode()
        req = urllib.request.Request(  # noqa: S310 - API_BASE is operator-configured
            f"{API_BASE}/api/v1/auth/login",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)  # noqa: S310  # nosec B310
            result = json.loads(resp.read())
            self._token = result["access_token"]
            print(f"[AUTH] Authenticated as {API_EMAIL}")
            return self._token
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            print(f"[AUTH] Failed: {e}", file=sys.stderr)
            return None

    def _send_flows(self, flows: list[dict[str, Any]]) -> bool:
        """Send a batch of flow records to AEGIS ingest API."""
        token = self._auth()
        if not token:
            return False

        body = "\n".join(json.dumps(f) for f in flows)
        req = urllib.request.Request(  # noqa: S310 - API_BASE is operator-configured
            f"{API_BASE}/api/v1/ingest/flows",
            data=body.encode(),
            headers={
                "Content-Type": "application/x-ndjson",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            resp = urllib.request.urlopen(req, timeout=15)  # noqa: S310  # nosec B310
            result = json.loads(resp.read())
            accepted = int(result.get("accepted", 0))
            self._flownet_stats["flows_sent"] += accepted
            return True
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self._token = None
            self._flownet_stats["send_errors"] += 1
            print(f"[SEND] Error {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
            return False
        except (urllib.error.URLError, OSError, ValueError) as e:
            self._flownet_stats["send_errors"] += 1
            print(f"[SEND] Error: {e}", file=sys.stderr)
            return False

    def _process_packet(self, pkt: Any) -> None:
        """Process one captured packet."""
        if not pkt.haslayer(IP):
            return

        ip = pkt[IP]
        src_ip = ip.src
        dst_ip = ip.dst
        proto = "other"
        src_port = 0
        dst_port = 0
        length = len(pkt)
        dns_query = None

        if pkt.haslayer(TCP):
            proto = "tcp"
            src_port = pkt[TCP].sport
            dst_port = pkt[TCP].dport
        elif pkt.haslayer(UDP):
            proto = "udp"
            src_port = pkt[UDP].sport
            dst_port = pkt[UDP].dport

        # DNS query extraction
        if pkt.haslayer(DNS) and pkt[DNS].qd:
            dns_query = pkt[DNS].qd.qname.decode("utf-8", errors="replace")

        ts = float(pkt.time)
        self._aggregator.add_packet(
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=src_port,
            dst_port=dst_port,
            proto=proto,
            length=length,
            ts=ts,
            dns_query=dns_query,
        )
        self._flownet_stats["packets_captured"] += 1

    def _send_loop(self) -> None:
        """Periodically flush aggregated flows and send to AEGIS."""
        while self._running:
            time.sleep(FLUSH_INTERVAL)
            flows = self._aggregator.flush()
            if flows:
                self._send_flows(flows)
                print(
                    f"[FLOW] Sent {len(flows)} flows | "
                    f"Total: {self._flownet_stats['flows_sent']} | "
                    f"Packets: {self._flownet_stats['packets_captured']} | "
                    f"Errors: {self._flownet_stats['send_errors']}"
                )

    def run(self) -> None:
        """Start the capture service."""
        if not HAS_SCAPY:
            print(
                "[FATAL] scapy is not installed. Install with: pip install scapy", file=sys.stderr
            )
            sys.exit(1)

        print("=" * 60)
        print("  AEGIS Network Capture Service")
        print("=" * 60)
        print(f"  API:        {API_BASE}")
        print(f"  Interface:  {INTERFACE}")
        print(f"  Interval:   {FLUSH_INTERVAL}s")
        print(f"  Filter:     {FILTER_EXPR or '(none)'}")
        print("=" * 60)

        # Test auth
        if not self._auth():
            print("[FATAL] Cannot authenticate with AEGIS backend", file=sys.stderr)
            sys.exit(1)

        self._running = True

        # Start send thread
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True, name="sender")
        self._send_thread.start()

        # Start capture on main thread
        print(f"[CAPTURE] Starting packet capture on {INTERFACE}...")
        try:
            sniff(
                iface=INTERFACE if INTERFACE != "any" else None,
                prn=self._process_packet,
                filter=FILTER_EXPR or None,
                store=False,
                stop_filter=lambda _: not self._running,
            )
        except PermissionError:
            print(
                "[FATAL] Permission denied. Run with --cap-add NET_ADMIN or --privileged",
                file=sys.stderr,
            )
            sys.exit(1)
        except Exception as e:  # noqa: BLE001 - any sniff failure is fatal; report and exit
            print(f"[FATAL] Capture error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            # Final flush
            flows = self._aggregator.flush()
            if flows:
                self._send_flows(flows)
            print(
                f"\n[DONE] Captured {self._flownet_stats['packets_captured']} packets, "
                f"sent {self._flownet_stats['flows_sent']} flows"
            )


def main() -> None:
    service = CaptureService()
    service.run()


if __name__ == "__main__":
    main()
