"""T-317: Prometheus metrics and OpenTelemetry traces across the pipeline.

The acceptance criterion is a sentence about propagation -- "a trace ID from the
ingest response appears in the alert record" -- so the test that matters most
drives the whole chain through the real components: an ingest request through the
application, the trace context it returns, the scoring worker consuming a record
that carries that context, the correlator turning the score into a case, and the
alert row the query API reads back. Nothing in that chain is stubbed except the
parts that have no implementation to use yet (the Kafka transport, the model
service), and each of those says so where it lives.

The rest of the suite is about the ways telemetry goes wrong: a label that grows
without bound, a span that leaks the path a client chose, a counter that moves
for work that was refused, a trace id invented for a record that never had one,
and an exporter configured where none can be installed.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aegis_ml.scoring.fusion import fuse
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.main import create_app
from app.observability import metrics
from app.observability.tracing import (
    configure_tracing,
    context_from_traceparent,
    current_trace_id,
    current_traceparent,
    exporter_for,
    span,
    trace_id_from_traceparent,
    traceparent_for,
)
from app.schemas.ingest import FlowRecordIn
from app.schemas.query import AlertQuery
from app.services.alert_stream import AlertNotification
from app.services.correlator import (
    Correlator,
    Detection,
    InMemoryCaseStore,
    Modality,
    alert_row,
)
from app.services.limits import RateLimitPolicy
from app.services.query_service import paginate
from app.workers.scoring_worker import (
    ConsumedRecord,
    InMemoryScoreSink,
    ScoringWorker,
    WindowIdentity,
)
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import REGISTRY

SECRET = "t" * 48
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
FLOW = {
    "timestamp": "2026-03-15T10:00:00Z",
    "src_ip": "10.0.0.1",
    "dst_ip": "10.0.0.2",
    "src_port": 1234,
    "dst_port": 80,
    "protocol": "tcp",
    "direction": "inbound",
    "packets": 10,
    "src_packets": 5,
    "dst_packets": 5,
    "src_bytes": 1000,
    "dst_bytes": 2000,
    "duration": 1.5,
}

LOG = {
    "timestamp": "2026-03-15T10:00:00Z",
    "host": "web-01",
    "service": "sshd",
    "level": "info",
    "message": "Accepted publickey for alice",
}


@pytest.fixture(scope="module")
def spans() -> InMemorySpanExporter:
    """One exporter for the module, attached to the process tracer provider."""
    exporter = InMemorySpanExporter()
    configure_tracing(exporter)
    return exporter


@pytest.fixture
def exported(spans: InMemorySpanExporter) -> Iterator[InMemorySpanExporter]:
    """The exporter, emptied first so a test sees only its own spans."""
    spans.clear()
    yield spans


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> Iterator[TestClient]:
    app = create_app(settings)
    app.state.token_service = auth
    with TestClient(app) as test_client:
        yield test_client


def headers(auth: TokenService, role: str = "analyst") -> dict[str, str]:
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def sample(name: str, **labels: str) -> float:
    """One series of a metric, read the way a Prometheus scrape reads it."""
    return REGISTRY.get_sample_value(name, labels) or 0.0


def exposed_series(name: str, **labels: str) -> list[str]:
    """The exposed series of a metric whose label set contains these labels.

    A value cannot say whether a series exists -- an absent series reads as zero,
    which is exactly what a counter that was never incremented reads as -- so the
    zero-skip property is asserted against the series themselves.
    """
    wanted = tuple(sorted(labels.items()))
    found = []
    for metric in REGISTRY.collect():
        for member in metric.samples:
            if member.name != name:
                continue
            if all(member.labels.get(key) == value for key, value in wanted):
                found.append(member.labels.get("stage", ""))
    return found


# --- trace context ------------------------------------------------------------


def test_a_span_produces_a_usable_traceparent(exported: InMemorySpanExporter) -> None:
    with span("unit") as active:
        header = traceparent_for(active)
        assert header is not None
        version, trace_id, parent_id, flags = header.split("-")
        assert version == "00"
        assert int(flags, 16) & 1, "the sampled bit is set, and other bits are the span's own"
        assert len(trace_id) == 32 and int(trace_id, 16) > 0
        assert len(parent_id) == 16
        assert trace_id_from_traceparent(header) == trace_id


def test_the_current_context_is_readable_from_anywhere(exported: InMemorySpanExporter) -> None:
    assert current_traceparent() is None
    assert current_trace_id() is None
    with span("context") as active:
        assert current_traceparent() == traceparent_for(active)
        assert current_trace_id() == trace_id_from_traceparent(traceparent_for(active))


def test_a_span_that_is_not_recording_has_no_traceparent() -> None:
    """A span with no provider must not produce a header: invented ids look exported."""
    from opentelemetry.trace import NonRecordingSpan, SpanContext

    assert traceparent_for(None) is None
    invalid = NonRecordingSpan(SpanContext(trace_id=0, span_id=0, is_remote=False))
    assert traceparent_for(invalid) is None


def test_a_child_span_lands_on_its_parents_trace(exported: InMemorySpanExporter) -> None:
    parent = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    with span("child", parent_traceparent=parent) as active:
        assert trace_id_from_traceparent(traceparent_for(active)) == "a" * 32


@pytest.mark.parametrize(
    "header",
    [
        "",
        "not-a-traceparent",
        "00-" + "0" * 32 + "-" + "b" * 16 + "-01",  # the standard's "invalid"
        "00-short-" + "b" * 16 + "-01",
    ],
)
def test_an_unusable_traceparent_is_ignored(header: str) -> None:
    """Ignored, not refused: refusing ingest over a broken header trades data for telemetry."""
    assert context_from_traceparent(header) is None
    assert trace_id_from_traceparent(header) is None


def test_a_future_traceparent_version_is_still_usable() -> None:
    """W3C lets a later version add fields, so 01 parses; an unknown shape does not."""
    header = "01-" + "a" * 32 + "-" + "b" * 16 + "-01"
    assert trace_id_from_traceparent(header) == "a" * 32


def test_the_tracer_is_created_lazily_when_nothing_configured_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A process that imports the tracer without an application still gets one."""
    from app.observability import tracing

    monkeypatch.setattr(tracing, "_provider", None)
    assert tracing.get_tracer() is not None


