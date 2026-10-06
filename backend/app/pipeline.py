"""The in-process pipeline: ingest -> bus -> score -> detect -> correlate -> row (T-319).

R-88 asks for a golden test over the whole path, from synthetic traffic to an
alert the API returns, in CI and without Docker-in-Docker. That means the two
systems this environment does not have -- Kafka and PostgreSQL -- are fakes, and
everything between them is the real thing: the ingest service's validation, the
producer's partition function, the scoring worker's windower, the correlator's
policy, and the query API.

The fakes sit at the **external system's boundary**, not above it. The bus is a
broker: a log per partition, offsets assigned on append, one header set per
record, and a consumer that decodes ``flow@1`` payloads. Above it the real
`FlowProducer` decides partitions and the real `ScoringWorker` decides windows,
so a defect in either is a defect the golden test sees. An in-process double that
spoke `ConsumedRecord` directly would hide exactly the code the test exists to
exercise.

Four things are injected because they do not exist yet, and each is a recorded
gap rather than a silent stand-in:

* the scorer -- the ML service exposes no scoring endpoint (T-307's own note);
* the fusion rule -- the backend image does not install the ML package, so the
  arithmetic is passed in (the golden test passes the real ``aegis_ml`` rule);
* the family labeler -- no attributed classifier is wired into ingest;
* the entity ids -- ``entities.id`` is an Identity column the ingest path does
  not write, so :class:`EntityRegistry` allocates in memory (the ``alerts`` table
  also has no case-id column, see :mod:`app.services.alert_store`).

D-053 records all of them, and the golden test asserts the path that *is* built
rather than the path a diagram describes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.models import Alert
from app.messaging.partitioner import FLOW_TOPIC
from app.messaging.producer import FlowProducer, OffsetTracker, SentRecord
from app.observability.tracing import TRACEPARENT_HEADER
from app.schemas.ingest import FlowRecordIn
from app.services.alert_store import AlertStore
from app.services.alert_stream import AlertHub
from app.services.correlator import (
    Action,
    Correlator,
    Detection,
    FusionRule,
    InMemoryCaseStore,
    Modality,
    Outcome,
    alert_row,
)
from app.services.query_service import alert_row_of
from app.workers.scoring_worker import (
    ConsumedRecord,
    Scorer,
    ScoreSink,
    ScoringWorker,
    WindowIdentity,
)

__all__ = [
    "AlertWriter",
    "DetectionSink",
    "EntityRegistry",
    "FlowConsumer",
    "InProcessBus",
    "Pipeline",
    "build_pipeline",
]


@dataclass(frozen=True, slots=True)
class _LogRecord:
    """One record in a partition's log: an immutable offset plus its bytes."""

    offset: int
    value: bytes
    headers: Mapping[str, str]


