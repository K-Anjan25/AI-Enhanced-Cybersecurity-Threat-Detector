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
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.core.logging import get_logger
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
)

__all__ = ["RuleDetector", "FlowWindow"]

_LOG = get_logger("aegis.rule_detector")

# Ports commonly used for authentication
AUTH_PORTS = frozenset({22, 23, 3389, 5900, 5985, 5986, 8022, 9090})

# Ports for lateral movement
LATERAL_PORTS = frozenset({445, 135, 139, 3389, 5985, 5986, 8443, 9090})

# Known C2 beacon intervals (seconds) — checked with tolerance
BEACON_INTERVALS = (60, 120, 300, 600, 900, 1800, 3600)

# DNS port
DNS_PORT = 53

# Thresholds. These are the documented detection bounds (architecture.md §7.2);
# there is deliberately no environment override that quietly lowers them, because
# a knob that turns normal traffic into alerts is how a demo earns a screenshot
# and how a threshold drifts without anybody deciding it.
PORT_SCAN_THRESHOLD = 15  # unique dst_ports from one src in window
BEACON_MIN_FLOWS = 5  # minimum flows to suspect beaconing
BEACON_INTERVAL_TOLERANCE = 0.15  # 15% tolerance on interval
EXFIL_BYTE_THRESHOLD = 50_000_000  # outbound bytes
BRUTE_FORCE_THRESHOLD = 10  # failed connections to auth ports
DNS_TUNNEL_SIZE = 512  # bytes — large DNS queries are suspicious
LATERAL_THRESHOLD = 5  # connections to lateral ports


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
        """Add one flow and widen the window's bounds to contain it."""
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
    """Deterministic entity id from IP string.

    The hash is a keyed lookup into an id space, not a security control, so
    MD5 is marked ``usedforsecurity=False``: the value is stable across runs
    and processes, which is what the correlator's case ids rely on.
    """
    digest = hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()
    return int(digest[:8], 16)


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
                        *(("Matches known C2 interval pattern",) if matches_known else ()),
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
                    (
                        f"Largest flow: {top_flows[0].orig_bytes:,} bytes to {top_flows[0].dst_ip}"
                        if top_flows
                        else ""
                    ),
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
            f
            for f in auth_flows
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
                    f"Success rate: {_success_rate(len(auth_flows), len(failed)):.1f}%",
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
            f
            for f in window.flows
            if f.dst_port in LATERAL_PORTS and _is_internal(f.dst_ip) and _is_internal(f.src_ip)
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


def _success_rate(total: int, failed: int) -> float:
    """Percentage of auth flows that did not fail, guarding against an empty set."""
    return (total - failed) / max(total, 1) * 100


def _is_internal(ip: str) -> bool:
    """Check if an IP is in a private range."""
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        a, b = int(parts[0]), int(parts[1])
        return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168) or a == 127
    except (ValueError, IndexError):
        return False


class _Scanner(Protocol):
    """One family detector: a window in, at most one hit out."""

    def scan(self, window: FlowWindow) -> RuleHit | None:
        """Return the family's hit for this window, if any."""
        ...


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
        """Build every family detector over one alert store and one correlator."""
        self._alerts = alert_store
        self._lookback = timedelta(minutes=lookback_minutes)
        self._entity_registry = entity_registry
        self._detectors: list[_Scanner] = [
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
        """Running totals of detections and alerts."""
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
                records.append(_flow_record(f))
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
                            created_at=(
                                case.first_seen if isinstance(case.first_seen, datetime) else now
                            ),
                        )
                        self._total_alerts += 1
                        new_alerts.append(
                            {
                                "family": case.family,
                                "severity": case.severity.value,
                                "score": float(case.score),
                                "entity_id": case.entity_id,
                                "action": outcome.action.value,
                                "explanation": list(hit.reasons),
                            }
                        )
                    except Exception as exc:  # noqa: BLE001 - a store error must not stop the cycle
                        _LOG.warning("rule_detector_store_failed", error=str(exc))

        self._last_run = now
        return new_alerts


@dataclass(slots=True)
class _RuleFusion:
    """A fused score that satisfies :class:`FusedScoreLike` structurally."""

    score: float
    partial_evidence: bool


def _simple_fuse(flow_score: float | None, log_score: float | None) -> FusedScoreLike:
    """Fuse for rule detections: the flow score is the only modality that exists.

    Rule hits carry no log modality, so the score is the flow score as-is and
    ``partial_evidence`` is False. Refuses to invent a score when neither side is set.
    """
    if flow_score is None and log_score is None:
        msg = "rule detector produced no score to fuse"
        raise ValueError(msg)
    value = flow_score if flow_score is not None else log_score
    if value is None:  # unreachable after the guard above; typed, not asserted
        msg = "rule detector produced no score to fuse"
        raise ValueError(msg)
    return _RuleFusion(score=float(value), partial_evidence=False)


def _flow_record(f: Mapping[str, object]) -> FlowRecord:
    """Build one :class:`FlowRecord` from a loosely typed flow dict.

    Raises:
        ValueError: if a numeric field cannot be parsed.
        TypeError: if a numeric field has an unsupported type.
    """
    duration = f.get("duration")
    return FlowRecord(
        ts=float(_num(f.get("ts"))),
        src_ip=str(f.get("src_ip", "")),
        dst_ip=str(f.get("dst_ip", "")),
        src_port=int(_num(f.get("src_port"))),
        dst_port=int(_num(f.get("dst_port"))),
        proto=str(f.get("proto", "tcp")),
        service=_opt_str(f.get("service")),
        duration=None if duration is None else float(_num(duration)),
        orig_bytes=int(_num(f.get("orig_bytes"))),
        resp_bytes=int(_num(f.get("resp_bytes"))),
        conn_state=_opt_str(f.get("conn_state")),
        source=_opt_str(f.get("source")),
    )


def _num(value: object) -> float:
    """Coerce a stored numeric field; a missing field reads as zero."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        raise TypeError("boolean is not a numeric flow field")
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"unsupported flow field type {type(value).__name__}")


def _opt_str(value: object) -> str | None:
    """Return a string field, or None when it is absent."""
    return None if value is None else str(value)


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
