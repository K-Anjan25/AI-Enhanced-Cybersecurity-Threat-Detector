"""Background rule detection task: reads buffered flows, creates alerts.

This runs inside the backend process as a background task. It maintains
a buffer of recently ingested flows and runs the rule-based detector
on them periodically to generate alerts.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.services.rule_detector import RuleDetector

if TYPE_CHECKING:
    from app.services.alert_store import AlertStore

__all__ = ["DetectionEngine"]

_LOG = get_logger("aegis.detection_engine")


class DetectionEngine:
    """Manages the rule-based detection loop.

    Call ``feed()`` from the ingest path with each accepted batch.
    Call ``start()`` to begin periodic scoring. The engine runs in a
    daemon thread and processes buffered flows every ``interval`` seconds.
    """

    def __init__(
        self,
        alert_store: AlertStore,
        *,
        interval: float = 15.0,
        max_buffer: int = 10_000,
    ) -> None:
        """Bind the detector to an alert store and the scoring cadence."""
        self._detector = RuleDetector(alert_store)
        self._interval = interval
        self._max_buffer = max_buffer
        self._buffer: deque[dict[str, object]] = deque(maxlen=max_buffer)
        self._lock = threading.Lock()
        self._running = False
        # An event, not a bare sleep, so stop() wakes the loop immediately:
        # a thread parked in time.sleep(interval) would hold shutdown for the
        # whole join timeout on every application instance (every test builds one).
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_alerts: list[dict[str, object]] = []
        self._cycle_count = 0

    @property
    def stats(self) -> dict[str, object]:
        """Current engine stats."""
        with self._lock:
            return {
                **self._detector.stats,
                "buffer_size": len(self._buffer),
                "cycle_count": self._cycle_count,
                "last_cycle_alerts": len(self._last_alerts),
                "running": self._running,
            }

    def feed(self, records: list[dict[str, object]]) -> None:
        """Add flow records to the detection buffer.

        Call this from the ingest path with each accepted batch.
        Each record should be a dict with flow fields.
        """
        with self._lock:
            for record in records:
                self._buffer.append(record)

    def start(self) -> None:
        """Start the background detection loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name="rule-detector",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background detection loop."""
        self._running = False
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        """Main detection loop."""
        while self._running:
            if self._wake.wait(self._interval):
                break
            try:
                self._run_cycle()
            except Exception as exc:  # noqa: BLE001 - one bad cycle must not kill the loop
                _LOG.warning("detection_cycle_failed", error=str(exc))

    def _run_cycle(self) -> None:
        """Run one detection cycle."""
        # Drain the buffer
        with self._lock:
            if not self._buffer:
                return
            flows = list(self._buffer)
            self._buffer.clear()

        # Run detectors
        new_alerts = self._detector.process_flows(flows)

        with self._lock:
            self._last_alerts = new_alerts
            self._cycle_count += 1
