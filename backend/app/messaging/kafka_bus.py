"""A real Kafka broker behind the ``Producer`` and ``Consumer`` interfaces (Q-08, D-085).

The pipeline (``app.pipeline``) talks to its bus through two calls: ``send`` for
the producer side and ``read`` / ``end_offset`` for the consumer side. This module
implements those calls over kafka-python-ng, so the same ``FlowProducer``,
``FlowConsumer`` and ``ScoringWorker`` run against a broker in production and
against ``InProcessBus`` in the golden test.

Producer guarantees: ``acks=all`` with idempotence, and ``flush()`` raises when any
record was not acknowledged. The ingest route calls ``flush()`` before it answers,
so a record is only counted as taken in once the broker has it.

Consumer guarantees: one consumer per partition, assigned explicitly (no consumer
group and no broker-side commits). The position is the caller's (the worker's
``OffsetTracker``), passed in on every read with ``seek``, so a read never skips
records that another partition's poll would have discarded.

The client factories are injectable so the adapter can be exercised without a
broker; the real broker run is the operator's check (see docs/operate.md).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app.messaging.partitioner import FLOW_TOPIC


class KafkaBusError(RuntimeError):
    """A record was not acknowledged by the broker, or the broker call failed."""


def _decode_headers(raw: Sequence[tuple[str, bytes | None]] | None) -> dict[str, str]:
    """Headers as the pipeline carries them: text to text, absent values dropped."""
    out: dict[str, str] = {}
    for key, value in raw or ():
        if value is not None:
            out[key] = value.decode("utf-8", errors="replace")
    return out


class KafkaBus:
    """Producer and consumer over one topic, backed by a Kafka broker."""

    def __init__(
        self,
        bootstrap_servers: str,
        *,
        topic: str = FLOW_TOPIC,
        partitions: int = 6,
        send_timeout_s: float = 10.0,
        poll_timeout_ms: int = 100,
        producer_factory: Callable[[], Any] | None = None,
        consumer_factory: Callable[[], Any] | None = None,
    ) -> None:
        """Remember where the broker is. Clients are created on first use."""
        if not bootstrap_servers.strip():
            msg = "bootstrap_servers must name at least one broker"
            raise ValueError(msg)
        if partitions <= 0:
            msg = f"partitions must be positive, got {partitions}"
            raise ValueError(msg)
        self.topic = topic
        self.partitions = partitions
        self._bootstrap = bootstrap_servers
        self._send_timeout = send_timeout_s
        self._poll_timeout_ms = poll_timeout_ms
        self._producer_factory = producer_factory or self._default_producer
        self._consumer_factory = consumer_factory or self._default_consumer
        self._producer: Any | None = None
        self._consumers: dict[int, Any] = {}
        self._pending: list[Any] = []
        self._lock = threading.Lock()

    # -- clients -----------------------------------------------------------------

    def _default_producer(self) -> Any:
        from kafka import KafkaProducer  # type: ignore[import-untyped]

        return KafkaProducer(
            bootstrap_servers=self._bootstrap,
            acks="all",
            enable_idempotence=True,
            linger_ms=5,
            retries=5,
            value_serializer=None,
        )

    def _default_consumer(self) -> Any:
        from kafka import KafkaConsumer  # type: ignore[import-untyped]

        return KafkaConsumer(
            bootstrap_servers=self._bootstrap,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            group_id=None,
        )

    def _producer_client(self) -> Any:
        with self._lock:
            if self._producer is None:
                self._producer = self._producer_factory()
            return self._producer

    def _consumer_for(self, partition: int) -> Any:
        with self._lock:
            consumer = self._consumers.get(partition)
            if consumer is None:
                from kafka import TopicPartition  # type: ignore[import-untyped]

                consumer = self._consumer_factory()
                consumer.assign([TopicPartition(self.topic, partition)])
                self._consumers[partition] = consumer
            return consumer

    # -- Producer ----------------------------------------------------------------

    def send(
        self,
        topic: str,
        value: bytes,
        partition: int,
        key: bytes,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Queue one record for ``partition``. Delivery is confirmed by :meth:`flush`."""
        if not 0 <= partition < self.partitions:
            msg = f"partition {partition} is outside 0..{self.partitions - 1}"
            raise ValueError(msg)
        producer = self._producer_client()
        encoded = [(k, v.encode("utf-8")) for k, v in (headers or {}).items()]
        future = producer.send(topic, value=value, key=key, partition=partition, headers=encoded)
        with self._lock:
            self._pending.append(future)

    def flush(self) -> None:
        """Wait until every queued record is acknowledged; raise if any was not."""
        with self._lock:
            pending, self._pending = self._pending, []
        if not pending:
            return
        producer = self._producer_client()
        producer.flush(timeout=self._send_timeout)
        for future in pending:
            try:
                future.get(timeout=self._send_timeout)
            except Exception as exc:
                msg = f"record not acknowledged by the broker: {exc}"
                raise KafkaBusError(msg) from exc

    # -- Consumer ----------------------------------------------------------------

    def read(
        self, topic: str, partition: int, from_offset: int, limit: int
    ) -> list[tuple[int, bytes, Mapping[str, str]]]:
        """Return up to ``limit`` records at or after ``from_offset``, oldest first."""
        from kafka import TopicPartition  # type: ignore[import-untyped]

        consumer = self._consumer_for(partition)
        tp = TopicPartition(topic, partition)
        consumer.seek(tp, from_offset)
        batches = consumer.poll(timeout_ms=self._poll_timeout_ms, max_records=limit)
        records = batches.get(tp, [])[:limit]
        return [(r.offset, r.value, _decode_headers(r.headers)) for r in records]

    def end_offset(self, topic: str, partition: int) -> int:
        """The log end offset of ``partition``, for lag."""
        from kafka import TopicPartition  # type: ignore[import-untyped]

        consumer = self._consumer_for(partition)
        tp = TopicPartition(topic, partition)
        return int(consumer.end_offsets([tp])[tp])

    def close(self) -> None:
        """Flush and close every client this bus created."""
        with self._lock:
            producer, self._producer = self._producer, None
            consumers, self._consumers = self._consumers, {}
        if producer is not None:
            producer.flush(timeout=self._send_timeout)
            producer.close()
        for consumer in consumers.values():
            consumer.close()
