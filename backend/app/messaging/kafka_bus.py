"""A real Kafka broker behind the ``Producer`` and ``Consumer`` interfaces (Q-08, D-085).

The pipeline (``app.pipeline``) talks to its bus through two calls: ``send`` for
the producer side and ``read`` / ``end_offset`` for the consumer side. This module
implements those calls over kafka-python-ng, so the same ``FlowProducer``,
``FlowConsumer`` and ``ScoringWorker`` run against a broker in production and
against ``InProcessBus`` in the golden test.

Producer guarantees: ``acks=all`` with retries, so delivery is at-least-once: a retried
send can duplicate a flow. kafka-python-ng 2.2 has no idempotent producer, and the
correlator keys alerts by evidence identity, so a replayed flow does not open a second
alert. ``flush()`` raises when any record was not acknowledged. The ingest route calls
``flush()`` before it answers, so a record is only counted as taken in once the broker
has it.

Consumer guarantees: one consumer per partition, assigned explicitly (no consumer
group and no broker-side commits). The position is the caller's (the worker's
``OffsetTracker``), passed in on every read with ``seek``, so a read never skips
records that another partition's poll would have discarded.

The client factories are injectable so the adapter can be exercised without a
broker; the real broker run is the operator's check (see docs/operate.md).
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from kafka.errors import KafkaError  # type: ignore[import-untyped]

from app.messaging.partitioner import FLOW_TOPIC

_NO_ERROR = 0
_TOPIC_ALREADY_EXISTS = 36


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
        admin_factory: Callable[[], Any] | None = None,
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
        self._admin_factory = admin_factory or self._default_admin
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
            linger_ms=5,
            retries=5,
            value_serializer=None,
        )

    def _default_admin(self) -> Any:
        from kafka.admin import KafkaAdminClient  # type: ignore[import-untyped]

        return KafkaAdminClient(bootstrap_servers=self._bootstrap, client_id="aegis-topic-setup")

    def _default_consumer(self) -> Any:
        from kafka import KafkaConsumer

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
                from kafka import TopicPartition

                consumer = self._consumer_factory()
                consumer.assign([TopicPartition(self.topic, partition)])
                self._consumers[partition] = consumer
            return consumer

    # -- Producer ----------------------------------------------------------------

    def ensure_topic(
        self,
        *,
        attempts: int = 20,
        delay_s: float = 3.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Create the flow topic with the configured partition count, if it is missing.

        This replaces the one-shot kafka-init container, so the partition count the
        producer assumes lives in the code that uses it. It is idempotent: a topic that
        already exists is success. The broker may still be starting, so failures are
        retried; the error is raised only after the last attempt.

        ``create_topics`` in kafka-python-ng does not raise on a per-topic error, so the
        response's ``topic_errors`` is checked here: code 0 is created, 36 is already there.
        """
        last: str = "no attempt made"
        for attempt in range(1, attempts + 1):
            admin: Any | None = None
            try:
                admin = self._admin_factory()
                from kafka.admin import NewTopic

                response = admin.create_topics(
                    [
                        NewTopic(
                            name=self.topic,
                            num_partitions=self.partitions,
                            replication_factor=1,
                        )
                    ]
                )
                errors = [
                    (name, code, message)
                    for name, code, message in getattr(response, "topic_errors", [])
                    if code not in (_NO_ERROR, _TOPIC_ALREADY_EXISTS)
                ]
                if not errors:
                    return
                last = "; ".join(f"{name}: code {code} {message}" for name, code, message in errors)
            except Exception as exc:  # noqa: BLE001 - broker not up yet, or auth refused
                last = str(exc) or type(exc).__name__
            finally:
                if admin is not None:
                    with contextlib.suppress(KafkaError, OSError):
                        admin.close()
            if attempt < attempts:
                sleep(delay_s)
        msg = f"could not create topic {self.topic!r} after {attempts} attempts: {last}"
        raise KafkaBusError(msg)

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
        from kafka import TopicPartition

        consumer = self._consumer_for(partition)
        tp = TopicPartition(topic, partition)
        consumer.seek(tp, from_offset)
        batches = consumer.poll(timeout_ms=self._poll_timeout_ms, max_records=limit)
        records = batches.get(tp, [])[:limit]
        return [(r.offset, r.value, _decode_headers(r.headers)) for r in records]

    def end_offset(self, topic: str, partition: int) -> int:
        """The log end offset of ``partition``, for lag."""
        from kafka import TopicPartition

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
