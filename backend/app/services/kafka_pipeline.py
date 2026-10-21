"""Composes the Kafka path: ingest publishes, a live loop consumes and scores (D-085).

When ``AEGIS_KAFKA_BOOTSTRAP_SERVERS`` is set, the flow path is:

    ingest route -> FlowPublisher -> KafkaBus (flows.raw, 6 partitions, acks=all)
                                         |
    LiveScoringLoop (thread) -> ScoringWorker -> MlWindowAdapter -> ML service
                                         |
                              DetectionSink -> Correlator -> AlertWriter -> alert store

The in-process ``DetectionEngine`` is not fed in this mode: scoring the same flows
twice would raise every alert twice. Scoring errors never commit an offset, so a
window whose score could not be obtained is retried, not reported as clean.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.messaging.kafka_bus import KafkaBus
from app.schemas.ingest import FlowRecordIn

if TYPE_CHECKING:
    from app.pipeline import Pipeline
    from app.services.rule_detector import MlWindowScorerLike

_LOG = get_logger("aegis.kafka_pipeline")

#: Flow alerts carry this family. The ML score does not name a family (the verdict
#: enum has none), so the family is the detection modality, not a guess.
FLOW_FAMILY = "flow_anomaly"


class ScoringUnavailable(RuntimeError):
    """The model gave no score for a window. The batch stays uncommitted and is retried."""


class MlWindowAdapter:
    """The ``ScoringWorker``'s ``Scorer`` over the ML service client."""

    def __init__(self, client: MlWindowScorerLike) -> None:
        """Wrap the client that calls ``POST /score/windows``."""
        self._client = client

    def score(self, window: Any) -> float:
        """Return the model's score for one window, or raise :class:`ScoringUnavailable`."""
        flows = [record.model_dump(mode="json") for record in window.records]
        result = self._client.score(flows)
        if result is None:
            msg = "the ML service gave no score for this window"
            raise ScoringUnavailable(msg)
        return float(result.score)


class FlowPublisher:
    """What the ingest route calls: hand accepted flows to the broker, then wait for acks."""

    def __init__(self, pipeline: Pipeline, bus: KafkaBus) -> None:
        """Bind to the pipeline's producer side and the bus it flushes."""
        self._pipeline = pipeline
        self._bus = bus

    def publish(self, records: Sequence[FlowRecordIn], *, traceparent: str | None = None) -> None:
        """Send the records and raise unless the broker acknowledged every one."""
        if not records:
            return
        self._pipeline.publish(records, traceparent=traceparent)
        self._bus.flush()


class LiveScoringLoop:
    """Drains every partition in a background thread and flushes partial windows when quiet."""

    def __init__(
        self,
        pipeline: Pipeline,
        *,
        poll_interval: float = 0.2,
        idle_flush_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Remember the pipeline. Nothing runs until :meth:`start`."""
        self._pipeline = pipeline
        self._poll_interval = poll_interval
        self._idle_flush = idle_flush_seconds
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_activity = clock()

    def start(self) -> None:
        """Start the consumer thread (idempotent)."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="kafka-scoring", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the thread and score what is left, so a clean shutdown loses no window."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        try:
            self._pipeline.worker.flush()
        except Exception as exc:  # noqa: BLE001 - shutdown must not raise
            _LOG.warning("kafka_scoring_final_flush_failed", error=str(exc))

    def run_once(self) -> int:
        """One pass over every partition. Returns records processed (for tests and the loop)."""
        moved = 0
        for partition in range(self._pipeline.bus.partitions):
            moved += self._pipeline.worker.run(self._pipeline.consumer, partition, flush=False)
        if moved:
            self._last_activity = self._clock()
        elif self._clock() - self._last_activity >= self._idle_flush:
            self._pipeline.worker.flush()
            self._last_activity = self._clock()
        return moved

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                moved = self.run_once()
            except Exception as exc:  # noqa: BLE001 - one bad poll must not kill the loop
                _LOG.warning("kafka_scoring_cycle_failed", error=str(exc))
                moved = 0
            if moved == 0:
                self._stop.wait(self._poll_interval)


def build_kafka_pipeline(
    *,
    bootstrap_servers: str,
    ml_client: MlWindowScorerLike,
    alerts: Any,
    hub: Any,
    registry: Any,
    partitions: int = 6,
    window_size: int = 50,
    bus: KafkaBus | None = None,
    retention_ms: int | None = None,
) -> tuple[FlowPublisher, LiveScoringLoop, KafkaBus]:
    """Assemble publisher, live loop and bus around the production dependencies."""
    from aegis_ml.scoring.fusion import fuse  # type: ignore[import-not-found]

    from app.pipeline import build_pipeline
    from app.services.correlator import Modality

    kafka_bus = bus or KafkaBus(bootstrap_servers, partitions=partitions, retention_ms=retention_ms)
    pipeline = build_pipeline(
        MlWindowAdapter(ml_client),
        fuse=fuse,
        alerts=alerts,
        label_family=lambda _identity: FLOW_FAMILY,
        hub=hub,
        registry=registry,
        modality=Modality.flow,
        partitions=partitions,
        window_size=window_size,
        bus=kafka_bus,
    )
    return FlowPublisher(pipeline, kafka_bus), LiveScoringLoop(pipeline), kafka_bus
