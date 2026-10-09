"""Kafka consumer that reads flows, scores them via ML service, creates alerts.

This is the missing piece that connects:
  ingest → Kafka → ML scoring → correlator → alerts
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import urllib.request
import urllib.error

__all__ = ["MlScoringConsumer"]


class MlScoringConsumer:
    """Reads flow records from Kafka, sends to ML service for scoring,
    and feeds scores back into the alert correlator.

    Runs as a background thread in the backend process.
    """

    def __init__(
        self,
        ml_service_url: str,
        alert_callback: callable,
        *,
        poll_interval: float = 5.0,
        window_size: int = 50,
    ) -> None:
        self._ml_url = ml_service_url.rstrip("/")
        self._alert_callback = alert_callback
        self._poll_interval = poll_interval
        self._window_size = window_size
        self._running = False
        self._thread: threading.Thread | None = None
        self._flow_buffer: list[dict[str, Any]] = []
        self._stats = {
            "windows_scored": 0,
            "scoring_errors": 0,
            "alerts_created": 0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return {**self._stats, "buffer_size": len(self._flow_buffer)}

    def feed(self, flows: list[dict[str, Any]]) -> None:
        """Add flows to the buffer for scoring."""
        self._flow_buffer.extend(flows)
        # Process complete windows
        while len(self._flow_buffer) >= self._window_size:
            window = self._flow_buffer[:self._window_size]
            self._flow_buffer = self._flow_buffer[self._window_size:]
            self._score_window(window)

    def _score_window(self, window: list[dict[str, Any]]) -> None:
        """Send a window to the ML service and handle the score."""
        try:
            body = json.dumps({"flows": window}).encode()
            req = urllib.request.Request(
                f"{self._ml_url}/score",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())

            score = result.get("score", 0.0)
            explanations = result.get("explanations", [])
            model_id = result.get("model_id", "unknown")

            if score > 0.3:  # Threshold for creating an alert
                self._alert_callback(
                    score=score,
                    explanations=explanations,
                    model_id=model_id,
                    flows=window,
                )
                self._stats["alerts_created"] += 1

            self._stats["windows_scored"] += 1

        except Exception as e:
            self._stats["scoring_errors"] += 1

    def start(self) -> None:
        """Start the consumer thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="ml-scoring-consumer",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the consumer thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """Main loop: process remaining flows periodically."""
        while self._running:
            time.sleep(self._poll_interval)
            # Process any remaining flows
            if self._flow_buffer:
                window = self._flow_buffer[:self._window_size]
                self._flow_buffer = self._flow_buffer[self._window_size:]
                if window:
                    self._score_window(window)