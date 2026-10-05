"""Scoring worker: consume -> window -> score -> emit (T-307).

The acceptance criterion is that a restart resumes from the committed offset
with no data loss and no duplicates. Those two pull in opposite directions, and
it is worth being explicit about how both are met, because the obvious
implementations each satisfy one and break the other.

Committing the offset *before* the work is done gives at-most-once: a crash
loses records. Committing *after* gives at-least-once: a crash between emit and
commit means the window is processed twice.

So this worker commits after emitting -- records are never lost -- and gets
"no duplicates" from the other end: **emission is idempotent**. Every window
carries a deterministic identity, `(key, index)`, derived from the entity and
its position in that entity's stream, not from anything about the delivery
attempt. A window replayed after a restart produces the same identity, so the
sink overwrites rather than appends.

That identity is why the windowing comes from `aegis_ml.data.windowing` rather
than being reimplemented here. `Window.index` is assigned per entity by the
shared windower; a second windowing implementation would number windows
differently and the two would emit under different identities for the same
data, which is precisely the duplicate this design exists to prevent.

There is no scoring endpoint in the ML service yet -- `serving/app.py` exposes
only `/healthz` -- so `Scorer` is an injected dependency. That is recorded, not
hidden: the HTTP call is the untested part.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from aegis_ml.data.records import FlowRecord  # type: ignore[import-not-found]
from aegis_ml.data.windowing import Window, window_flows  # type: ignore[import-not-found]

from app.observability import metrics
from app.observability.tracing import duration_seconds, span
from app.schemas.ingest import FlowRecordIn

__all__ = [
    "Consumer",
    "ConsumedRecord",
    "InMemoryScoreSink",
    "OffsetCommitter",
    "ScoreSink",
    "Scorer",
    "ScoringWorker",
    "WindowIdentity",
    "window_identity",
]


@dataclass(frozen=True, slots=True)
class ConsumedRecord:
    """One record as it came off the topic, with the offset it arrived at.

    ``traceparent`` is the W3C trace context the record carried in its Kafka
    headers, if the ingest side put one there. It is not part of the window's
    identity -- identity is what makes replay idempotent, and tracing must never
    be able to change it -- it is carried alongside so the score a window
    produces can be attributed to the request that ingested it (T-317).
    """

    offset: int
    partition: int
    flow: FlowRecordIn
    traceparent: str | None = None


@dataclass(frozen=True, slots=True)
class WindowIdentity:
    """The stable identity a scored window is emitted under.

    Keyed on the entity and the **log offset of the window's first record**.

    An offset is a property of the record, not of the delivery attempt: Kafka
    offsets are immutable, so the same record has the same offset however many
    times it is read. That is what makes it safe here. What must never enter
    this identity is anything about the attempt -- a processing timestamp, an
    attempt counter, or a window counter held in worker memory. A counter is
    the tempting choice and the wrong one: it resets when the worker restarts,
    so the replayed window gets index zero again and lands on an identity
    already used by an earlier window.

    Deriving identity from data rather than from process state is the whole
    trick, and it is why "no duplicates" survives a restart instead of only
    surviving within one process lifetime.
    """

    key: str
    key_kind: str
    first_offset: int

    def as_string(self) -> str:
        """A single string form, for sinks keyed by one field."""
        return f"{self.key_kind}:{self.key}@{self.first_offset}"


def window_identity(window: Window[FlowRecord], first_offset: int) -> WindowIdentity:
    """The identity of one window, given the offset its first record arrived at."""
    return WindowIdentity(key=window.key, key_kind=window.key_kind, first_offset=first_offset)


class Scorer(Protocol):
    """The model-service call, narrowed to what the worker needs."""

    def score(self, window: Window[FlowRecord]) -> float:
        """Return an anomaly score in [0, 1] for one window."""
        ...


class ScoreSink(Protocol):
    """Where scores land. Implementations must be idempotent per identity."""

    def put(
        self,
        identity: WindowIdentity,
        score: float,
        records: int,
        *,
        traceparent: str | None = None,
    ) -> None:
        """Store one scored window, replacing any earlier score for it."""
        ...


class InMemoryScoreSink:
    """A ScoreSink that overwrites, which is what makes replay safe."""

    __slots__ = ("_scores", "_traceparents", "puts")

    def __init__(self) -> None:
        """Start empty, counting puts so replays are observable."""
        self._scores: dict[str, tuple[float, int]] = {}
        self._traceparents: dict[str, str] = {}
        self.puts = 0

    def put(
        self,
        identity: WindowIdentity,
        score: float,
        records: int,
        *,
        traceparent: str | None = None,
    ) -> None:
        """Store or replace one window's score."""
        self.puts += 1
        self._scores[identity.as_string()] = (score, records)
        if traceparent is not None:
            self._traceparents[identity.as_string()] = traceparent

    def traceparent_for(self, identity: WindowIdentity) -> str | None:
        """The trace context stored with one window's score, if it had one.

        This is what an adapter carries into the detection it builds from the
        score, and so on to the alert record.
        """
        return self._traceparents.get(identity.as_string())

    def scores(self) -> dict[str, tuple[float, int]]:
        """Every stored score, keyed by window identity."""
        return dict(self._scores)

    def __len__(self) -> int:
        """How many distinct windows are stored."""
        return len(self._scores)


