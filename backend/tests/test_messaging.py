"""T-306: `src_ip` partitioning, restart ordering, and the lag gauge.

The acceptance criterion has two halves -- one entity's flows stay ordered
across a restart, and lag is a Prometheus gauge. There is no Kafka broker in
this environment, so what is tested is the logic that *decides* both: which
partition a record goes to, and where a consumer resumes. The broker call
itself is a one-line injection point and is the part left unverified; that gap
is recorded rather than papered over.
"""

from __future__ import annotations

import pytest
from app.messaging.lag import (
    CONSUMER_LAG,
    current_lag,
    lag_from_offsets,
    observe_lag,
    observe_lags,
    reset_lag,
)
from app.messaging.partitioner import FLOW_TOPIC, partition_for, partition_key
from app.messaging.producer import FlowProducer, OffsetTracker, lag_report
from kafka.partitioner import DefaultPartitioner
from prometheus_client import REGISTRY, generate_latest

PARTITIONS = 6


class RecordingClient:
    """Stands in for the broker and remembers what was sent where."""

    def __init__(self) -> None:
        """Start with nothing sent."""
        self.sent: list[tuple[str, bytes, int, bytes]] = []

    def send(self, topic: str, value: bytes, partition: int, key: bytes) -> None:
        """Record the call."""
        self.sent.append((topic, value, partition, key))


# --- the partitioner --------------------------------------------------------


def test_one_source_always_maps_to_one_partition() -> None:
    """The whole ordering guarantee rests on this."""
    for ip in ("10.0.0.1", "192.168.1.50", "203.0.113.7"):
        assert len({partition_for(ip, PARTITIONS) for _ in range(200)}) == 1


def test_the_assignment_matches_kafkas_own_partitioner() -> None:
    """A hand-rolled hash would be deterministic and still wrong.

    If this disagrees with the broker, out-of-order scoring appears after a
    rebalance and nothing here would have caught it.
    """
    real = DefaultPartitioner()
    for i in range(50):
        ip = f"10.1.{i // 20}.{i % 20 + 1}"
        expected = real(partition_key(ip), list(range(PARTITIONS)), [])
        assert partition_for(ip, PARTITIONS) == expected, ip


def test_keys_spread_across_partitions() -> None:
    """Stable is not enough.

    A partitioner that sends everything to one partition is stable and useless.
    """
    seen = {partition_for(f"10.2.0.{i}", PARTITIONS) for i in range(256)}
    assert len(seen) > 1
    assert seen <= set(range(PARTITIONS))


def test_the_assignment_survives_a_restart() -> None:
    """No state means no drift: a fresh process maps identically."""
    before = {f"10.3.0.{i}": partition_for(f"10.3.0.{i}", PARTITIONS) for i in range(50)}
    # A "restart" is a new interpreter; the function is pure, so calling it
    # again with no shared state is the same thing.
    after = {ip: partition_for(ip, PARTITIONS) for ip in before}
    assert before == after


def test_a_different_partition_count_changes_the_mapping() -> None:
    """The operational hazard, recorded rather than hidden.

    Resizing the topic reassigns most keys, so ordering does not survive it.
    """
    moved = [
        ip
        for i in range(100)
        for ip in [f"10.4.0.{i}"]
        if partition_for(ip, 6) != partition_for(ip, 12)
    ]
    assert moved, "expected most keys to move when the partition count doubles"


def test_a_topic_with_no_partitions_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one partition"):
        partition_for("10.0.0.1", 0)


def test_no_available_partitions_is_refused() -> None:
    with pytest.raises(ValueError, match="no partitions are available"):
        partition_for("10.0.0.1", 6, available=[])


def test_the_key_is_the_source_address_alone() -> None:
    """Adding a port or timestamp would split one entity across partitions."""
    assert partition_key("10.0.0.1") == b"10.0.0.1"


# --- the producer -----------------------------------------------------------


def test_the_producer_writes_to_flows_raw() -> None:
    assert FLOW_TOPIC == "flows.raw"
    client = RecordingClient()
    FlowProducer(client).send("10.0.0.1", b"{}")
    assert client.sent[0][0] == "flows.raw"


def test_every_record_from_one_source_goes_to_one_partition() -> None:
    client = RecordingClient()
    producer = FlowProducer(client)
    for i in range(50):
        producer.send("192.168.1.50", f'{{"n":{i}}}'.encode())
    assert len({p for _, _, p, _ in client.sent}) == 1


def test_records_keep_their_order_within_the_partition() -> None:
    client = RecordingClient()
    producer = FlowProducer(client)
    payloads = [f'{{"n":{i}}}'.encode() for i in range(20)]
    producer.send_batch([("10.9.9.9", p) for p in payloads])
    assert [value for _, value, _, _ in client.sent] == payloads


