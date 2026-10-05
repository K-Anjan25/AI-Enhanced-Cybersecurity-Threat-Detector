"""Producing flows to Kafka, and the offset bookkeeping behind restarts.

The broker call is deliberately thin and injected. Everything that decides
*where* a record goes and *where a consumer resumes* lives here as pure logic,
so it can be tested without a broker -- which matters, because there is no
Kafka in this environment and the ordering property is the acceptance
criterion.

Ordering across a restart comes from two things working together:

1. The partition assignment is a pure function of `src_ip` and the partition
   count, so a restarted producer sends a given source to the same partition.
2. The consumer resumes from its last **committed** offset in that partition,
   not from the end and not from zero.

Break either and the guarantee goes. Resume from the end and a restart silently
skips records; resume from zero and it reprocesses everything; assign partitions
differently and one entity's flows interleave with another's.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from app.messaging.partitioner import FLOW_TOPIC, partition_for

__all__ = [
    "FLOW_TOPIC",
    "FlowProducer",
    "OffsetTracker",
    "Producer",
    "SentRecord",
    "lag_report",
]


class Producer(Protocol):
    """The broker client, narrowed to the one call this module makes."""

    def send(self, topic: str, value: bytes, partition: int, key: bytes) -> None:
        """Hand one record to the broker."""
        ...


@dataclass(frozen=True, slots=True)
class SentRecord:
    """What was sent, returned so callers can assert where it went."""

    partition: int
    key: str
    topic: str


class FlowProducer:
    """Sends flow records to `flows.raw`, partitioned by `src_ip`."""

    __slots__ = ("_client", "_num_partitions", "_topic")

    def __init__(
        self, client: Producer, *, topic: str = FLOW_TOPIC, num_partitions: int = 6
    ) -> None:
        """Bind to a broker client and a fixed partition count."""
        if num_partitions <= 0:
            msg = f"num_partitions must be positive, got {num_partitions}"
            raise ValueError(msg)
        self._client = client
        self._topic = topic
        self._num_partitions = num_partitions

    @property
    def topic(self) -> str:
        """The topic this producer writes to."""
        return self._topic

    @property
    def num_partitions(self) -> int:
        """How many partitions the topic is configured with."""
        return self._num_partitions

    def send(self, src_ip: str, payload: bytes) -> SentRecord:
        """Send one record, keyed so this source keeps its ordering."""
        partition = partition_for(src_ip, self._num_partitions)
        self._client.send(self._topic, payload, partition, src_ip.encode())
        return SentRecord(partition=partition, key=src_ip, topic=self._topic)

    def send_batch(self, records: Iterable[tuple[str, bytes]]) -> list[SentRecord]:
        """Send a batch.

        Records for one source keep their relative order because they keep their
        partition. Ordering *between* sources is not promised, and never was.
        """
        return [self.send(src_ip, payload) for src_ip, payload in records]


@dataclass(slots=True)
class OffsetTracker:
    """Per-partition committed offsets, which is where a restart resumes from.

    The next offset to read is ``committed + 1``: a Kafka offset identifies a
    record already in the log, so resuming *at* the committed offset would
    reprocess that record.
    """

    committed: dict[int, int] = field(default_factory=dict)

    def commit(self, partition: int, offset: int) -> None:
        """Record that everything up to and including ``offset`` is done.

        Offsets never move backwards. A stale commit arriving after a newer one
        -- which happens when a rebalance hands a partition to another consumer
        -- must not rewind the position and cause reprocessing.
        """
        current = self.committed.get(partition)
        if current is None or offset > current:
            self.committed[partition] = offset

    def resume_from(self, partition: int) -> int:
        """The offset to start reading after a restart."""
        committed = self.committed.get(partition)
        return 0 if committed is None else committed + 1

    def lag(self, partition: int, end_offset: int) -> int:
        """How far behind this partition is, for the Prometheus gauge."""
        return max(0, end_offset - self.resume_from(partition))


def lag_report(tracker: OffsetTracker, end_offsets: dict[int, int]) -> dict[int, int]:
    """Every partition's lag in one pass, ready for `observe_lags`."""
    return {partition: tracker.lag(partition, end) for partition, end in end_offsets.items()}