def test_a_malformed_traceparent_starts_a_fresh_trace(exported: InMemorySpanExporter) -> None:
    with span("fresh", parent_traceparent="garbage") as active:
        trace_id = trace_id_from_traceparent(traceparent_for(active))
        assert trace_id is not None and trace_id != "0" * 32


def test_the_provider_names_the_service_it_was_configured_with() -> None:
    """A span that does not say which service made it is a span without a home."""
    provider = configure_tracing()
    assert str(provider.resource.attributes["service.name"]).startswith("aegis-")


def test_configuring_tracing_twice_keeps_one_provider_and_one_exporter(
    spans: InMemorySpanExporter,
) -> None:
    """Two providers share a process by silently dropping half of the spans."""
    provider = configure_tracing()
    assert configure_tracing() is provider
    configure_tracing(spans)  # the exporter this module already attached
    spans.clear()
    with span("only once"):
        pass
    assert len(spans.get_finished_spans()) == 1, "the span was not exported twice"


def test_a_duration_never_goes_negative() -> None:
    """A clock that appears to run backwards must not put a negative in a histogram."""
    from app.observability.tracing import duration_seconds

    assert duration_seconds(time.perf_counter() + 5) == 0.0
    assert duration_seconds(time.perf_counter()) >= 0.0


def test_no_exporter_is_configured_by_default() -> None:
    """The ids are generated and propagated with nothing leaving the process."""
    assert exporter_for("") is None
    assert exporter_for("   ") is None


