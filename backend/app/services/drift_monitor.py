"""Background drift monitoring: computes PSI from recent flows and publishes gauges.

This implements T-421: the PSI gauge producer that makes aegis_drift_psi{feature}
appear in the /metrics scrape so the DriftPage can draw bars.
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections import Counter
from typing import Any

import urllib.request
import urllib.error

from app.observability.metrics import observe_drift_psi

__all__ = ["DriftMonitor"]

# PSI thresholds
PSI_STABLE = 0.10
PSI_MODERATE = 0.25

# Feature baselines (from typical network traffic)
FEATURE_BASELINES: dict[str, dict[str, float]] = {
    "dst_port": {
        "80": 0.25, "443": 0.35, "53": 0.15, "22": 0.05,
        "3389": 0.02, "25": 0.03, "993": 0.03, "587": 0.02,
        "other": 0.10,
    },
    "proto": {"tcp": 0.70, "udp": 0.25, "icmp": 0.05},
    "duration_bucket": {
        "0-1s": 0.40, "1-10s": 0.25, "10-60s": 0.15,
        "1-5m": 0.10, "5m+": 0.10,
    },
}


def _bucket_port(port: int) -> str:
    common = {80: "80", 443: "443", 53: "53", 22: "22", 3389: "3389",
              25: "25", 993: "993", 587: "587"}
    return common.get(port, "other")


def _bucket_duration(duration: float | None) -> str:
    if duration is None:
        return "0-1s"
    if duration < 1:
        return "0-1s"
    if duration < 10:
        return "1-10s"
    if duration < 60:
        return "10-60s"
    if duration < 300:
        return "1-5m"
    return "5m+"


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
        elif feature == "duration_bucket":
            _bucket_duration(f.get("duration"))
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
    """Background task that computes PSI from buffered flows and publishes gauges.

    Runs every `interval` seconds, reads flows from the detection engine's
    buffer, computes PSI for each feature, and publishes to prometheus_client.
    """

    def __init__(
        self,
        flow_buffer: list[dict[str, Any]] | None = None,
        *,
        interval: float = 60.0,
        ml_service_url: str | None = None,
    ) -> None:
        self._interval = interval
        self._ml_url = ml_service_url
        self._running = False
        self._thread: threading.Thread | None = None
        self._flow_buffer_ref = flow_buffer
        self._lock = threading.Lock()
        self._last_psi: dict[str, float] = {}

    @property
    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "last_psi": dict(self._last_psi),
                "interval": self._interval,
            }

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="drift-monitor"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while self._running:
            time.sleep(self._interval)
            try:
                self._compute_and_publish()
            except Exception:
                pass

    def _compute_and_publish(self) -> None:
        # Try ML service first
        if self._ml_url:
            try:
                self._publish_from_ml_service()
                return
            except Exception:
                pass

        # Fallback: compute locally from buffered flows
        self._compute_local()

    def _publish_from_ml_service(self) -> None:
        """Get drift data from ML service /drift endpoint."""
        # Get recent flows from the flow store or buffer
        # For now, send empty and let ML service use its own data
        body = json.dumps({"flows": []}).encode()
        req = urllib.request.Request(
            f"{self._ml_url}/drift",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())

        for feature_result in result.get("features", []):
            feature = feature_result.get("feature", "")
            psi = feature_result.get("psi", 0.0)
            if feature:
                observe_drift_psi(feature, psi)
                with self._lock:
                    self._last_psi[feature] = psi

    def _compute_local(self) -> None:
        """Compute PSI locally from recent flows."""
        if self._flow_buffer_ref is None or not self._flow_buffer_ref:
            return

        # Take a snapshot
        with self._lock:
            flows = list(self._flow_buffer_ref[-1000:])  # Last 1000 flows

        if len(flows) < 10:
            return

        for feature, baseline in FEATURE_BASELINES.items():
            observed = _compute_distribution(flows, feature)
            if not observed:
                continue
            psi = _compute_psi(baseline, observed)
            observe_drift_psi(feature, psi)
            with self._lock:
                self._last_psi[feature] = psi