class InProcessBus:
    """A Kafka-shaped broker in memory: a log per topic and partition (T-319).

    Offsets are assigned on append and never reused, records are immutable, and a
    read starts at the offset it is given -- the three properties the worker's
    resume logic depends on. What it deliberately does not model is replication,
    retention and consumer groups: a test that needed those would be testing Kafka,
    not this application.
    """

    __slots__ = ("_log", "partitions")

    def __init__(self, *, partitions: int = 6) -> None:
        """Create an empty bus with a fixed partition count."""
        if partitions <= 0:
            msg = f"partitions must be positive, got {partitions}"
            raise ValueError(msg)
        self.partitions = partitions
        self._log: dict[tuple[str, int], list[_LogRecord]] = {}

    def send(
        self,
        topic: str,
        value: bytes,
        partition: int,
        key: bytes,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Append one record, exactly where the broker client would (the ``Producer`` call).

        The key is accepted and dropped: a broker uses it for partitioning, and
        the partition is already chosen by :func:`partition_for` before this call.
        """
        if not 0 <= partition < self.partitions:
            msg = f"partition {partition} is outside 0..{self.partitions - 1}"
            raise ValueError(msg)
        log = self._log.setdefault((topic, partition), [])
        log.append(_LogRecord(offset=len(log), value=value, headers=dict(headers or {})))

    def read(
        self, topic: str, partition: int, from_offset: int, limit: int
    ) -> list[tuple[int, bytes, Mapping[str, str]]]:
        """Return up to ``limit`` records at or after ``from_offset``."""
        log = self._log.get((topic, partition), [])
        return [
            (record.offset, record.value, record.headers) for record in log[from_offset:][:limit]
        ]

    def end_offset(self, topic: str, partition: int) -> int:
        """The offset a producer would read as the log's end, for lag."""
        return len(self._log.get((topic, partition), []))

    def count(self) -> int:
        """How many records are on the bus, across every topic and partition."""
        return sum(len(log) for log in self._log.values())


class FlowConsumer:
    """The scoring worker's ``Consumer`` over a bus, decoding ``flow@1`` (T-319).

    Decoding happens here rather than before the bus on purpose: the payload the
    producer sent is the payload the consumer parses, so the golden test exercises
    the wire contract instead of a shortcut that passes Python objects along.
    """

    __slots__ = ("_bus", "_topic")

    def __init__(self, bus: InProcessBus, *, topic: str = FLOW_TOPIC) -> None:
        """Bind to a bus and the topic this consumer reads."""
        self._bus = bus
        self._topic = topic

    def read(self, partition: int, from_offset: int, limit: int) -> Sequence[ConsumedRecord]:
        """Return up to ``limit`` records from ``from_offset``, oldest first."""
        return [
            ConsumedRecord(
                offset=offset,
                partition=partition,
                flow=FlowRecordIn.model_validate_json(value),
                traceparent=headers.get(TRACEPARENT_HEADER),
            )
            for offset, value, headers in self._bus.read(self._topic, partition, from_offset, limit)
        ]

    def end_offset(self, partition: int) -> int:
        """This consumer's view of the partition end, for lag."""
        return self._bus.end_offset(self._topic, partition)


class EntityRegistry:
    """Assigns the integer id an alert row references (T-319).

    ``alerts.entity_id`` is a foreign key into ``entities``, and the persistent
    source of that id is the table's Identity column. The ingest path does not
    write ``entities`` yet, so this allocates in memory: stable per ``(kind,
    value)``, assigned on first sight, so two detections about one host are one
    entity. The id is meaningful within a process and nowhere else, which is why
    it is a recorded gap and not presented as the real thing.
    """

    __slots__ = ("_ids",)

    def __init__(self) -> None:
        """Start empty, with ids from 1 the way a fresh sequence would."""
        self._ids: dict[tuple[str, str], int] = {}

    def id_for(self, kind: str, value: str) -> int:
        """Return the stable id for one entity, allocating it on first sight."""
        key = (kind, value)
        if key not in self._ids:
            self._ids[key] = len(self._ids) + 1
        return self._ids[key]

    def __len__(self) -> int:
        """How many entities have been seen."""
        return len(self._ids)


class DetectionSink:
    """A ``ScoreSink`` that turns each scored window into a detection (T-319).

    This is the adapter T-307 left out: the worker emits scores, the correlator
    consumes detections, and something has to say which entity, which family and
    when. It stays small on purpose -- every *decision* remains in the correlator,
    including what to do with a duplicate.

    A window with no close time is refused rather than dated from the worker's
    clock: an alert's ``first_seen`` is when the traffic happened, and a replay
    stamped with the replay's clock would move an incident's start time.
    """

    __slots__ = ("_correlator", "_label_family", "_modality", "_model_id", "_publish", "_registry")

    def __init__(
        self,
        correlator: Correlator,
        registry: EntityRegistry,
        publish: Callable[[Outcome], Alert | None],
        *,
        label_family: Callable[[WindowIdentity], str],
        modality: Modality = Modality.flow,
        model_id: str | None = None,
    ) -> None:
        """Wire the correlator, the id source, the labeler and the alert writer."""
        self._correlator = correlator
        self._registry = registry
        self._publish = publish
        self._label_family = label_family
        self._modality = modality
        self._model_id = model_id

    def put(
        self,
        identity: WindowIdentity,
        score: float,
        records: int,
        *,
        traceparent: str | None = None,
        closed_at: datetime | None = None,
    ) -> None:
        """Correlate one scored window, and store the case it produced.

        Raises:
            ValueError: if the window carries no close time.
        """
        if closed_at is None:
            msg = (
                "a scored window must carry the close time of its last record; "
                "an alert dated from the worker's clock would move on replay"
            )
            raise ValueError(msg)
        detection = Detection(
            entity_id=self._registry.id_for(identity.key_kind, identity.key),
            family=self._label_family(identity),
            modality=self._modality,
            score=score,
            at=closed_at,
            evidence_id=identity.as_string(),
            model_id=self._model_id,
            traceparent=traceparent,
        )
        self._publish(self._correlator.ingest(detection))


class AlertWriter:
    """Writes each case as an alert row and announces it (T-310, T-319).

    ``created``, ``absorbed`` and ``grouped`` all reach here, and each one
    refreshes the same row: an incident that absorbs a repeat is one alert whose
    count grew, not a second alert. A ``duplicate`` never arrives -- the correlator
    short-circuits it, which is what keeps a replayed window from touching a row an
    analyst is looking at.
    """

    __slots__ = ("_alerts", "_clock", "_hub")

    def __init__(
        self,
        alerts: AlertStore,
        *,
        hub: AlertHub | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Wire the store, the optional stream, and the row clock."""
        self._alerts = alerts
        self._hub = hub
        self._clock = clock or _utcnow

    def __call__(self, outcome: Outcome) -> Alert | None:
        """Store one outcome's case, returning the row (or ``None`` for a duplicate)."""
        if outcome.action is Action.duplicate:
            return None
        row = self._alerts.save(outcome.case.id, alert_row(outcome.case), created_at=self._clock())
        if self._hub is not None:
            self._hub.publish(alert_row_of(row))
        return row


def _utcnow() -> datetime:
    """The current time, aware, in UTC."""
    return datetime.now(UTC)


@dataclass(slots=True)
class Pipeline:
    """The composed path, with every external system injected (T-319)."""

    bus: InProcessBus
    producer: FlowProducer
    consumer: FlowConsumer
    worker: ScoringWorker
    committer: OffsetTracker
    correlator: Correlator
    sink: ScoreSink
    alerts: AlertStore
    registry: EntityRegistry

    def publish(
        self, records: Sequence[FlowRecordIn], *, traceparent: str | None = None
    ) -> list[SentRecord]:
        """Hand accepted records to the bus, the way the ingest route does.

        One header set per call: every record in one ingest request was accepted
        under one trace context, so the trace that reaches the alert is the trace
        the client was given.
        """
        headers = {TRACEPARENT_HEADER: traceparent} if traceparent else None
        return self.producer.send_batch(
            ((str(record.src_ip), record.model_dump_json().encode()) for record in records),
            headers=headers,
        )

    def drain(self, partitions: Sequence[int] | None = None) -> int:
        """Score and correlate everything on the bus, returning records processed."""
        chosen = tuple(partitions) if partitions is not None else tuple(range(self.bus.partitions))
        return sum(self.worker.run(self.consumer, partition) for partition in chosen)


def build_pipeline(
    scorer: Scorer,
    *,
    fuse: FusionRule,
    alerts: AlertStore,
    label_family: Callable[[WindowIdentity], str],
    hub: AlertHub | None = None,
    registry: EntityRegistry | None = None,
    model_id: str | None = None,
    modality: Modality = Modality.flow,
    partitions: int = 6,
    window_size: int = 50,
    clock: Callable[[], datetime] | None = None,
) -> Pipeline:
    """Assemble the in-process pipeline over the injected dependencies.

    The parameters are the systems this environment does not have; the wiring
    between them is the production wiring, and it is what the golden test drives.
    """
    bus = InProcessBus(partitions=partitions)
    entities = registry or EntityRegistry()
    correlator = Correlator(InMemoryCaseStore(), fuse)
    writer = AlertWriter(alerts, hub=hub, clock=clock)
    sink = DetectionSink(
        correlator,
        entities,
        writer,
        label_family=label_family,
        modality=modality,
        model_id=model_id,
    )
    committer = OffsetTracker()
    return Pipeline(
        bus=bus,
        producer=FlowProducer(bus, num_partitions=partitions),
        consumer=FlowConsumer(bus),
        worker=ScoringWorker(scorer, sink, committer, window_size=window_size),
        committer=committer,
        correlator=correlator,
        sink=sink,
        alerts=alerts,
        registry=entities,
    )