def test_the_application_hands_the_settings_to_tracing(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pinned separately from the spans: a tracer nobody configured exports nothing."""
    from app import main

    configured: list[dict[str, Any]] = []
    seen: list[str] = []

    def record_configure(exporter: Any = None, **options: Any) -> None:
        configured.append({"exporter": exporter, **options})

    monkeypatch.setattr(main, "configure_tracing", record_configure)
    monkeypatch.setattr(main, "exporter_for", lambda endpoint: seen.append(endpoint))
    resolved = settings.model_copy(update={"otel_exporter_endpoint": "http://collector:4318"})
    create_app(resolved)
    assert seen == ["http://collector:4318"]
    assert configured[0]["service_name"] == resolved.service_name


def test_an_endpoint_without_the_extra_fails_loudly() -> None:
    """A deployment that configures a collector but did not install the extra must know."""
    import importlib.util

    try:
        installed = (
            importlib.util.find_spec("opentelemetry.exporter.otlp.proto.http.trace_exporter")
            is not None
        )
    except ModuleNotFoundError:
        installed = False
    if installed:  # pragma: no cover - depends on the environment's extras
        pytest.skip("the OTLP exporter is installed here")
    with pytest.raises(RuntimeError, match="otlp"):
        exporter_for("http://collector:4318/v1/traces")


# --- the acceptance criterion -------------------------------------------------


class RecordingScorer:
    """A model service that always answers, and counts the calls."""

    def __init__(self, score: float = 0.95) -> None:
        """Return a fixed score, which the severity bands turn into an alert."""
        self.score_value = score
        self.calls = 0

    def score(self, window: Any) -> float:
        """Answer one window."""
        self.calls += 1
        return self.score_value


class ListConsumer:
    """A topic backed by a list: the offsets are what the worker resumes from."""

    def __init__(self, records: list[ConsumedRecord]) -> None:
        """Hold the records the worker will read."""
        self.records = records

    def read(self, partition: int, from_offset: int, limit: int) -> list[ConsumedRecord]:
        """Everything at or after the offset, up to the limit."""
        return [record for record in self.records if record.offset >= from_offset][:limit]


class DictCommitter:
    """Committed offsets in a dict, which is what survives a restart here."""

    def __init__(self) -> None:
        """Start with nothing committed."""
        self.committed: dict[int, int] = {}

    def commit(self, partition: int, offset: int) -> None:
        """Record progress."""
        self.committed[partition] = offset

    def resume_from(self, partition: int) -> int:
        """Where a restarted worker begins."""
        return self.committed.get(partition, -1) + 1


NOW = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)


class _OrmRow:
    """A stand-in for an `alerts` row, with only the columns the API reads."""

    def __init__(self, row: dict[str, Any]) -> None:
        """Fill the columns the query API reads from an alert_row payload."""
        self.id = 1
        self.created_at = NOW
        self.entity_id = row["entity_id"]
        self.family = row["family"]
        self.severity = row["severity"]
        self.score = row["score"]
        self.status = row["status"]
        self.first_seen = row["first_seen"]
        self.last_seen = row["last_seen"]
        self.occurrence_count = row["occurrence_count"]
        self.window_ref = row["window_ref"]


class RecordingSink(InMemoryScoreSink):
    """The in-memory sink, remembering the identities it was given."""

    def __init__(self) -> None:
        """Start empty, with no identities remembered."""
        super().__init__()
        self.identities: list[WindowIdentity] = []

    def put(
        self,
        identity: WindowIdentity,
        score: float,
        records: int,
        *,
        traceparent: str | None = None,
    ) -> None:
        """Store the score and keep the identity for the caller."""
        self.identities.append(identity)
        super().put(identity, score, records, traceparent=traceparent)


def test_a_trace_id_from_the_ingest_response_appears_in_the_alert_record(
    client: TestClient, auth: TokenService
) -> None:
    """T-317's acceptance criterion, driven end to end through the real pieces.

    The trace id is read from the ingest *response*; the same context then rides a
    consumed record into the scoring worker and the correlator, exactly as it will
    ride a Kafka header, and the alert row the query API reads back is asserted to
    carry that id.
    """
    granted = headers(auth)
    response = client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted)
    assert response.status_code == 200
    traceparent = response.headers["traceparent"]
    trace_id = response.headers["x-trace-id"]
    assert trace_id == trace_id_from_traceparent(traceparent)

    # 1. The record carries the context the ingest response named.
    record = ConsumedRecord(
        offset=0, partition=0, flow=FlowRecordIn(**FLOW), traceparent=traceparent
    )
    sink = RecordingSink()
    worker = ScoringWorker(RecordingScorer(), sink, DictCommitter(), window_size=1)
    worker.run(ListConsumer([record]), 0, max_batches=1)
    assert sink.identities, "the window was scored, so there is an identity to look up"
    identity = sink.identities[0]
    assert sink.traceparent_for(identity) == traceparent

    # 2. The detection built from that score carries the same context.
    correlator = Correlator(InMemoryCaseStore(), fuse)
    outcome = correlator.ingest(
        Detection(
            entity_id=7,
            family="DoS",
            modality=Modality.flow,
            score=0.95,
            at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
            evidence_id=identity.as_string(),
            traceparent=sink.traceparent_for(identity),
        )
    )
    assert outcome.case.trace_id == trace_id

    # 3. The alert record the pipeline persists carries it...
    row = alert_row(outcome.case)
    assert row["window_ref"]["trace_id"] == trace_id  # type: ignore[index]

    # 4. ...and the query API returns it, and the stream sends the same row.
    alert_query = AlertQuery(
        start=datetime(2026, 3, 1, tzinfo=UTC), end=datetime(2026, 4, 1, tzinfo=UTC)
    )
    page = paginate([_OrmRow(row)], alert_query)  # type: ignore[arg-type]
    assert page.items[0].trace_id == trace_id
    notification = AlertNotification(sequence=1, alert=page.items[0]).as_dict()
    assert notification["alert"]["trace_id"] == trace_id  # type: ignore[index]


def test_the_alert_row_is_read_back_only_when_it_has_a_trace() -> None:
    """An alert without a trace context reports a gap, not an invented id."""
    row = paginate(
        [_OrmRow(_component_row(window_ref={"store": "stream"}))],  # type: ignore[arg-type]
        _query(),
    )
    assert row.items[0].trace_id is None
    row = paginate(
        [_OrmRow(_component_row(window_ref={"trace_id": 1234}))],  # type: ignore[arg-type]
        _query(),
    )
    assert row.items[0].trace_id is None, "a non-string is not a trace id"
    row = paginate(
        [_OrmRow(_component_row(window_ref={"trace_id": ""}))],  # type: ignore[arg-type]
        _query(),
    )
    assert row.items[0].trace_id is None, "an empty string is not a trace id"
    row = paginate(
        [_OrmRow(_component_row(window_ref=None))],  # type: ignore[arg-type]
        _query(),
    )
    assert row.items[0].trace_id is None


def _query() -> AlertQuery:
    return AlertQuery(start=datetime(2026, 3, 1, tzinfo=UTC), end=datetime(2026, 4, 1, tzinfo=UTC))


def _component_row(window_ref: Any) -> dict[str, Any]:
    return {
        "entity_id": 7,
        "family": "DoS",
        "severity": "critical",
        "score": 0.95,
        "status": "open",
        "first_seen": NOW,
        "last_seen": NOW,
        "occurrence_count": 1,
        "window_ref": window_ref,
    }


def test_the_window_is_attributed_to_its_first_record() -> None:
    """A window can straddle two requests; the one that opened it is the origin."""
    first = "00-" + "3" * 32 + "-" + "4" * 16 + "-01"
    second = "00-" + "5" * 32 + "-" + "6" * 16 + "-01"
    records = [
        ConsumedRecord(offset=0, partition=0, flow=FlowRecordIn(**FLOW), traceparent=first),
        ConsumedRecord(offset=1, partition=0, flow=FlowRecordIn(**FLOW), traceparent=second),
    ]
    sink = RecordingSink()
    worker = ScoringWorker(RecordingScorer(), sink, DictCommitter(), window_size=2)
    worker.run(ListConsumer(records), 0, max_batches=1)
    assert sink.traceparent_for(sink.identities[0]) == first


def test_a_case_keeps_the_trace_of_the_occurrence_that_opened_it() -> None:
    """The question a trace answers is which request opened the alert."""
    opening = "00-" + "7" * 32 + "-" + "8" * 16 + "-01"
    later = "00-" + "9" * 32 + "-" + "a" * 16 + "-01"
    correlator = Correlator(InMemoryCaseStore(), fuse)
    correlator.ingest(_detection(traceparent=opening, evidence_id="flow:10.0.0.7@100", at=NOW))
    grouped = correlator.ingest(
        _detection(
            traceparent=later,
            evidence_id="log:10.0.0.7@200",
            modality=Modality.log,
            at=NOW + timedelta(seconds=30),
        )
    )
    assert grouped.case.trace_id == "7" * 32


def _detection(
    *,
    traceparent: str | None = None,
    evidence_id: str = "flow:10.0.0.7@100",
    modality: Modality = Modality.flow,
    at: datetime = NOW,
) -> Detection:
    """A correlated detection, with the fields this suite cares about."""
    return Detection(
        entity_id=7,
        family="DoS",
        modality=modality,
        score=0.95,
        at=at,
        evidence_id=evidence_id,
        traceparent=traceparent,
    )


# --- spans along the pipeline -------------------------------------------------


def test_the_score_is_a_child_span_of_the_records_trace(exported: InMemorySpanExporter) -> None:
    parent = "00-" + "c" * 32 + "-" + "d" * 16 + "-01"
    record = ConsumedRecord(offset=0, partition=0, flow=FlowRecordIn(**FLOW), traceparent=parent)
    worker = ScoringWorker(RecordingScorer(), InMemoryScoreSink(), DictCommitter(), window_size=1)
    worker.run(ListConsumer([record]), 0, max_batches=1)
    scored = [span for span in exported.get_finished_spans() if span.name == "score window"]
    assert len(scored) == 1
    assert trace_id_from_traceparent(parent) == format_trace(span=scored[0])
    assert scored[0].attributes["aegis.score"] == 0.95


def format_trace(*, span: Any) -> str:
    """The trace id of an exported span, in the same 32-hex form the API uses."""
    return f"{span.context.trace_id:032x}"


def test_correlation_is_a_span_on_the_detections_trace(exported: InMemorySpanExporter) -> None:
    parent = "00-" + "e" * 32 + "-" + "f" * 16 + "-01"
    correlator = Correlator(InMemoryCaseStore(), fuse)
    correlator.ingest(
        Detection(
            entity_id=7,
            family="DoS",
            modality=Modality.flow,
            score=0.95,
            at=NOW,
            evidence_id="flow:10.0.0.7@100",
            traceparent=parent,
        )
    )
    correlated = [
        span for span in exported.get_finished_spans() if span.name == "correlate detection"
    ]
    assert len(correlated) == 1
    assert format_trace(span=correlated[0]) == "e" * 32
    assert correlated[0].attributes["aegis.correlator.action"] == "created"


# --- metrics ------------------------------------------------------------------


def test_the_domain_metrics_are_the_ones_the_architecture_names() -> None:
    """The names are the architecture's list, because a dashboard is written against them."""
    from app.messaging.lag import CONSUMER_LAG

    names = metrics.metric_label_names()
    assert {
        "aegis_flows_ingested_total",
        "aegis_score_latency_seconds",
        "aegis_alerts_created_total",
        "aegis_drift_psi",
    } <= set(names)
    assert CONSUMER_LAG._name == "aegis_kafka_consumer_lag"  # noqa: SLF001


def test_every_metric_label_is_a_bounded_vocabulary() -> None:
    """A label whose value comes from the request is a way to grow without bound."""
    allowed = {
        "modality",
        "stage",
        "severity",
        "feature",
        "method",
        "route",
        "status",
        "group",
        "topic",
        "partition",
    }
    for name, labels in metrics.metric_label_names().items():
        assert set(labels) <= allowed, f"{name} carries an unreviewed label: {labels}"
        assert not any(label in labels for label in ("path", "user", "token", "ip", "trace_id"))


def test_a_record_with_several_bad_fields_is_one_rejection(
    client: TestClient, auth: TokenService
) -> None:
    """The counter's unit is the record: pydantic reports one error per field."""
    before = sample("aegis_records_rejected_total", modality="flow", stage="validation")
    response = client.post(
        "/api/v1/ingest/flows", json=[{"src_ip": "10.0.0.1"}], headers=headers(auth)
    )
    assert response.status_code == 200
    assert response.json()["rejected"] == 1
    assert len(response.json()["errors"]) > 1, "the record failed several fields"
    assert (
        sample("aegis_records_rejected_total", modality="flow", stage="validation") == before + 1
    ), "one record, one rejection"


def test_an_ingest_batch_moves_the_counters_by_what_it_did(
    client: TestClient, auth: TokenService
) -> None:
    before_ok = sample("aegis_flows_ingested_total", modality="flow")
    before_bad = sample("aegis_records_rejected_total", modality="flow", stage="validation")
    response = client.post(
        "/api/v1/ingest/flows", json=[FLOW, {"src_ip": "10.0.0.1"}], headers=headers(auth)
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 1
    assert sample("aegis_flows_ingested_total", modality="flow") == before_ok + 1
    assert (
        sample("aegis_records_rejected_total", modality="flow", stage="validation")
        == before_bad + 1
    )


def test_logs_are_counted_under_their_own_modality(client: TestClient, auth: TokenService) -> None:
    """One counter, two modalities: a log line must not be counted as a flow."""
    before_flow = sample("aegis_flows_ingested_total", modality="flow")
    before_log = sample("aegis_flows_ingested_total", modality="log")
    response = client.post(
        "/api/v1/ingest/logs",
        json=[LOG],
        headers=headers(auth),
    )
    assert response.status_code == 200 and response.json()["accepted"] == 1
    assert sample("aegis_flows_ingested_total", modality="log") == before_log + 1
    assert sample("aegis_flows_ingested_total", modality="flow") == before_flow


def test_a_refused_batch_counts_its_rejections_but_not_as_ingested(
    client: TestClient, auth: TokenService
) -> None:
    client.app.state.admission.admit(client.app.state.admission.capacity)  # type: ignore[attr-defined]
    before_ok = sample("aegis_flows_ingested_total", modality="flow")
    before_bad = sample("aegis_records_rejected_total", modality="flow", stage="validation")
    response = client.post(
        "/api/v1/ingest/flows", json=[FLOW, {"src_ip": "10.0.0.1"}], headers=headers(auth)
    )
    assert response.status_code == 503
    assert sample("aegis_flows_ingested_total", modality="flow") == before_ok, (
        "records the buffer refused are not ingested, and counting them would make the "
        "dashboard claim work that will be retried"
    )
    assert (
        sample("aegis_records_rejected_total", modality="flow", stage="validation")
        == before_bad + 1
    )


def test_the_score_latency_histogram_records_every_window() -> None:
    before = sample("aegis_score_latency_seconds_count")
    record = ConsumedRecord(offset=0, partition=0, flow=FlowRecordIn(**FLOW))
    worker = ScoringWorker(RecordingScorer(), InMemoryScoreSink(), DictCommitter(), window_size=1)
    worker.run(ListConsumer([record]), 0, max_batches=1)
    assert sample("aegis_score_latency_seconds_count") == before + 1


def test_only_a_created_alert_moves_the_created_counter() -> None:
    """The band comes from the case, and a repeat is not a new alert (FR-15).

    The score is deliberately mid-band: a counter labelled with a hard-coded
    ``critical`` would still move for a case that opened lower.
    """
    correlator = Correlator(InMemoryCaseStore(), fuse)
    detection = Detection(
        entity_id=7,
        family="DoS",
        modality=Modality.flow,
        score=0.80,
        at=NOW,
        evidence_id="flow:10.0.0.7@100",
    )
    outcome = correlator.ingest(detection)
    band = outcome.case.severity.value
    after_create = sample("aegis_alerts_created_total", severity=band)
    assert after_create >= 1
    correlator.ingest(detection)  # the same evidence again: a duplicate, not a new alert
    assert sample("aegis_alerts_created_total", severity=band) == after_create


def test_drift_psi_is_a_gauge_and_negative_values_are_refused() -> None:
    metrics.observe_drift_psi("state", 26.667)
    assert sample("aegis_drift_psi", feature="state") == 26.667
    with pytest.raises(ValueError, match="cannot be negative"):
        metrics.observe_drift_psi("state", -0.1)


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: metrics.observe_ingest("packets", accepted=1, rejected={}), "unknown modality"),
        (lambda: metrics.observe_ingest("flow", accepted=-1, rejected={}), "cannot be negative"),
        (
            lambda: metrics.observe_ingest("flow", accepted=0, rejected={"parse": -2}),
            "cannot be negative",
        ),
        (lambda: metrics.observe_score_latency(-0.5), "cannot be negative"),
        (lambda: metrics.observe_http_request("GET", "/x", 200, -1.0), "cannot be negative"),
    ],
)
def test_a_nonsense_measurement_is_refused(call: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        call()


def test_a_stage_that_refused_nothing_creates_no_series() -> None:
    """Zero counts are skipped: a series per stage that never fired is noise.

    Asserted against the exposed series rather than against the value, because a
    series that was never created and a counter that was incremented by zero both
    read as zero -- only one of them is a memory cost in the scrape.
    """
    assert not exposed_series("aegis_records_rejected_total", modality="log", stage="schema")
    metrics.observe_ingest("log", accepted=0, rejected={"schema": 0})
    assert not exposed_series("aegis_records_rejected_total", modality="log", stage="schema")
    metrics.observe_ingest("log", accepted=0, rejected={"schema": 2})
    assert exposed_series("aegis_records_rejected_total", modality="log", stage="schema")


# --- golden signals and the scrape endpoint -----------------------------------


def test_metrics_are_served_in_the_exposition_format(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "# TYPE aegis_flows_ingested_total counter" in body
    assert "# TYPE aegis_score_latency_seconds histogram" in body
    assert "aegis_kafka_consumer_lag" in body


def test_the_scrape_is_not_counted_as_request_traffic(client: TestClient) -> None:
    before = sample("aegis_http_requests_total", method="GET", route="/metrics", status="200")
    client.get("/metrics")
    client.get("/metrics")
    assert (
        sample("aegis_http_requests_total", method="GET", route="/metrics", status="200") == before
    )


def test_a_request_is_counted_against_its_route_template(
    client: TestClient, auth: TokenService
) -> None:
    before = sample("aegis_http_requests_total", method="GET", route="/api/v1/alerts", status="422")
    response = client.get("/api/v1/alerts", headers=headers(auth))
    assert response.status_code == 422, "the fixture sends no window, so the schema refuses it"
    assert (
        sample("aegis_http_requests_total", method="GET", route="/api/v1/alerts", status="422")
        == before + 1
    )


def test_an_unmatched_path_collapses_into_one_series(client: TestClient) -> None:
    before = sample("aegis_http_requests_total", method="GET", route="unmatched", status="404")
    client.get("/definitely-not-a-route-1")
    client.get("/definitely-not-a-route-2")
    assert (
        sample("aegis_http_requests_total", method="GET", route="unmatched", status="404")
        == before + 2
    )
    body = client.get("/metrics").text
    assert "definitely-not-a-route" not in body, "the path a client chose never becomes a label"


def test_the_refusals_are_traced_and_counted_too(client: TestClient, auth: TokenService) -> None:
    """A 429 is a request the service handled: it is measured, and it is traceable."""
    client.app.state.rate_limit_policy = RateLimitPolicy(  # type: ignore[attr-defined]
        credential_per_minute=1, anonymous_per_minute=1, secret=APP_SECRET
    )
    # The limiter answers *before* routing, so no route template exists to label
    # the refusal with: it lands on the single unmatched series, and the status
    # label is what distinguishes a refusal from a 404.
    before = sample("aegis_http_requests_total", method="POST", route="unmatched", status="429")
    granted = headers(auth)
    assert client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted).status_code == 200
    refused = client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted)
    assert refused.status_code == 429
    assert refused.headers["x-trace-id"]
    assert (
        sample("aegis_http_requests_total", method="POST", route="unmatched", status="429")
        == before + 1
    )


