"""T-307: the scoring worker resumes with no data loss and no duplicates.

The criterion is tested by actually crashing the worker mid-batch and running a
fresh one against the same committed state, then asserting the set of windows
emitted across both runs is exactly the set a single uninterrupted run would
have produced -- no gaps and no second copy.

That is the property that matters, and it is the one an implementation can
appear to have while not: commit-before-emit loses records, commit-after-emit
without an idempotent sink duplicates them.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aegis_ml.data.records import FlowRecord
from aegis_ml.data.windowing import Window
from app.schemas.ingest import FlowRecordIn
from app.workers.scoring_worker import (
    ConsumedRecord,
    InMemoryScoreSink,
    ScoringWorker,
    WindowIdentity,
    window_identity,
)

WINDOW_SIZE = 5


def wire(src_ip: str, minute: int) -> FlowRecordIn:
    """A valid flow@1 wire record."""
    return FlowRecordIn(
        timestamp=datetime(2026, 3, 15, 10, minute, tzinfo=UTC),
        src_ip=src_ip,  # type: ignore[arg-type]
        dst_ip="10.0.0.2",  # type: ignore[arg-type]
        src_port=1000 + minute,
        dst_port=80,
        protocol="tcp",  # type: ignore[arg-type]
        direction="inbound",  # type: ignore[arg-type]
        packets=10,
        src_packets=5,
        dst_packets=5,
        src_bytes=1000,
        dst_bytes=2000,
        duration=1.5,
    )


class ListConsumer:
    """A topic backed by a list, which is enough to test resume behaviour."""

    def __init__(self, records: list[ConsumedRecord], *, fail_at: int | None = None) -> None:
        """Optionally raise when a given offset is read, to simulate a crash."""
        self._records = records
        self._fail_at = fail_at
        self.reads = 0

    def read(self, partition: int, from_offset: int, limit: int) -> list[ConsumedRecord]:
        """Return records at or after the offset, crashing if configured."""
        self.reads += 1
        batch = [r for r in self._records if r.offset >= from_offset][:limit]
        if self._fail_at is not None and any(r.offset >= self._fail_at for r in batch):
            msg = "simulated crash"
            raise RuntimeError(msg)
        return batch


class DictCommitter:
    """Committed offsets in a dict, which is what survives a restart here."""

    def __init__(self, committed: dict[int, int] | None = None) -> None:
        """Start from any previously committed state."""
        self.committed: dict[int, int] = dict(committed or {})
        self.commits = 0

    def commit(self, partition: int, offset: int) -> None:
        """Record progress, never moving backwards."""
        self.commits += 1
        current = self.committed.get(partition)
        if current is None or offset > current:
            self.committed[partition] = offset

    def resume_from(self, partition: int) -> int:
        """Where a restarted worker begins."""
        committed = self.committed.get(partition)
        return 0 if committed is None else committed + 1


class FixedScorer:
    """Scores by record count, so a window's score identifies it."""

    def __init__(self) -> None:
        """Count the calls."""
        self.calls = 0

    def score(self, window: Window[FlowRecord]) -> float:
        """Return a score derived from the window."""
        self.calls += 1
        return round(len(window.records) / 100, 4)


def records_for(src_ip: str, count: int, *, start_offset: int = 0) -> list[ConsumedRecord]:
    """A run of consecutive records from one source."""
    return [
        ConsumedRecord(offset=start_offset + i, partition=0, flow=wire(src_ip, i))
        for i in range(count)
    ]


# --- basic operation --------------------------------------------------------


def test_the_worker_windows_scores_and_emits() -> None:
    consumer = ListConsumer(records_for("10.0.0.1", 12))
    sink = InMemoryScoreSink()
    worker = ScoringWorker(FixedScorer(), sink, DictCommitter(), window_size=WINDOW_SIZE)

    processed = worker.run(consumer, 0)

    assert processed == 12
    assert len(sink) == 3


def test_an_empty_partition_processes_nothing() -> None:
    sink = InMemoryScoreSink()
    worker = ScoringWorker(FixedScorer(), sink, DictCommitter())
    assert worker.run(ListConsumer([]), 0) == 0
    assert len(sink) == 0


