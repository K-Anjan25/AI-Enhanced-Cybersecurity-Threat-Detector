"""The Kafka path, offline: the real KafkaBus and pipeline over a fake broker client (D-085).

A fake kafka-python client pair shares one log, so what the producer sends is what
the consumer reads, with real offsets, partitions and headers. Everything above the
client is the production code: FlowPublisher, FlowProducer, FlowConsumer,
ScoringWorker, the ML adapter, DetectionSink and the correlator.

What this cannot show is a real broker's behaviour (replication, rebalance, retention,
acks under load). That check is the operator's run against docker compose.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.messaging.kafka_bus import KafkaBus, KafkaBusError
from app.messaging.partitioner import partition_for
from app.observability.tracing import TRACEPARENT_HEADER
from app.schemas.ingest import FlowRecordIn
from app.services.alert_store import InMemoryAlertStore
from app.services.entity_registry import EntityRegistry
from app.services.kafka_pipeline import (
    FlowPublisher,
    MlWindowAdapter,
    ScoringUnavailable,
    build_kafka_pipeline,
)
from app.services.ml_window_scorer import MlWindowScorer
from app.services.rule_detector import MlWindowResult
from kafka import TopicPartition  # type: ignore[import-untyped]

TOPIC = "flows.raw"


# -- a fake broker client -------------------------------------------------------


@dataclass
class _Rec:
    offset: int
    value: bytes
    headers: list[tuple[str, bytes]]


@dataclass
class _Log:
    records: dict[tuple[str, int], list[_Rec]] = field(default_factory=dict)
    fail_next_send: bool = False


class _Future:
    def __init__(self, error: Exception | None) -> None:
        self._error = error

    def get(self, timeout: float | None = None) -> None:
        if self._error is not None:
            raise self._error


class _Producer:
    def __init__(self, log: _Log) -> None:
        self._log = log

    def send(
        self, topic: str, *, value: bytes, key: bytes, partition: int, headers: Any
    ) -> _Future:
        if self._log.fail_next_send:
            self._log.fail_next_send = False
            return _Future(RuntimeError("broker refused the record"))
        bucket = self._log.records.setdefault((topic, partition), [])
        bucket.append(_Rec(offset=len(bucket), value=value, headers=list(headers or [])))
        return _Future(None)

    def flush(self, timeout: float | None = None) -> None:
        return None

    def close(self) -> None:
        return None


class _Consumer:
    def __init__(self, log: _Log) -> None:
        self._log = log
        self._tp: TopicPartition | None = None
        self._position = 0

    def assign(self, partitions: list[TopicPartition]) -> None:
        self._tp = partitions[0]

    def seek(self, tp: TopicPartition, offset: int) -> None:
        self._position = offset

    def poll(self, timeout_ms: int = 0, max_records: int = 500) -> dict[TopicPartition, list[Any]]:
        assert self._tp is not None
        bucket = self._log.records.get((self._tp.topic, self._tp.partition), [])
        batch = bucket[self._position : self._position + max_records]
        return {self._tp: [_Msg(r) for r in batch]} if batch else {}

    def end_offsets(self, partitions: list[TopicPartition]) -> dict[TopicPartition, int]:
        out = {}
        for tp in partitions:
            out[tp] = len(self._log.records.get((tp.topic, tp.partition), []))
        return out

    def close(self) -> None:
        return None


class _Msg:
    def __init__(self, rec: _Rec) -> None:
        self.offset = rec.offset
        self.value = rec.value
        self.headers = rec.headers


def _bus(log: _Log | None = None) -> tuple[KafkaBus, _Log]:
    shared = log or _Log()
    bus = KafkaBus(
        "kafka:9092",
        topic=TOPIC,
        partitions=6,
        producer_factory=lambda: _Producer(shared),
        consumer_factory=lambda: _Consumer(shared),
    )
    return bus, shared


# -- the bus ---------------------------------------------------------------------


def test_send_then_flush_lands_records_on_their_partition_with_headers() -> None:
    bus, log = _bus()
    bus.send(TOPIC, b"x", 2, b"10.0.0.5", {TRACEPARENT_HEADER: "00-abc-def-01"})
    bus.flush()
    [record] = bus.read(TOPIC, 2, 0, 10)
    assert record[0] == 0
    assert record[1] == b"x"
    assert record[2] == {TRACEPARENT_HEADER: "00-abc-def-01"}
    assert bus.read(TOPIC, 3, 0, 10) == []
    assert len(log.records[(TOPIC, 2)]) == 1


def test_flush_raises_when_the_broker_refuses_a_record() -> None:
    bus, log = _bus()
    log.fail_next_send = True
    bus.send(TOPIC, b"x", 0, b"k")
    with pytest.raises(KafkaBusError, match="not acknowledged"):
        bus.flush()


def test_read_starts_at_the_offset_it_is_given_and_respects_the_limit() -> None:
    bus, _ = _bus()
    for i in range(5):
        bus.send(TOPIC, bytes([i]), 1, b"k")
    bus.flush()
    assert [r[0] for r in bus.read(TOPIC, 1, 2, 2)] == [2, 3]
    assert bus.end_offset(TOPIC, 1) == 5


def test_a_partition_outside_the_topic_is_refused() -> None:
    bus, _ = _bus()
    with pytest.raises(ValueError, match="outside"):
        bus.send(TOPIC, b"x", 6, b"k")


def test_a_bus_needs_a_broker_address() -> None:
    with pytest.raises(ValueError, match="bootstrap_servers"):
        KafkaBus("  ")


# -- the pipeline over the bus --------------------------------------------------


class _FakeMl:
    """Stands in for MlWindowScorer: a fixed score, or no score while the model is down."""

    def __init__(self) -> None:
        self.calls: list[int] = []
        self.down = False

    def score(self, flows: list[dict[str, object]]) -> MlWindowResult | None:
        self.calls.append(len(flows))
        if self.down:
            return None
        return MlWindowResult(
            score=0.9, model_id="fake-flownet", reasons=(), partial_evidence=False
        )


def _flow(i: int, src: str = "10.0.0.5") -> FlowRecordIn:
    start = datetime(2026, 10, 18, 12, 0, tzinfo=UTC) + timedelta(seconds=i)
    return FlowRecordIn(
        timestamp=start,
        src_ip=src,  # type: ignore[arg-type]
        dst_ip="10.0.9.9",  # type: ignore[arg-type]
        src_port=40000 + i,
        dst_port=443,
        protocol="tcp",  # type: ignore[arg-type]
        direction="internal",  # type: ignore[arg-type]
        packets=10,
        src_packets=5,
        dst_packets=5,
        src_bytes=500,
        dst_bytes=500,
        duration=1.0,
    )


def _live(ml: _FakeMl) -> tuple[FlowPublisher, Any, Any]:
    bus, _ = _bus()
    publisher, live, _bus_obj = build_kafka_pipeline(
        bootstrap_servers="kafka:9092",
        ml_client=ml,  # type: ignore[arg-type]
        alerts=InMemoryAlertStore(),
        hub=None,
        registry=EntityRegistry(),
        bus=bus,
    )
    return publisher, live, _bus_obj


def test_flows_published_over_kafka_are_scored_in_full_windows_and_the_tail_on_flush() -> None:
    ml = _FakeMl()
    publisher, live, _ = _live(ml)
    publisher.publish([_flow(i) for i in range(120)], traceparent="00-aaaa-bbbb-01")

    live.run_once()
    # Two full 50-flow windows; the 20 left over wait for the stream to go quiet.
    assert ml.calls == [50, 50]

    live._pipeline.worker.flush()
    assert ml.calls == [50, 50, 20]


def test_a_partial_window_is_not_scored_while_the_stream_is_live() -> None:
    ml = _FakeMl()
    publisher, live, _ = _live(ml)
    publisher.publish([_flow(i) for i in range(30)])
    live.run_once()
    assert ml.calls == []


def test_an_ml_outage_leaves_the_offset_uncommitted_so_the_batch_is_retried() -> None:
    ml = _FakeMl()
    publisher, live, bus = _live(ml)
    publisher.publish([_flow(i) for i in range(50)])
    ml.down = True
    partition = partition_for("10.0.0.5", 6)

    with pytest.raises(ScoringUnavailable):
        live._pipeline.worker.run(live._pipeline.consumer, partition, flush=False)
    assert live._pipeline.committer.resume_from(partition) == 0

    ml.down = False
    live.run_once()
    assert live._pipeline.committer.resume_from(partition) == 50


def test_the_adapter_refuses_to_turn_a_missing_score_into_zero() -> None:
    adapter = MlWindowAdapter(_FakeMl())
    adapter._client.down = True  # type: ignore[attr-defined]
    window = _window_of_50()
    with pytest.raises(ScoringUnavailable):
        adapter.score(window)


def test_an_empty_publish_sends_nothing() -> None:
    publisher, _loop, broker = _live(_FakeMl())
    publisher.publish([])
    assert all(broker.end_offset(TOPIC, p) == 0 for p in range(6))


def test_the_ml_client_refuses_a_non_http_url() -> None:
    with pytest.raises(ValueError, match="http"):
        MlWindowScorer("ftp://ml-service:8001")


def _window_of_50() -> Any:
    """A real windower output: the records the worker would hand the scorer."""
    from aegis_ml.data.records import FlowRecord  # type: ignore[import-not-found]
    from aegis_ml.data.windowing import window_flows  # type: ignore[import-not-found]

    records = tuple(FlowRecord(**_flow(i).model_dump()) for i in range(50))
    [window] = list(window_flows(records, size=50))
    return window


# -- the ingest route, with a publisher wired ------------------------------------


class _RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str | None]] = []

    def publish(self, records: Any, *, traceparent: str | None = None) -> None:
        self.calls.append((len(records), traceparent))


class _SpyEngine:
    def __init__(self) -> None:
        self.fed: list[Any] = []

    def feed(self, records: list[dict[str, object]]) -> None:
        self.fed.extend(records)


def test_ingest_hands_flows_to_the_publisher_and_does_not_feed_the_in_process_engine(
    settings: Any,
) -> None:
    """With a publisher, the live consumer scores the flows: the engine must not see them too."""
    from app.auth.tokens import TokenService
    from app.main import create_app
    from fastapi.testclient import TestClient

    secret = "i" * 48
    auth = TokenService(secret)
    built = create_app(settings)
    built.state.token_service = auth
    publisher = _RecordingPublisher()
    engine = _SpyEngine()
    built.state.flow_publisher = publisher
    built.state.detection_engine = engine
    client = TestClient(built)

    body = "\n".join(_flow(i).model_dump_json() for i in range(3)).encode()
    pair = auth.issue("collector", "analyst")
    headers = {
        "Authorization": f"Bearer {pair.access_token}",
        "Content-Type": "application/x-ndjson",
        TRACEPARENT_HEADER: "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",  # pragma: allowlist secret  # noqa: E501
    }
    response = client.post("/api/v1/ingest/flows", content=body, headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["accepted"] == 3
    # The middleware keeps the client's trace and starts a child span, so the trace id
    # is the one the client sent while the span id is the request's own.
    [(count, traceparent)] = publisher.calls
    assert count == 3
    assert traceparent is not None
    assert (
        traceparent.split("-")[1]
        == "0123456789abcdef0123456789abcdef"  # pragma: allowlist secret  # noqa: E501
    )  # pragma: allowlist secret  # noqa: E501
    assert engine.fed == []


def test_client_kwargs_are_accepted_by_the_installed_kafka_client() -> None:
    """The real constructors reject unknown kwargs (kafka-python-ng asserts on them).

    The fake-client tests never reach the real constructor, so a config key the
    installed library does not support (enable_idempotence) only failed
    at the first ingest in the Docker image. Compare against the library's own
    DEFAULT_CONFIG so this fails offline.
    """
    import re

    import kafka  # type: ignore[import-untyped]

    source = (
        pathlib.Path(__file__).resolve().parents[1] / "app" / "messaging" / "kafka_bus.py"
    ).read_text()
    producer_kw = set(re.findall(r"KafkaProducer\(.*?\)", source, re.S))
    assert producer_kw, "KafkaProducer call not found"
    keys = set(re.findall(r"^\s+(\w+)=", next(iter(producer_kw)), re.M))
    unknown = keys - set(kafka.KafkaProducer.DEFAULT_CONFIG)
    assert not unknown, f"KafkaProducer kwargs unsupported by the installed client: {unknown}"

    consumer_kw = set(re.findall(r"KafkaConsumer\(.*?\)", source, re.S))
    assert consumer_kw, "KafkaConsumer call not found"
    keys = set(re.findall(r"^\s+(\w+)=", next(iter(consumer_kw)), re.M))
    unknown = keys - set(kafka.KafkaConsumer.DEFAULT_CONFIG)
    assert not unknown, f"KafkaConsumer kwargs unsupported by the installed client: {unknown}"


class _Admin:
    """A fake KafkaAdminClient: each create_topics call pops the next scripted outcome."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[list[object]] = []
        self.closed = 0

    def create_topics(self, topics: list[object]) -> object:
        self.calls.append(topics)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def close(self) -> None:
        self.closed += 1


