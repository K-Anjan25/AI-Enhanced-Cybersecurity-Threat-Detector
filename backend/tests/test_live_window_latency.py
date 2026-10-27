"""The live path scores a trickle of flows within a bounded wait, not in bursts.

The symptom this guards against: at 1-2 flows per second, a 50-flow window per source
takes tens of seconds to fill, and the old idle flush never fired because any movement
reset its clock. The fix is an age bound per source (``ScoringWorker.flush_stale``),
called on every poll by ``LiveScoringLoop.run_once``. These tests run on a fake clock,
so the timing assertions are exact rather than sleep-based.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from aegis_ml.data.windowing import Window  # type: ignore[import-not-found]
from app.services.kafka_pipeline import LiveScoringLoop
from app.workers.scoring_worker import (
    ConsumedRecord,
    InMemoryScoreSink,
    ScoringWorker,
)

from tests.test_scoring_worker import DictCommitter, wire

WINDOW_SIZE = 50
MAX_WAIT = 2.0


class FakeClock:
    """A monotonic clock the test advances by hand."""

    def __init__(self) -> None:
        """Start at time zero."""
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class GrowingConsumer:
    """A partition that receives records while the test runs, as a live stream does."""

    def __init__(self) -> None:
        """Start with an empty partition."""
        self.records: list[ConsumedRecord] = []

    def arrive(self, src_ip: str, minute: int) -> None:
        offset = len(self.records)
        self.records.append(ConsumedRecord(offset=offset, partition=0, flow=wire(src_ip, minute)))

    def read(self, partition: int, from_offset: int, limit: int) -> list[ConsumedRecord]:
        return [r for r in self.records if r.offset >= from_offset][:limit]


class TimedScorer:
    """Records, for each scored window, when it was scored and how many flows it had."""

    def __init__(self, clock: FakeClock) -> None:
        """Bind to the fake clock."""
        self._clock = clock
        self.scored: list[tuple[float, int]] = []

    def score(self, window: Window[Any]) -> float:
        self.scored.append((self._clock(), len(window.records)))
        return 0.5


def _worker(clock: FakeClock, scorer: TimedScorer) -> ScoringWorker:
    return ScoringWorker(
        scorer,  # type: ignore[arg-type]
        InMemoryScoreSink(),
        DictCommitter(),
        window_size=WINDOW_SIZE,
        clock=clock,
    )


def test_a_lone_flow_is_released_at_the_bound_not_before() -> None:
    clock = FakeClock()
    scorer = TimedScorer(clock)
    worker = _worker(clock, scorer)
    consumer = GrowingConsumer()
    consumer.arrive("10.0.0.1", 0)
    worker.run(consumer, 0, flush=False)

    clock.now = MAX_WAIT - 0.5
    assert worker.flush_stale(MAX_WAIT) == 0
    assert scorer.scored == []

    clock.now = MAX_WAIT
    assert worker.flush_stale(MAX_WAIT) == 1
    assert scorer.scored == [(MAX_WAIT, 1)]


def test_a_steady_trickle_never_waits_longer_than_the_bound() -> None:
    """One flow a second from three sources for 60 s: every flow is scored within the bound."""
    clock = FakeClock()
    scorer = TimedScorer(clock)
    worker = _worker(clock, scorer)
    consumer = GrowingConsumer()
    arrivals: list[float] = []  # one entry per flow; the bound itself is pinned above
    sources = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    for second in range(60):
        clock.now = float(second)
        consumer.arrive(sources[second % 3], second)
        arrivals.append(clock.now)
        worker.run(consumer, 0, flush=False)
        worker.flush_stale(MAX_WAIT)

    # Drain what is still inside its bound at the end of the minute.
    clock.now = 60.0 + MAX_WAIT
    worker.flush_stale(MAX_WAIT)

    scored_flows = sum(count for _, count in scorer.scored)
    assert scored_flows == len(arrivals), "every flow must be scored, none stranded"
    # No window is a 50-flow window here: nothing waited for one, which is the point.
    assert all(count < WINDOW_SIZE for _, count in scorer.scored)


def test_the_live_loop_releases_partial_windows_while_records_keep_moving() -> None:
    """The regression: the old idle flush never fired while any record was moving."""
    clock = FakeClock()
    scorer = TimedScorer(clock)
    worker = _worker(clock, scorer)
    consumer = GrowingConsumer()
    pipeline = SimpleNamespace(
        worker=worker,
        consumer=consumer,
        bus=SimpleNamespace(partitions=1),
    )
    live = LiveScoringLoop(pipeline, max_window_wait_seconds=MAX_WAIT)  # type: ignore[arg-type]

    consumer.arrive("10.0.0.1", 0)
    for second in range(1, 10):
        clock.now = float(second)
        consumer.arrive("10.0.0.1", second)  # movement on every pass, as on a trickle
        live.run_once()

    assert scorer.scored, "a source that never fills a window must still be scored"
    first_release, first_count = scorer.scored[0]
    assert first_release <= MAX_WAIT + 1.0
    assert first_count < WINDOW_SIZE


def test_a_zero_bound_scores_each_flow_as_it_arrives() -> None:
    clock = FakeClock()
    scorer = TimedScorer(clock)
    worker = _worker(clock, scorer)
    consumer = GrowingConsumer()
    live = LiveScoringLoop(
        SimpleNamespace(worker=worker, consumer=consumer, bus=SimpleNamespace(partitions=1)),  # type: ignore[arg-type]
        max_window_wait_seconds=0.0,
    )
    consumer.arrive("10.0.0.1", 0)
    live.run_once()
    assert scorer.scored == [(0.0, 1)]


def test_a_negative_bound_is_refused() -> None:
    import pytest

    with pytest.raises(ValueError, match="max_window_wait_seconds"):
        LiveScoringLoop(
            SimpleNamespace(worker=None, consumer=None, bus=SimpleNamespace(partitions=1)),  # type: ignore[arg-type]
            max_window_wait_seconds=-1.0,
        )