def test_a_body_cap_refusal_is_counted_as_a_413(client: TestClient, auth: TokenService) -> None:
    client.app.state.max_request_bytes = 64  # type: ignore[attr-defined]
    before = sample("aegis_http_requests_total", method="POST", route="unmatched", status="413")
    response = client.post(
        "/api/v1/ingest/flows",
        content=b"[" + b" " * 4096 + b"]",
        headers={**headers(auth), "content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.headers["x-trace-id"]
    assert (
        sample("aegis_http_requests_total", method="POST", route="unmatched", status="413")
        == before + 1
    )


def test_the_response_carries_the_callers_trace(client: TestClient) -> None:
    parent = "00-" + "1" * 32 + "-" + "2" * 16 + "-01"
    response = client.get("/healthz", headers={"traceparent": parent})
    assert response.status_code == 200
    assert response.headers["x-trace-id"] == "1" * 32
    assert response.headers["traceparent"].split("-")[1] == "1" * 32


def test_a_malformed_traceparent_does_not_fail_the_request(client: TestClient) -> None:
    response = client.get("/healthz", headers={"traceparent": "garbage"})
    assert response.status_code == 200
    trace_id = response.headers["x-trace-id"]
    assert trace_id != "0" * 32 and len(trace_id) == 32


def test_a_request_without_a_trace_context_gets_no_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard is exercised directly: with no provider there is nothing to stamp."""
    from app.api import middleware

    monkeypatch.setattr(middleware, "traceparent_for", lambda span=None: None)
    sent = _drive_tracing({"type": "http", "method": "GET", "path": "/healthz", "headers": []})
    assert status_of(sent) == 200
    assert all(name != b"traceparent" for name, _value in _headers_of(sent))


async def _ok_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """A minimal ASGI application that answers 200."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _drive_tracing(scope: dict[str, Any]) -> list[dict[str, Any]]:
    """Run one request through the tracing middleware alone."""
    import asyncio

    from app.api.middleware import TracingMiddleware

    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b""}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(TracingMiddleware(_ok_app)(scope, receive, send))
    return sent


def status_of(sent: list[dict[str, Any]]) -> int:
    return next(message["status"] for message in sent if message["type"] == "http.response.start")


def _headers_of(sent: list[dict[str, Any]]) -> list[tuple[bytes, bytes]]:
    for message in sent:
        if message["type"] == "http.response.start":
            return list(message["headers"])
    return []


async def _silent_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """An application that answers a request with nothing at all."""


async def _failing_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """An application that raises before it can answer."""
    msg = "boom"
    raise RuntimeError(msg)


def _drive_metrics(app: Any, *, method: str = "GET", path: str = "/x") -> None:
    """Run one request through the metrics middleware alone."""
    import asyncio

    from app.api.middleware import MetricsMiddleware

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b""}

    async def send(message: dict[str, Any]) -> None:
        return None

    scope = {"type": "http", "method": method, "path": path, "headers": []}
    asyncio.run(MetricsMiddleware(app)(scope, receive, send))