def _response(*errors: tuple[str, int, str]) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(topic_errors=list(errors))


def _bus_with(admin: _Admin) -> KafkaBus:
    return KafkaBus("kafka:9092", admin_factory=lambda: admin)


def test_ensure_topic_creates_with_the_producer_partition_count() -> None:
    admin = _Admin([_response((TOPIC, 0, ""))])
    _bus_with(admin).ensure_topic(sleep=lambda _s: None)
    (topics,) = admin.calls
    (new_topic,) = topics
    assert new_topic.name == TOPIC
    assert new_topic.num_partitions == 6
    assert admin.closed == 1


def test_ensure_topic_accepts_an_existing_topic() -> None:
    """Restarts are routine: a topic that already exists is success, not an error."""
    admin = _Admin([_response((TOPIC, 36, "Topic 'flows.raw' already exists."))])
    _bus_with(admin).ensure_topic(sleep=lambda _s: None)
    assert len(admin.calls) == 1


def test_ensure_topic_retries_while_the_broker_starts() -> None:
    from kafka.errors import KafkaError  # type: ignore[import-untyped]

    sleeps: list[float] = []
    admin = _Admin(
        [
            KafkaError("NoBrokersAvailable"),
            KafkaError("NoBrokersAvailable"),
            _response((TOPIC, 0, "")),
        ]
    )
    _bus_with(admin).ensure_topic(attempts=5, delay_s=2.0, sleep=sleeps.append)
    assert len(admin.calls) == 3
    assert sleeps == [2.0, 2.0]
    assert admin.closed == 3


def test_ensure_topic_raises_when_a_topic_error_persists() -> None:
    admin = _Admin([_response((TOPIC, 37, "invalid partitions"))] * 2)
    with pytest.raises(KafkaBusError, match="code 37"):
        _bus_with(admin).ensure_topic(attempts=2, sleep=lambda _s: None)
    assert len(admin.calls) == 2
