"""Bounded, expiring health state for Docker-managed packet-capture sensors.

Heartbeats are operational liveness signals, not traffic observations. The registry
keeps only the latest timestamp per configured sensor; it does not retain packet or
alert data and correctly reports an unreported sensor fleet as ``unknown``.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas.capture import CaptureEngine

DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 45
MAX_CAPTURE_SENSORS = 128


class CaptureHealthCapacityError(RuntimeError):
    """Raised when only live sensors remain and the registry is at its hard cap."""


@dataclass(frozen=True)
class _Heartbeat:
    """One sensor's latest server-received heartbeat."""

    sensor_id: str
    engines: tuple[CaptureEngine, ...]
    last_seen_at: datetime
    received_at: float


class CaptureHealthRegistry:
    """Thread-safe latest-only registry whose health expires when reports stop."""

    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
        max_sensors: int = MAX_CAPTURE_SENSORS,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create an empty, sensor-count-bounded registry with injectable clocks."""
        if timeout_seconds < 1:
            msg = "capture heartbeat timeout must be at least one second"
            raise ValueError(msg)
        if max_sensors < 1:
            msg = "capture health registry must allow at least one sensor"
            raise ValueError(msg)
        self.timeout_seconds = timeout_seconds
        self.max_sensors = max_sensors
        self._now = now or (lambda: datetime.now(UTC))
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._sensors: dict[str, _Heartbeat] = {}

    def record(self, sensor_id: str, engines: Sequence[CaptureEngine]) -> dict[str, object]:
        """Record the server receipt time and return the current sensor state."""
        heartbeat = _Heartbeat(
            sensor_id=sensor_id,
            engines=tuple(engines),
            last_seen_at=self._now().astimezone(UTC),
            received_at=self._monotonic(),
        )
        with self._lock:
            if sensor_id not in self._sensors and len(self._sensors) >= self.max_sensors:
                stale = [
                    item
                    for item in self._sensors.values()
                    if heartbeat.received_at - item.received_at > self.timeout_seconds
                ]
                if not stale:
                    raise CaptureHealthCapacityError(
                        "capture health registry is full of live sensors"
                    )
                oldest_stale = min(stale, key=lambda item: item.received_at)
                del self._sensors[oldest_stale.sensor_id]
            self._sensors[sensor_id] = heartbeat
            return self._sensor_status(heartbeat, heartbeat.received_at)

    def snapshot(self) -> dict[str, object]:
        """Return the current fleet state; missing and expired reports are explicit."""
        now = self._monotonic()
        with self._lock:
            sensors = [self._sensor_status(item, now) for item in self._sensors.values()]
        sensors.sort(key=lambda item: str(item["sensor_id"]))
        if not sensors:
            status = "unknown"
        elif any(item["status"] == "stale" for item in sensors):
            status = "stale"
        else:
            status = "healthy"
        return {
            "status": status,
            "heartbeat_timeout_seconds": self.timeout_seconds,
            "sensors": sensors,
        }

    def _sensor_status(self, heartbeat: _Heartbeat, now: float) -> dict[str, object]:
        """Compute status from elapsed monotonic time, never a client clock."""
        age_seconds = max(0.0, now - heartbeat.received_at)
        return {
            "sensor_id": heartbeat.sensor_id,
            "engines": list(heartbeat.engines),
            "status": "healthy" if age_seconds <= self.timeout_seconds else "stale",
            "last_seen_at": heartbeat.last_seen_at,
            "age_seconds": age_seconds,
        }