def test_a_request_that_never_answered_is_counted_as_a_500() -> None:
    """A connection that closes with no status is a failure, not a success.

    The method arrives lower-cased, as a proxy may send it: the series a dashboard
    queries is the upper-case one the API actually serves.
    """
    before = sample("aegis_http_requests_total", method="GET", route="unmatched", status="500")
    durations = sample("aegis_http_request_duration_seconds_count", method="GET", route="unmatched")
    _drive_metrics(_silent_app, method="get")
    assert (
        sample("aegis_http_requests_total", method="GET", route="unmatched", status="500")
        == before + 1
    )
    assert (
        sample("aegis_http_request_duration_seconds_count", method="GET", route="unmatched")
        == durations + 1
    )


def test_a_request_that_raised_is_measured_before_the_error_propagates() -> None:
    """The time a failed request cost is exactly the time worth seeing."""
    before = sample("aegis_http_requests_total", method="GET", route="unmatched", status="500")
    with pytest.raises(RuntimeError, match="boom"):
        _drive_metrics(_failing_app)
    assert (
        sample("aegis_http_requests_total", method="GET", route="unmatched", status="500")
        == before + 1
    )


def test_the_span_is_named_for_the_route_that_answered(
    client: TestClient, exported: InMemorySpanExporter
) -> None:
    """A name is what makes a trace searchable; the path a client chose is not."""
    client.get("/healthz")
    finished = {finished.name: finished for finished in exported.get_finished_spans()}
    assert "GET /healthz" in finished, "the span is renamed once the router chose a route"
    span_attributes = finished["GET /healthz"].attributes
    assert span_attributes["http.route"] == "/healthz"
    assert span_attributes["http.request.method"] == "GET"
    assert span_attributes["http.response.status_code"] == 200
    assert all("/healthz" not in name or name.startswith("GET ") for name in finished)