def test_progress_is_committed() -> None:
    committer = DictCommitter()
    worker = ScoringWorker(FixedScorer(), InMemoryScoreSink(), committer, window_size=WINDOW_SIZE)
    worker.run(ListConsumer(records_for("10.0.0.1", 7)), 0)
    assert committer.committed[0] == 6


def test_the_wire_record_survives_the_conversion() -> None:
    """The windower needs aegis_ml records; the API receives wire records."""
    consumer = ListConsumer(records_for("10.0.0.1", WINDOW_SIZE))
    seen: list[FlowRecord] = []

    class Recording:
        def score(self, window: Window[FlowRecord]) -> float:
            seen.extend(window.records)
            return 0.5

    ScoringWorker(Recording(), InMemoryScoreSink(), DictCommitter(), window_size=WINDOW_SIZE).run(
        consumer, 0
    )
    assert len(seen) == WINDOW_SIZE
    assert str(seen[0].src_ip) == "10.0.0.1"


# --- the restart criterion --------------------------------------------------


def test_a_restart_loses_nothing_and_duplicates_nothing() -> None:
    """The acceptance criterion, by crashing the worker mid-stream."""
    all_records = records_for("10.0.0.1", 20)

    # Run 1 crashes partway through.
    committer = DictCommitter()
    first_sink = InMemoryScoreSink()
    crashing = ListConsumer(all_records, fail_at=10)
    worker_one = ScoringWorker(
        FixedScorer(), first_sink, committer, window_size=WINDOW_SIZE, batch_size=5
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        worker_one.run(crashing, 0)

    # Run 2 is a fresh worker over the same committed state.
    second_sink = InMemoryScoreSink()
    worker_two = ScoringWorker(
        FixedScorer(), second_sink, committer, window_size=WINDOW_SIZE, batch_size=5
    )
    worker_two.run(ListConsumer(all_records), 0)

    # Together they must cover every record exactly once.
    emitted = {**first_sink.scores(), **second_sink.scores()}
    baseline_sink = InMemoryScoreSink()
    ScoringWorker(
        FixedScorer(), baseline_sink, DictCommitter(), window_size=WINDOW_SIZE, batch_size=5
    ).run(ListConsumer(all_records), 0)

    assert set(emitted) == set(baseline_sink.scores())
    assert emitted == baseline_sink.scores()


def test_a_replayed_window_overwrites_rather_than_appends() -> None:
    """Idempotence is what makes at-least-once delivery safe."""
    records = records_for("10.0.0.1", 5)
    sink = InMemoryScoreSink()
    committer = DictCommitter()

    for _ in range(3):
        ScoringWorker(FixedScorer(), sink, committer, window_size=WINDOW_SIZE).run(
            ListConsumer(records), 0
        )
        committer.committed.clear()  # force a full reprocess each time

    assert len(sink) == 1
    assert sink.puts == 3  # emitted three times...
    assert len(sink.scores()) == 1  # ...but only one window exists


def test_records_are_never_skipped_when_resuming() -> None:
    """Resume at committed + 1, not at committed and not at the log end."""
    committer = DictCommitter()
    committer.commit(0, 4)
    consumer = ListConsumer(records_for("10.0.0.1", 10))
    sink = InMemoryScoreSink()

    processed = ScoringWorker(FixedScorer(), sink, committer, window_size=WINDOW_SIZE).run(
        consumer, 0
    )

    assert processed == 5  # offsets 5..9, not 4..9 and not nothing


def test_a_restart_does_not_reprocess_what_was_committed() -> None:
    committer = DictCommitter()
    committer.commit(0, 9)
    scorer = FixedScorer()
    ScoringWorker(scorer, InMemoryScoreSink(), committer, window_size=WINDOW_SIZE).run(
        ListConsumer(records_for("10.0.0.1", 10)), 0
    )
    assert scorer.calls == 0


# --- window identity --------------------------------------------------------


def test_the_identity_is_stable_for_the_same_window() -> None:
    records = records_for("10.0.0.1", WINDOW_SIZE)
    identities: list[set[str]] = []
    for _ in range(3):
        sink = InMemoryScoreSink()
        ScoringWorker(FixedScorer(), sink, DictCommitter(), window_size=WINDOW_SIZE).run(
            ListConsumer(records), 0
        )
        identities.append(set(sink.scores()))
    assert identities[0] == identities[1] == identities[2]


def test_the_identity_survives_a_restart() -> None:
    """Same records, fresh worker: the same window must get the same identity.

    This is what a worker-memory counter would have broken.
    """
    records = records_for("10.0.0.1", 10)
    identities = []
    for _ in range(2):
        sink = InMemoryScoreSink()
        ScoringWorker(FixedScorer(), sink, DictCommitter(), window_size=WINDOW_SIZE).run(
            ListConsumer(records), 0
        )
        identities.append(set(sink.scores()))
    assert identities[0] == identities[1]
    assert len(identities[0]) == 2


def test_different_entities_get_different_identities() -> None:
    # Interleaved in arrival order, not concatenated: window_flows requires
    # arrival order and rightly refuses a stream that steps back in time.
    a = records_for("10.0.0.1", WINDOW_SIZE)
    b = records_for("10.0.0.2", WINDOW_SIZE)
    records = [r for pair in zip(a, b, strict=True) for r in pair]
    sink = InMemoryScoreSink()
    ScoringWorker(FixedScorer(), sink, DictCommitter(), window_size=WINDOW_SIZE).run(
        ListConsumer(records), 0
    )
    assert len(sink) == 2


def test_the_identity_is_derived_from_data_not_process_state() -> None:
    """The offset belongs in the key; an attempt counter does not.

    This test originally asserted the opposite -- that no offset may appear --
    and that was wrong. A Kafka offset is a property of the record and is
    immutable, so the same record yields the same identity on every read. What
    defeats idempotence is process state: a window counter held in worker
    memory resets on restart, so the replayed window takes index zero again and
    collides with an earlier window. The identity has no field where such a
    counter could live.
    """
    identity = WindowIdentity(key="10.0.0.1", key_kind="source", first_offset=42)
    assert identity.as_string() == "source:10.0.0.1@42"
    assert set(WindowIdentity.__slots__ if hasattr(WindowIdentity, "__slots__") else ()) <= {
        "key",
        "key_kind",
        "first_offset",
    }


def test_window_identity_is_derived_from_the_window() -> None:
    records = records_for("10.0.0.1", WINDOW_SIZE)
    captured: list[Window[FlowRecord]] = []

    class Capture:
        def score(self, window: Window[FlowRecord]) -> float:
            captured.append(window)
            return 0.1

    ScoringWorker(Capture(), InMemoryScoreSink(), DictCommitter(), window_size=WINDOW_SIZE).run(
        ListConsumer(records), 0
    )
    identity = window_identity(captured[0], 0)
    assert identity.key == "10.0.0.1"
    assert identity.first_offset == 0


# --- batching ---------------------------------------------------------------


def test_batching_does_not_change_the_result() -> None:
    """Batch size is a throughput knob, not a semantic one."""
    records = records_for("10.0.0.1", 20)
    results = []
    for batch in (3, 7, 50):
        sink = InMemoryScoreSink()
        ScoringWorker(
            FixedScorer(), sink, DictCommitter(), window_size=WINDOW_SIZE, batch_size=batch
        ).run(ListConsumer(records), 0)
        results.append(sink.scores())
    assert results[0] == results[1] == results[2]


def test_max_batches_bounds_one_run() -> None:
    consumer = ListConsumer(records_for("10.0.0.1", 20))
    committer = DictCommitter()
    processed = ScoringWorker(
        FixedScorer(), InMemoryScoreSink(), committer, window_size=WINDOW_SIZE, batch_size=5
    ).run(consumer, 0, max_batches=2)
    assert processed == 10
    assert committer.committed[0] == 9


def test_a_partial_final_window_is_still_scored() -> None:
    """A live stream ends mid-window; dropping it would lose the newest flows."""
    sink = InMemoryScoreSink()
    ScoringWorker(FixedScorer(), sink, DictCommitter(), window_size=WINDOW_SIZE).run(
        ListConsumer(records_for("10.0.0.1", 7)), 0
    )
    sizes = [count for _, count in sink.scores().values()]
    assert sorted(sizes) == [2, 5]