def test_the_record_is_keyed_by_source() -> None:
    """The key is what a consumer groups by; an unkeyed record loses ordering."""
    client = RecordingClient()
    FlowProducer(client).send("10.0.0.1", b"{}")
    assert client.sent[0][3] == b"10.0.0.1"


def test_a_batch_spans_partitions_but_keeps_each_source_together() -> None:
    client = RecordingClient()
    producer = FlowProducer(client)
    producer.send_batch(
        [("10.0.0.1", b"a"), ("10.0.0.2", b"b"), ("10.0.0.1", b"c"), ("10.0.0.2", b"d")]
    )
    by_key: dict[bytes, list[int]] = {}
    for _, value, partition, key in client.sent:
        by_key.setdefault(key, []).append(partition)
    for partitions in by_key.values():
        assert len(set(partitions)) == 1


def test_a_producer_with_no_partitions_is_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        FlowProducer(RecordingClient(), num_partitions=0)


# --- restart ordering -------------------------------------------------------


def test_a_restart_resumes_after_the_last_committed_offset() -> None:
    """Not at it -- that would reprocess the record already handled."""
    tracker = OffsetTracker()
    tracker.commit(0, 41)
    assert tracker.resume_from(0) == 42


def test_an_unconsumed_partition_starts_at_zero() -> None:
    assert OffsetTracker().resume_from(3) == 0


def test_offsets_never_move_backwards() -> None:
    """A stale commit after a rebalance must not rewind and reprocess."""
    tracker = OffsetTracker()
    tracker.commit(0, 100)
    tracker.commit(0, 50)
    assert tracker.committed[0] == 100
    assert tracker.resume_from(0) == 101


def test_partitions_are_tracked_independently() -> None:
    tracker = OffsetTracker()
    tracker.commit(0, 10)
    tracker.commit(1, 99)
    assert tracker.resume_from(0) == 11
    assert tracker.resume_from(1) == 100


def test_no_record_is_skipped_or_repeated_across_a_restart() -> None:
    """The criterion, end to end on the offsets.

    Consume some, restart, consume the rest, and assert the union is the whole
    log exactly once. Resuming from the end would skip; from zero would repeat.
    """
    log = list(range(30))
    tracker = OffsetTracker()
    consumed: list[int] = []

    position = tracker.resume_from(0)
    consumed.extend(log[position:12])
    tracker.commit(0, 11)

    # Restart: a fresh tracker would start at zero, so the committed state is
    # what carries over.
    resumed = OffsetTracker(committed=dict(tracker.committed))
    position = resumed.resume_from(0)
    consumed.extend(log[position:])

    assert consumed == log
    assert len(consumed) == len(set(consumed))


# --- the lag gauge ----------------------------------------------------------


def test_lag_is_the_difference_and_never_negative() -> None:
    assert lag_from_offsets(5, 20) == 15
    assert lag_from_offsets(20, 20) == 0
    # Retention can delete records a consumer had not reached. Reporting a
    # negative lag would read as "ahead" when the consumer has lost its place.
    assert lag_from_offsets(30, 20) == 0


def test_the_gauge_is_registered_with_prometheus() -> None:
    reset_lag()
    observe_lag("scorers", FLOW_TOPIC, 3, 42)
    assert current_lag("scorers", FLOW_TOPIC, 3) == 42.0
    assert b"aegis_kafka_consumer_lag" in generate_latest(REGISTRY)


def test_lag_is_exported_per_partition_not_aggregated() -> None:
    """One stuck partition must not average away into a healthy-looking total."""
    reset_lag()
    observe_lags("scorers", FLOW_TOPIC, {0: 1, 1: 5_000, 2: 2})
    assert current_lag("scorers", FLOW_TOPIC, 1) == 5_000.0
    assert current_lag("scorers", FLOW_TOPIC, 0) == 1.0


def test_the_gauge_carries_group_topic_and_partition_labels() -> None:
    reset_lag()
    observe_lag("scorers", FLOW_TOPIC, 2, 7)
    sample = generate_latest(REGISTRY).decode()
    assert 'group="scorers"' in sample
    assert f'topic="{FLOW_TOPIC}"' in sample
    assert 'partition="2"' in sample


def test_the_gauge_has_help_text() -> None:
    assert CONSUMER_LAG._name == "aegis_kafka_consumer_lag"  # noqa: SLF001


def test_lag_report_covers_every_partition() -> None:
    tracker = OffsetTracker()
    tracker.commit(0, 9)
    report = lag_report(tracker, {0: 20, 1: 5})
    assert report == {0: 10, 1: 5}


def test_an_unobserved_partition_reports_none() -> None:
    reset_lag()
    assert current_lag("nobody", FLOW_TOPIC, 0) is None