def test_a_request_produces_exactly_one_server_span(
    client: TestClient, exported: InMemorySpanExporter
) -> None:
    """The application instruments itself; the framework's native telemetry is off.

    FastAPI >= 0.142 traces every request on its own if it is not told otherwise,
    which would put two identically named server spans on one trace and give a
    deployment a second exporter configured from ``OTEL_*`` environment variables.
    """
    client.get("/healthz")
    names = [finished.name for finished in exported.get_finished_spans()]
    assert names.count("GET /healthz") == 1, names


def test_the_metrics_route_is_rate_limited_like_every_unauthenticated_route(
    client: TestClient,
) -> None:
    """R-56 covers it because it is unauthenticated; the scrape is not exempt."""
    client.app.state.rate_limit_policy = RateLimitPolicy(  # type: ignore[attr-defined]
        credential_per_minute=1, anonymous_per_minute=1, secret=APP_SECRET
    )
    assert client.get("/metrics").status_code == 200
    assert client.get("/metrics").status_code == 429


def test_the_metrics_endpoint_exposes_no_identifiers(
    client: TestClient, auth: TokenService
) -> None:
    """R-58: a scrape is readable by anyone in the network, so it carries no data."""
    granted = headers(auth)
    client.post("/api/v1/ingest/flows", json=[FLOW], headers=granted)
    body = client.get("/metrics").text
    assert "10.0.0.1" not in body
    assert "10.0.0.2" not in body
    assert granted["Authorization"].split()[1] not in body
    for value in ("corp", "analyst", "DoS", "Reconnaissance"):
        assert value not in body
