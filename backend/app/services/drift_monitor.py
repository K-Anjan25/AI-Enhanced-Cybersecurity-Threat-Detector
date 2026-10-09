"""Background drift monitoring: computes PSI from recent flows and publishes gauges."""

from __future__ import annotations

import logging
import math
import threading
from collections import Counter
from typing import Any

from app.observability.metrics import observe_drift_psi

logger = logging.getLogger(__name__)

__all__ = ["DriftMonitor"]

FEATURE_BASELINES: dict[str, dict[str, float]] = {
    "dst_port": {
        "80": 0.25,
        "443": 0.35,
        "53": 0.15,
        "22": 0.05,
        "3389": 0.02,
        "25": 0.03,
        "993": 0.03,
        "587": 0.02,
        "other": 0.10,
    },
    "proto": {"tcp": 0.70, "udp": 0.25, "icmp": 0.05},
}


def _bucket_port(port: int) -> str:
    common = {
        80: "80",
        443: "443",
        53: "53",
        22: "22",
        3389: "3389",
        25: "25",
        993: "993",
        587: "587",
    }
    return common.get(port, "other")


def _compute_distribution(flows: list[dict[str, Any]], feature: str) -> dict[str, float]:
    total = len(flows)
    if total == 0:
        return {}
    counter: Counter[str] = Counter()
    for f in flows:
        if feature == "dst_port":
            counter[_bucket_port(int(f.get("dst_port", 0)))] += 1
        elif feature == "proto":
            counter[str(f.get("proto", "tcp"))] += 1
    return {k: v / total for k, v in counter.items()}


def _compute_psi(expected: dict[str, float], observed: dict[str, float]) -> float:
    epsilon = 1e-6
    all_keys = set(expected.keys()) | set(observed.keys())
    psi = 0.0
    for key in all_keys:
        e = max(expected.get(key, 0), epsilon)
        o = max(observed.get(key, 0), epsilon)
        psi += (o - e) * math.log(o / e)
    return psi


class DriftMonitor:
    """Computes PSI from buffered flows and publishes aegis_drift_psi gauges."""

    def __init__(
        self,
        flow_buffer: list[dict[str, Any]] | None = None,
        *,
        interval: float = 60.0,
        ml_service_url: str | None = None,
    ) -> None:
        """Configure the publish cadence; no thread starts until ``start()``."""
        self._interval = interval
        self._ml_url = ml_service_url
        self._running = False
        # An event, not a bare sleep, so stop() wakes the loop immediately
        # instead of holding shutdown for the whole join timeout.
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._flow_buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._last_psi: dict[str, float] = {}
        self._compute_count = 0

    @property
    def stats(self) -> dict[str, Any]:
        """Current running state, last PSI values and cycle counters."""
        with self._lock:
            return {
                "running": self._running,
                "last_psi": dict(self._last_psi),
                "interval": self._interval,
                "compute_count": self._compute_count,
                "buffer_size": len(self._flow_buffer),
            }

    def add_flows(self, flows: list[dict[str, Any]]) -> None:
        """Buffer recent flows, keeping only the newest 5000."""
        with self._lock:
            self._flow_buffer.extend(flows)
            if len(self._flow_buffer) > 5000:
                self._flow_buffer = self._flow_buffer[-5000:]

    def start(self) -> None:
        """Start the daemon thread that publishes PSI on each interval."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="drift-monitor")
        self._thread.start()
        logger.info("drift_monitor_started interval=%s", self._interval)

    def stop(self) -> None:
        """Stop the loop and wait briefly for the thread to exit."""
        self._running = False
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        if self._wake.wait(3):
            return
        self._compute_and_publish()
        while self._running:
            if self._wake.wait(self._interval):
                break
            self._compute_and_publish()

    def _compute_and_publish(self) -> None:
        with self._lock:
            flows = list(self._flow_buffer[-2000:])

        if len(flows) < 2:
            logger.info("drift_monitor_insufficient_flows count=%d", len(flows))
            return

        for feature, baseline in FEATURE_BASELINES.items():
            observed = _compute_distribution(flows, feature)
            if not observed:
                continue
            psi = _compute_psi(baseline, observed)
            observe_drift_psi(feature, psi)
            with self._lock:
                self._last_psi[feature] = psi
            logger.info("drift_monitor_published feature=%s psi=%.4f", feature, psi)

        self._compute_count += 1
        logger.info("drift_monitor_cycle_done count=%d flows=%d", self._compute_count, len(flows))