class Consumer(Protocol):
    """The topic, narrowed to reading from a resume point."""

    def read(self, partition: int, from_offset: int, limit: int) -> Sequence[ConsumedRecord]:
        """Return up to ``limit`` records at or after ``from_offset``."""
        ...


class OffsetCommitter(Protocol):
    """Where committed offsets are kept across restarts."""

    def commit(self, partition: int, offset: int) -> None:
        """Record that everything up to ``offset`` has been emitted."""
        ...

    def resume_from(self, partition: int) -> int:
        """The offset to start at after a restart."""
        ...


class ScoringWorker:
    """Drains a partition, windows the flows, scores them, and emits."""

    __slots__ = (
        "_batch",
        "_committer",
        "_next_index",
        "_pending",
        "_scorer",
        "_sink",
        "_window_size",
    )

    def __init__(
        self,
        scorer: Scorer,
        sink: ScoreSink,
        committer: OffsetCommitter,
        *,
        window_size: int = 50,
        batch_size: int = 500,
    ) -> None:
        """Wire the three injected dependencies."""
        self._scorer = scorer
        self._sink = sink
        self._committer = committer
        self._window_size = window_size
        self._batch = batch_size
        # Per-entity state carried across batches, so window indices stay
        # continuous with what has already been emitted.
        self._pending: dict[str, list[tuple[int, FlowRecord, str | None]]] = {}

    def _to_flow_record(self, wire: FlowRecordIn) -> FlowRecord:
        """Convert a wire record to the record the windower expects.

        The two contracts are field-identical and kept that way by
        `tests/test_ingest_contract.py`, so this is a re-wrap rather than a
        mapping with its own opinions.
        """
        return FlowRecord(**wire.model_dump())

    def run(self, consumer: Consumer, partition: int, *, max_batches: int | None = None) -> int:
        """Process one partition until it is drained.

        Returns the number of records processed. Commits after each batch is
        emitted, so a crash replays at most one batch -- and replay is safe
        because emission is idempotent.
        """
        total = 0
        batches = 0
        position = self._committer.resume_from(partition)

        while max_batches is None or batches < max_batches:
            records = consumer.read(partition, position, self._batch)
            if not records:
                break
            total += len(records)
            batches += 1
            self._emit((r.offset, self._to_flow_record(r.flow), r.traceparent) for r in records)
            # After emitting, never before. Committing first would drop the
            # batch on a crash between the commit and the emit.
            self._committer.commit(partition, records[-1].offset)
            position = records[-1].offset + 1

        # The partition is drained: score whatever is left rather than dropping
        # the newest flows, which a live stream always has.
        self._emit((), flush=True)
        return total

    def _emit(
        self,
        batch: Iterable[tuple[int, FlowRecord, str | None]],
        *,
        flush: bool = False,
    ) -> None:
        """Window a batch and score each complete window.

        Records are buffered per entity across batches rather than windowed per
        batch. Windowing each batch on its own restarts the numbering, so batch
        two's first window lands on the same identity as batch one's and
        silently overwrites it -- the idempotent sink that makes replay safe
        becomes the thing that hides the loss. Carrying the remainder keeps the
        windows continuous with what was already emitted.
        """
        for offset, flow, traceparent in batch:
            self._pending.setdefault(str(flow.src_ip), []).append((offset, flow, traceparent))

        for key, buffered in self._pending.items():
            count = (
                len(buffered) if flush else (len(buffered) // self._window_size) * self._window_size
            )
            if count == 0:
                continue
            chunk = buffered[:count]
            self._pending[key] = buffered[count:]
            flows = tuple(flow for _, flow, _traceparent in chunk)
            for window in window_flows(flows, size=self._window_size):
                position = window.index * self._window_size
                first_offset, _first_flow, traceparent = chunk[position]
                identity = WindowIdentity(
                    key=window.key, key_kind=window.key_kind, first_offset=first_offset
                )
                # The span is a child of the ingest request that produced the
                # window's first record, so a slow score can be read against the
                # request that waited for it (NFR-01, T-317). Time is measured
                # around the call itself: the histogram is the model's latency,
                # not the worker's throughput.
                started = time.perf_counter()
                with span(
                    "score window",
                    parent_traceparent=traceparent,
                    attributes={"aegis.window.records": len(window.records)},
                ) as active:
                    score = self._scorer.score(window)
                    active.set_attribute("aegis.score", score)
                metrics.observe_score_latency(duration_seconds(started))
                self._sink.put(identity, score, len(window.records), traceparent=traceparent)


def drain(consumer: Consumer, partitions: Sequence[int], worker: ScoringWorker) -> dict[int, int]:
    """Run the worker over several partitions, reporting each one's count."""
    return {partition: worker.run(consumer, partition) for partition in partitions}


def count_windows(flows: Sequence[FlowRecord], *, size: int = 50) -> int:
    """How many windows a stream cuts into, for tests and capacity checks."""
    return len(window_flows(tuple(flows), size=size))


def iter_batches(records: Sequence[ConsumedRecord], size: int) -> Iterator[list[ConsumedRecord]]:
    """Split a sequence of records into batches."""
    for start in range(0, len(records), size):
        yield list(records[start : start + size])
