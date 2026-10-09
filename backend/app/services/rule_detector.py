"""Rule-based threat detector: flow patterns → scores → alerts (no ML needed).

This is a standalone scoring engine that detects common attack patterns
from flow data using heuristics. It runs as a background task inside the
backend process, reading from the flow read model and writing alerts
directly to the alert store.

Detected families:
  - port_scan: one source contacting many destination ports
  - beacon: regular-interval small flows to the same destination (C2)
  - exfiltration: large outbound data transfers
  - brute_force: repeated connections to auth ports (22, 3389, etc.)
  - dns_tunnel: unusually large DNS queries
  - lateral_movement: internal-to-internal on sensitive ports

Each family maps to a score in [0, 1] and an explanation.
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Mapping

from app.db.models import AlertStatus, Severity
from app.services.alert_store import AlertStore
from app.services.correlator import (
    Action,
    AlertCase,
    Correlator,
    Detection,
    Explanation,
    FusedScoreLike,
    InMemoryCaseStore,
    Modality,
    SeverityBands,
    severity_for,
)

__all__ = ["RuleDetector", "FlowWindow"]

# Ports commonly used for authentication
AUTH_PORTS = frozenset({22, 23, 3389, 5900, 5985, 5986, 8022, 9090})

# Ports for lateral movement
LATERAL_PORTS = frozenset({445, 135, 139, 3389, 5985, 5986, 8443, 9090})

# Known C2 beacon intervals (seconds) — checked with tolerance
BEACON_INTERVALS = (60, 120, 300, 600, 900, 1800, 3600)

# DNS port
DNS_PORT = 53

# Thresholds — use AEGIS_DEMO_THRESHOLD_DIVISOR to lower all thresholds
# (e.g. set to 5 in development so normal traffic triggers alerts for demo)
import os
_threshold_divisor = int(os.environ.get("AEGIS_DEMO_THRESHOLD_DIVISOR", "1"))

PORT_SCAN_THRESHOLD = max(3, 15 // _threshold_divisor)     # unique dst_ports from one src in window
BEACON_MIN_FLOWS = max(2, 5 // _threshold_divisor)         # minimum flows to suspect beaconing
BEACON_INTERVAL_TOLERANCE = 0.15                            # 15% tolerance on interval
EXFIL_BYTE_THRESHOLD = max(1_000_000, 50_000_000 // _threshold_divisor)  # outbound bytes
BRUTE_FORCE_THRESHOLD = max(2, 10 // _threshold_divisor)   # failed connections to auth ports
DNS_TUNNEL_SIZE = 512                                       # bytes — large DNS queries are suspicious
LATERAL_THRESHOLD = max(2, 5 // _threshold_divisor)        # connections to lateral ports


@dataclass(frozen=True, slots=True)
class FlowRecord:
    """Minimal flow record for detection."""
    ts: float
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    proto: str
    service: str | None = None
    duration: float | None = None
    orig_bytes: int = 0
    resp_bytes: int = 0
    conn_state: str | None = None
    source: str | None = None


@dataclass(slots=True)
class FlowWindow:
    """A time-bounded collection of flows for one source IP."""
    key: str
    flows: list[FlowRecord] = field(default_factory=list)
    start: datetime | None = None
    end: datetime | None = None

    def add(self, flow: FlowRecord) -> None:
        self.flows.append(flow)
        ts = datetime.fromtimestamp(flow.ts, tz=UTC)
        if self.start is None or ts < self.start:
            self.start = ts
        if self.end is None or ts > self.end:
            self.end = ts


@dataclass(frozen=True, slots=True)
class RuleHit:
    """One detection from a rule."""
    family: str
    score: float
    reasons: tuple[str, ...]
    entity_key: str


def _entity_id(key: str) -> int:
    """Deterministic entity id from IP string."""
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


class PortScanDetector:
    """Detects port scanning: one source hitting many destination ports."""

    def scan(self, window: FlowWindow) -> RuleHit | None:
        if not window.flows:
            return None
        dst_ports = {f.dst_port for f in window.flows}
        if len(dst_ports) >= PORT_SCAN_THRESHOLD:
            score = min(0.5 + (len(dst_ports) - PORT_SCAN_THRESHOLD) * 0.02, 0.99)
            top_ports = sorted(dst_ports)[:10]
            return RuleHit(
                family="port_scan",
                score=score,
                reasons=(
                    f"{len(dst_ports)} unique destination ports from {window.key}",
                    f"Ports include: {', '.join(str(p) for p in top_ports)}",
                    f"Total flows in window: {len(window.flows)}",
                ),
                entity_key=window.key,
            )
        return None


class BeaconDetector:
    """Detects C2 beaconing: regular-interval connections to same destination."""

    def scan(self, window: FlowWindow) -> RuleHit | None:
        if len(window.flows) < BEACON_MIN_FLOWS:
            return None

        # Group by destination
        by_dest: dict[str, list[float]] = defaultdict(list)
        for f in window.flows:
            by_dest[f"{f.dst_ip}:{f.dst_port}"].append(f.ts)

        for dest, timestamps in by_dest.items():
            if len(timestamps) < BEACON_MIN_FLOWS:
                continue
            timestamps.sort()
            intervals = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
            if not intervals:
                continue
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval < 5:  # Too frequent, likely normal
                continue
            # Check consistency
            deviations = [abs(iv - avg_interval) / avg_interval for iv in intervals]
            avg_deviation = sum(deviations) / len(deviations)
            if avg_deviation < BEACON_INTERVAL_TOLERANCE:
                score = min(0.6 + (1 - avg_deviation) * 0.3, 0.99)
                # Check against known beacon intervals
                matches_known = any(
                    abs(avg_interval - known) / known < 0.1 for known in BEACON_INTERVALS
                )
                if matches_known:
                    score = min(score + 0.1, 0.99)
                return RuleHit(
                    family="beacon",
                    score=score,
                    reasons=(
                        f"Regular beacon to {dest} every {avg_interval:.1f}s",
                        f"Jitter: {avg_deviation * 100:.1f}% (suspiciously low)",
                        f"{len(timestamps)} beacon signals detected",
                        *(
                            ("Matches known C2 interval pattern",)
                            if matches_known
                            else ()
                        ),
                    ),
                    entity_key=window.key,
                )
        return None


class ExfiltrationDetector:
    """Detects data exfiltration: large outbound transfers."""

    def scan(self, window: FlowWindow) -> RuleHit | None:
        if not window.flows:
            return None
        total_outbound = sum(f.orig_bytes for f in window.flows)
        if total_outbound >= EXFIL_BYTE_THRESHOLD:
            score = min(0.5 + (total_outbound - EXFIL_BYTE_THRESHOLD) / 200_000_000, 0.99)
            top_flows = sorted(window.flows, key=lambda f: f.orig_bytes, reverse=True)[:5]
            return RuleHit(
                family="exfiltration",
                score=score,
                reasons=(
                    f"{total_outbound:,} bytes outbound from {window.key}",
                    f"Largest flow: {top_flows[0].orig_bytes:,} bytes to {top_flows[0].dst_ip}"
                    if top_flows
                    else "",
                    f"{len(window.flows)} flows in window",
                ),
                entity_key=window.key,
            )
        return None


class BruteForceDetector:
    """Detects brute force: repeated connections to auth ports."""

    def scan(self, window: FlowWindow) -> RuleHit | None:
        if not window.flows:
            return None
        auth_flows = [f for f in window.flows if f.dst_port in AUTH_PORTS]
        failed = [
            f for f in auth_flows
            if f.conn_state in ("REJ", "RSTO", "RSTR", "S0", "SH")
            or (f.duration is not None and f.duration < 0.5 and f.resp_bytes < 100)
        ]
        if len(failed) >= BRUTE_FORCE_THRESHOLD:
            score = min(0.5 + (len(failed) - BRUTE_FORCE_THRESHOLD) * 0.02, 0.99)
            targets = Counter(f.dst_port for f in failed).most_common(3)
            return RuleHit(
                family="brute_force",
                score=score,
                reasons=(
                    f"{len(failed)} failed auth attempts from {window.key}",
                    f"Target ports: {', '.join(f'{p} ({c}x)' for p, c in targets)}",
                    f"Success rate: {(len(auth_flows) - len(failed)) / max(len(auth_flows), 1) * 100:.1f}%",
                ),
                entity_key=window.key,
            )
        return None


class DnsTunnelDetector:
    """Detects DNS tunneling: unusually large DNS queries."""

    def scan(self, window: FlowWindow) -> RuleHit | None:
        if not window.flows:
            return None
        dns_flows = [f for f in window.flows if f.dst_port == DNS_PORT or f.service == "dns"]
        large_dns = [f for f in dns_flows if f.orig_bytes > DNS_TUNNEL_SIZE]
        if len(large_dns) >= 3:
            avg_size = sum(f.orig_bytes for f in large_dns) / len(large_dns)
            score = min(0.4 + (avg_size - DNS_TUNNEL_SIZE) / 5000, 0.95)
            return RuleHit(
                family="dns_tunnel",
                score=score,
                reasons=(
                    f"{len(large_dns)} large DNS queries from {window.key}",
                    f"Average query size: {avg_size:.0f} bytes (normal: <100)",
                    f"Max query size: {max(f.orig_bytes for f in large_dns):,} bytes",
                ),
                entity_key=window.key,
            )
        return None


class LateralMovementDetector:
    """Detects lateral movement: internal-to-internal on sensitive ports."""

    def scan(self, window: FlowWindow) -> RuleHit | None:
        if not window.flows:
            return None
        lateral = [
            f for f in window.flows
            if f.dst_port in LATERAL_PORTS
            and _is_internal(f.dst_ip)
            and _is_internal(f.src_ip)
        ]
        if len(lateral) >= LATERAL_THRESHOLD:
            targets = Counter(f.dst_ip for f in lateral).most_common(5)
            score = min(0.5 + (len(lateral) - LATERAL_THRESHOLD) * 0.03, 0.95)
            return RuleHit(
                family="lateral_movement",
                score=score,
                reasons=(
                    f"{len(lateral)} lateral connections from {window.key}",
                    f"Internal targets: {', '.join(f'{ip} ({c}x)' for ip, c in targets)}",
                    f"Ports: {', '.join(str(p) for p in sorted({f.dst_port for f in lateral}))}",
                ),
                entity_key=window.key,
            )
        return None


def _is_internal(ip: str) -> bool:
    """Check if an IP is in a private range."""
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        a, b = int(parts[0]), int(parts[1])
        return (
            a == 10
            or (a == 172 and 16 <= b <= 31)
            or (a == 192 and b == 168)
            or a == 127
        )
    except (ValueError, IndexError):
        return False


class RuleDetector:
    """Orchestrates all rule-based detectors on a set of flows.

    Runs periodically inside the backend process. Reads flows from the
    flow read model, applies all detectors, and writes alerts to the
    alert store.
    """

    def __init__(
        self,
        alert_store: AlertStore,
        *,
        lookback_minutes: int = 10,
        entity_registry: object | None = None,
    ) -> None:
        self._alerts = alert_store
        self._lookback = timedelta(minutes=lookback_minutes)
        self._entity_registry = entity_registry
        self._detectors = [
            PortScanDetector(),
            BeaconDetector(),
            ExfiltrationDetector(),
            BruteForceDetector(),
            DnsTunnelDetector(),
            LateralMovementDetector(),
        ]
        self._last_run: datetime | None = None
        self._total_detections = 0
        self._total_alerts = 0
        # Correlator for deduplication
        self._correlator = Correlator(InMemoryCaseStore(), _simple_fuse)

    @property
    def stats(self) -> dict[str, int]:
        return {
            "total_detections": self._total_detections,
            "total_alerts": self._total_alerts,
        }

    def process_flows(self, flows: list[dict[str, object]]) -> list[dict[str, object]]:
        """Process a batch of flow dicts and return any new alerts created.

        Each flow dict should have: ts, src_ip, dst_ip, src_port, dst_port,
        proto, service, duration, orig_bytes, resp_bytes, conn_state.
        """
        if not flows:
            return []

        # Convert to FlowRecord objects
        records: list[FlowRecord] = []
        for f in flows:
            try:
                records.append(FlowRecord(
                    ts=float(f.get("ts", 0)),
                    src_ip=str(f.get("src_ip", "")),
                    dst_ip=str(f.get("dst_ip", "")),
                    src_port=int(f.get("src_port", 0)),
                    dst_port=int(f.get("dst_port", 0)),
                    proto=str(f.get("proto", "tcp")),
                    service=f.get("service"),
                    duration=f.get("duration"),
                    orig_bytes=int(f.get("orig_bytes", 0)),
                    resp_bytes=int(f.get("resp_bytes", 0)),
                    conn_state=f.get("conn_state"),
                    source=f.get("source"),
                ))
            except (ValueError, TypeError):
                continue

        # Build windows by source IP
        windows: dict[str, FlowWindow] = {}
        for r in records:
            key = r.src_ip
            if key not in windows:
                windows[key] = FlowWindow(key=key)
            windows[key].add(r)

        # Run all detectors on each window
        new_alerts: list[dict[str, object]] = []
        now = datetime.now(UTC)

        for window in windows.values():
            for detector in self._detectors:
                hit = detector.scan(window)
                if hit is None:
                    continue
                self._total_detections += 1

                # Create detection for the correlator
                entity_id = _entity_id(hit.entity_key)
                detection = Detection(
                    entity_id=entity_id,
                    family=hit.family,
                    modality=Modality.flow,
                    score=hit.score,
                    at=window.end or now,
                    evidence_id=f"rule:{hit.entity_key}:{hit.family}:{int(now.timestamp())}",
                    model_id="rule-detector-v1",
                    explanation=Explanation(reasons=hit.reasons),
                )

                # Correlate (dedup, group, absorb)
                outcome = self._correlator.ingest(detection)

                if outcome.action in (Action.created, Action.grouped, Action.absorbed):
                    case = outcome.case
                    row = _alert_row_from_case(case)
                    # Store in alert store
                    try:
                        self._alerts.save(
                            case.id,
                            row,
                            created_at=case.first_seen if isinstance(case.first_seen, datetime) else now,
                        )
                        self._total_alerts += 1
                        new_alerts.append({
                            "family": case.family,
                            "severity": case.severity.value,
                            "score": float(case.score),
                            "entity_id": case.entity_id,
                            "action": outcome.action.value,
                            "explanation": list(hit.reasons),
                        })
                    except Exception:
                        pass  # Don't crash the detector on store errors

        self._last_run = now
        return new_alerts


def _simple_fuse(scores: Mapping[str, float] | float | None, *args: object) -> FusedScoreLike:
    """Simple fusion rule: just use the flow score directly."""
    from app.services.correlator import FusedScoreLike

    if isinstance(scores, dict):
        value = max(scores.values()) if scores else 0.0
    elif isinstance(scores, (int, float)):
        value = float(scores)
    else:
        value = 0.0
    return FusedScoreLike(score=value, partial_evidence=False)


def _alert_row_from_case(case: AlertCase) -> dict[str, object]:
    """Convert a case to alert row values."""
    from app.services.correlator import Modality

    best = case.best_by_modality()
    return {
        "entity_id": case.entity_id,
        "family": case.family,
        "severity": case.severity.value,
        "score": float(case.score),
        "model_flow_id": best[Modality.flow].model_id if Modality.flow in best else None,
        "model_log_id": best[Modality.log].model_id if Modality.log in best else None,
        "window_ref": {
            "store": "rule_detector",
            "id": case.first_evidence_id,
            "grouped": case.grouped,
            "evidence": [
                {
                    "id": occ.evidence_id,
                    "modality": occ.modality.value,
                    "score": occ.score,
                    "at": occ.at.isoformat(),
                    "model": occ.model_id,
                }
                for occ in case.occurrences
            ],
        },
        "explanation": case.explanation_payload(),
        "status": case.status.value,
        "first_seen": case.first_seen,
        "last_seen": case.last_seen,
        "occurrence_count": case.occurrence_count,
    }