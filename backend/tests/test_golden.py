"""T-319: the golden path -- synthetic traffic in, an alert out of the API (R-88).

R-88 asks for one test that runs the whole path and passes in CI without
Docker-in-Docker. So this file drives the real application over real HTTP --
ingest validation, admission, the audit row, the trace context on the response --
through the real producer, consumer and windower, into the real correlator, and
reads the result back through the real query route. The only fakes are the two
systems this environment does not have, and both sit at the external system's
boundary rather than inside the logic under test: the broker
(:class:`~app.pipeline.InProcessBus`, a log per partition) and the alert store
(:class:`~app.services.alert_store.InMemoryAlertStore`).

What the assertions are for, in order:

* the batch arithmetic (FR-04) survives the trip: what the route accepted is what
  reached the bus, and a line that was rejected never does;
* the score came from the window the worker built -- the scorer derives it from
  the records it is handed, so a worker that windowed the wrong records would
  produce a different number;
* the alert is visible through ``GET /api/v1/alerts``, with the severity the real
  fusion rule produces and the trace id of the request that ingested the traffic
  (T-317's criterion, end to end rather than stage by stage);
* a consumer that lost its committed offsets re-reads the same windows and the
  row the analyst is looking at does not change, which is T-307's idempotence
  asserted at the end of the pipeline instead of at the sink.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from aegis_ml.data.records import FlowRecord
from aegis_ml.data.windowing import Window
from aegis_ml.scoring.fusion import fuse
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.db.models import AlertStatus
from app.main import create_app
from app.messaging.partitioner import FLOW_TOPIC, partition_for
from app.messaging.producer import FlowProducer
from app.pipeline import InProcessBus, Pipeline, build_pipeline
from app.services.alert_store import InMemoryAlertStore
from app.services.correlator import Correlator
from app.workers.scoring_worker import ScoringWorker, WindowIdentity
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

SECRET = "g" * 48
#: The family the golden path's labeler attributes. No attributed classifier is
#: wired yet, so the label is injected; D-053 records that gap.
FAMILY = "port_scan"
SCAN_SOURCE = "10.0.0.9"
BENIGN_SOURCE = "10.0.0.5"
SCAN_FLOWS = 60
BENIGN_FLOWS = 5
WINDOW_SIZE = 50
PARTITIONS = 3
START = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)
#: Client libraries for the systems the golden test must not need. ``kafka``
#: (kafka-python) is deliberately not in this set: T-306's suite imports its pure
#: partitioner to compare against ours, and importing it dials nothing.
UNNEEDED_CLIENTS = frozenset(
    {"confluent_kafka", "elasticsearch", "opensearchpy", "psycopg", "psycopg2", "asyncpg"}
)


def flow(src_ip: str, index: int, dst_port: int) -> dict[str, object]:
    """One `flow@1` record, one second after the previous one from this source."""
    return {
        "schema_version": "flow@1",
        "timestamp": (START + timedelta(seconds=index)).isoformat().replace("+00:00", "Z"),
        "src_ip": src_ip,
        "dst_ip": "10.0.0.2",
        "src_port": 40000 + index,
        "dst_port": dst_port,
        "protocol": "tcp",
        "direction": "outbound",
        "packets": 10,
        "src_packets": 5,
        "dst_packets": 5,
        "src_bytes": 1000,
        "dst_bytes": 2000,
        "duration": 1.5,
        "state": "S0",
    }


def scan_traffic() -> list[dict[str, object]]:
    """Sixty flows from one source, one destination port each (FR-01's shape)."""
    return [flow(SCAN_SOURCE, index, 1000 + index) for index in range(SCAN_FLOWS)]


def benign_traffic() -> list[dict[str, object]]:
    """Five flows from another source, all to one port."""
    return [flow(BENIGN_SOURCE, index, 80) for index in range(BENIGN_FLOWS)]


def _granted(auth: TokenService, role: str = "analyst") -> dict[str, str]:
    """A bearer token for a role that may ingest and read."""
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def ndjson(records: Sequence[object]) -> str:
    """Render records as the NDJSON a collector sends."""
    return "\n".join(
        record if isinstance(record, str) else json.dumps(record) for record in records
    )


class PortScanScorer:
    """A scorer whose number comes from the window it was given (T-319).

    Content-derived on purpose: a constant would let the test pass even if the
    worker handed it the wrong records. The rule is "how many distinct
    destination ports per window", which is what the synthetic traffic is shaped
    like, and it keeps the golden test free of a model artifact.
    """

    def __init__(self) -> None:
        """Start with no windows seen."""
        self.windows: list[Window[FlowRecord]] = []

    def score(self, window: Window[FlowRecord]) -> float:
        """Return the fraction of the window that is distinct destination ports."""
        self.windows.append(window)
        ports = {record.dst_port for record in window.records}
        return min(1.0, len(ports) / WINDOW_SIZE)


@dataclass(slots=True)
class GoldenRun:
    """The wired path, plus what a test needs to drive and inspect it."""

    app: FastAPI
    client: TestClient
    pipeline: Pipeline
    scorer: PortScanScorer
    alerts: InMemoryAlertStore
    auth: TokenService

    def granted(self, role: str = "analyst") -> dict[str, str]:
        """A bearer token for a role that may ingest and read."""
        return _granted(self.auth, role)

    def ingest(self, body: str, *, granted: dict[str, str]) -> Response:
        """POST an NDJSON batch through the real ingest route."""
        return self.client.post(
            "/api/v1/ingest/flows",
            content=body.encode(),
            headers={"content-type": "application/x-ndjson", **granted},
        )

    def alerts_via_api(self, granted: dict[str, str], **filters: str) -> Response:
        """GET the alerts the API returns for a window around now."""
        now = datetime.now(UTC)
        params: dict[str, str] = {
            "start": (now - timedelta(hours=1)).isoformat(),
            "end": (now + timedelta(hours=1)).isoformat(),
            **filters,
        }
        return self.client.get("/api/v1/alerts", params=params, headers=granted)


@pytest.fixture
def golden(settings: Settings) -> Iterator[GoldenRun]:
    """Build the application and wire the in-process pipeline into it."""
    app = create_app(settings)
    app.state.token_service = TokenService(SECRET)
    store = app.state.alert_store
    assert isinstance(store, InMemoryAlertStore)
    scorer = PortScanScorer()
    pipeline = build_pipeline(
        scorer,
        fuse=fuse,
        alerts=store,
        hub=app.state.alert_hub,
        label_family=lambda _identity: FAMILY,
        model_id="flow@1+t319",
        partitions=PARTITIONS,
        window_size=WINDOW_SIZE,
    )
    # The composition root's seam, and the only wiring these tests add (T-319).
    app.state.flow_publisher = pipeline
    with TestClient(app) as client:
        yield GoldenRun(
            app=app,
            client=client,
            pipeline=pipeline,
            scorer=scorer,
            alerts=store,
            auth=app.state.token_service,
        )


def test_the_golden_path_from_traffic_to_a_visible_alert(golden: GoldenRun) -> None:
    """R-88's path: ingest over HTTP, score, correlate, and read the alert back."""
    granted = golden.granted()

    response = golden.ingest(ndjson([*scan_traffic(), *benign_traffic()]), granted=granted)
    assert response.status_code == 200
    counts = response.json()
    assert counts["received"] == SCAN_FLOWS + BENIGN_FLOWS
    assert counts["accepted"] == SCAN_FLOWS + BENIGN_FLOWS
    assert counts["rejected"] == 0
    trace_id = response.headers["x-trace-id"]
    assert len(trace_id) == 32

    # The route handed on exactly what it accepted, and the real producer put every
    # flow of one source in one partition.
    assert golden.pipeline.bus.count() == SCAN_FLOWS + BENIGN_FLOWS
    # The real partition function put each source where its ordering is preserved,
    # and both sources went to different partitions -- the bus is a broker, so this
    # is asserted on the bus rather than assumed from the producer's return value.
    assert {
        partition: golden.pipeline.bus.end_offset(FLOW_TOPIC, partition)
        for partition in range(golden.pipeline.bus.partitions)
    } == {
        partition_for(SCAN_SOURCE, PARTITIONS): SCAN_FLOWS,
        partition_for(BENIGN_SOURCE, PARTITIONS): BENIGN_FLOWS,
        0: 0,
    }
    assert golden.pipeline.drain() == SCAN_FLOWS + BENIGN_FLOWS

    # The worker built the windows from the records that travelled: 60 scan flows
    # cut into 50 + 10, and the benign five into one end-of-stream window. Sources
    # may arrive in any order -- partitions drain one after another -- but one
    # source's windows keep their order.
    lengths: dict[str, list[int]] = {}
    for window in golden.scorer.windows:
        lengths.setdefault(str(window.key), []).append(len(window.records))
    assert lengths == {
        SCAN_SOURCE: [WINDOW_SIZE, SCAN_FLOWS - WINDOW_SIZE],
        BENIGN_SOURCE: [BENIGN_FLOWS],
    }

    page = golden.alerts_via_api(granted)
    assert page.status_code == 200
    items = page.json()["items"]
    assert {item["family"] for item in items} == {FAMILY}

    scanned_id = golden.pipeline.registry.id_for("source", SCAN_SOURCE)
    benign_id = golden.pipeline.registry.id_for("source", BENIGN_SOURCE)
    by_entity = {item["entity_id"]: item for item in items}
    assert set(by_entity) == {scanned_id, benign_id}

    scanned = by_entity[scanned_id]
    # The real fusion rule penalises a single modality by a quarter, so a perfect
    # flow score becomes 0.75 -- the `high` band, not `critical`.
    assert scanned["score"] == pytest.approx(0.75)
    assert scanned["severity"] == "high"
    assert scanned["status"] == "open"
    # 50 + 10 records of one incident: two detections, one row (FR-15).
    assert scanned["occurrence_count"] == 2
    assert scanned["trace_id"] == trace_id

    benign = by_entity[benign_id]
    assert benign["severity"] == "info"
    assert benign["occurrence_count"] == 1
    assert benign["trace_id"] == trace_id

    # The row behind the API response is the case the windower's offsets produced.
    row = next(stored for stored in golden.alerts.rows() if stored.entity_id == scanned_id)
    window_ref = row.window_ref
    assert isinstance(window_ref, dict)
    evidence = window_ref["evidence"]
    assert isinstance(evidence, list)
    assert [item["id"] for item in evidence] == [
        f"source:{SCAN_SOURCE}@0",
        f"source:{SCAN_SOURCE}@{WINDOW_SIZE}",
    ]
    # Which model, which modality, from where: the evidence trail says what the
    # alert was built from, not just how many things it saw.
    assert {item["modality"] for item in evidence} == {"flow"}
    assert {item["model"] for item in evidence} == {"flow@1+t319"}
    assert window_ref["trace_id"] == trace_id
    assert isinstance(row.status, AlertStatus)

    # Two alerts, but three announcements: the incident was created, the other
    # entity's alert was created, and the first one absorbed its second window.
    assert len(golden.alerts) == 2
    # Cursor 0 is the "no position yet" the stream documents: send me the retained
    # window.
    catch_up = golden.app.state.alert_hub.catch_up(0)
    assert [item.sequence for item in catch_up.items] == [1, 2, 3]
    assert catch_up.items[2].alert.entity_id == scanned_id


def test_only_the_records_a_batch_accepted_reach_the_bus(golden: GoldenRun) -> None:
    """FR-04's arithmetic is the pipeline's contract too: a rejected line is dropped."""
    granted = golden.granted()
    body = ndjson([*scan_traffic(), "{ this is not a record", *benign_traffic()])

    response = golden.ingest(body, granted=granted)

    assert response.status_code == 200
    counts = response.json()
    assert counts["received"] == SCAN_FLOWS + BENIGN_FLOWS + 1
    assert counts["accepted"] == SCAN_FLOWS + BENIGN_FLOWS
    assert counts["rejected"] == 1
    # The bad line was the 61st, and it never reached the bus.
    assert counts["errors"][0]["index"] == SCAN_FLOWS
    assert golden.pipeline.bus.count() == SCAN_FLOWS + BENIGN_FLOWS


def test_a_replayed_offset_range_does_not_double_count(golden: GoldenRun) -> None:
    """T-307's idempotence asserted at the alert row, not at the sink."""
    granted = golden.granted()
    golden.ingest(ndjson([*scan_traffic(), *benign_traffic()]), granted=granted)
    assert golden.pipeline.drain() == SCAN_FLOWS + BENIGN_FLOWS
    before = {
        stored.id: (stored.occurrence_count, stored.score, stored.window_ref)
        for stored in golden.alerts.rows()
    }
    announced = golden.app.state.alert_hub.catch_up(0).latest

    # A consumer that lost its committed offsets resumes at zero and re-reads the
    # same windows. The evidence ids are the same, so every detection is a
    # duplicate and no row moves.
    golden.pipeline.committer.committed.clear()
    assert golden.pipeline.drain() == SCAN_FLOWS + BENIGN_FLOWS

    after = {
        stored.id: (stored.occurrence_count, stored.score, stored.window_ref)
        for stored in golden.alerts.rows()
    }
    assert after == before
    assert golden.app.state.alert_hub.catch_up().latest == announced


def test_the_golden_path_composes_real_stages_over_in_process_fakes(golden: GoldenRun) -> None:
    """R-88's "no Docker-in-Docker" is a property of what is composed, asserted."""
    assert isinstance(golden.pipeline.bus, InProcessBus)
    assert isinstance(golden.alerts, InMemoryAlertStore)
    # The stages between the fakes are the production ones, not test doubles.
    assert isinstance(golden.pipeline.producer, FlowProducer)
    assert isinstance(golden.pipeline.worker, ScoringWorker)
    assert isinstance(golden.pipeline.correlator, Correlator)
    # And no client for the two systems R-88 names has been imported to run it.
    assert UNNEEDED_CLIENTS.isdisjoint(sys.modules)


def test_the_api_refuses_a_window_it_cannot_bound(golden: GoldenRun) -> None:
    """R-34 survives the seam: the store is asked for a bounded window or nothing."""
    granted = golden.granted()
    naive = golden.client.get(
        "/api/v1/alerts",
        params={"start": "2026-10-05T12:00:00", "end": "2026-10-05T13:00:00"},
        headers=granted,
    )
    assert naive.status_code == 400
    assert "timezone" in naive.json()["detail"]


def test_the_scored_window_is_dated_from_its_own_records(golden: GoldenRun) -> None:
    """An alert's times are the traffic's, not the worker's clock (T-319)."""
    granted = golden.granted()
    golden.ingest(ndjson(scan_traffic()), granted=granted)
    golden.pipeline.drain()

    row = golden.alerts.rows()[0]
    # A detection is dated by when its window closed (T-308's ``Detection.at``),
    # because that is the moment the window existed as evidence: the first window
    # ends at record 49, and the second moves ``last_seen`` to record 59.
    assert row.first_seen == START + timedelta(seconds=WINDOW_SIZE - 1)
    assert row.last_seen == START + timedelta(seconds=SCAN_FLOWS - 1)
    # The row's creation time is the pipeline's clock; ``first_seen`` is the
    # traffic's. One is not the other, which is the point of carrying both.
    assert START < row.created_at <= datetime.now(UTC)


def test_an_identity_with_no_close_time_is_refused(golden: GoldenRun) -> None:
    """The sink refuses to invent a time: a replay would move the incident's start."""
    with pytest.raises(ValueError, match="close time"):
        golden.pipeline.sink.put(
            WindowIdentity(key=SCAN_SOURCE, key_kind="source", first_offset=0), 0.9, WINDOW_SIZE
        )


def test_the_query_api_applies_the_filters_and_the_cursor(golden: GoldenRun) -> None:
    """The in-memory store re-states the SQL predicates, so they are asserted too."""
    granted = golden.granted()
    golden.ingest(ndjson([*scan_traffic(), *benign_traffic()]), granted=granted)
    golden.pipeline.drain()

    assert len(golden.alerts_via_api(granted, family=FAMILY).json()["items"]) == 2
    assert golden.alerts_via_api(granted, family="exfiltration").json()["items"] == []
    assert len(golden.alerts_via_api(granted, severity="high").json()["items"]) == 1
    assert len(golden.alerts_via_api(granted, min_score="0.5").json()["items"]) == 1
    benign_id = golden.pipeline.registry.id_for("source", BENIGN_SOURCE)
    assert len(golden.alerts_via_api(granted, entity_id=str(benign_id)).json()["items"]) == 1

    # One row per page, and the cursor moves without repeating a row (T-305).
    first = golden.alerts_via_api(granted, limit="1").json()
    assert len(first["items"]) == 1
    assert first["next_cursor"]
    second = golden.alerts_via_api(granted, limit="1", cursor=first["next_cursor"]).json()
    assert second["items"][0]["id"] != first["items"][0]["id"]

    descending = golden.alerts_via_api(granted).json()
    ids = [item["id"] for item in descending["items"]]
    assert ids == sorted(ids, reverse=True)

    ascending = golden.alerts_via_api(granted, order="asc").json()
    ids = [item["id"] for item in ascending["items"]]
    assert ids == sorted(ids)

    # A window nobody wrote an alert in returns nothing, rather than everything.
    later = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    window = {
        "start": later,
        "end": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
    }
    assert golden.client.get("/api/v1/alerts", params=window, headers=granted).json()["items"] == []


def test_the_bus_refuses_a_partition_it_does_not_have(golden: GoldenRun) -> None:
    """The fake is a fake, not a lawless double: its contract is asserted too."""
    with pytest.raises(ValueError, match="positive"):
        InProcessBus(partitions=0)
    with pytest.raises(ValueError, match="outside"):
        golden.pipeline.bus.send("flows.raw", b"{}", 99, b"key")
    # A partition that never saw a record reads as empty rather than inventing one.
    assert golden.pipeline.bus.read("flows.raw", 99, 0, 10) == []
    assert golden.pipeline.bus.end_offset("flows.raw", 99) == 0
    assert golden.pipeline.consumer.end_offset(0) == 0


def test_a_pipeline_without_a_stream_still_stores_the_alert(settings: Settings) -> None:
    """A process with no subscribers still records what it found (T-310, T-319)."""
    app = create_app(settings)
    app.state.token_service = TokenService(SECRET)
    store = app.state.alert_store
    assert isinstance(store, InMemoryAlertStore)
    pipeline = build_pipeline(
        PortScanScorer(),
        fuse=fuse,
        alerts=store,
        label_family=lambda _identity: FAMILY,
        hub=None,
    )
    app.state.flow_publisher = pipeline
    granted = _granted(app.state.token_service)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingest/flows",
            content=ndjson(scan_traffic()).encode(),
            headers={"content-type": "application/x-ndjson", **granted},
        )
        assert response.status_code == 200
        pipeline.drain()

    assert len(store) == 1
    assert app.state.alert_hub.latest_sequence() is None


def test_a_missing_alert_store_is_reported_not_read_as_empty(settings: Settings) -> None:
    """An empty store and no store are different claims; only one is a quiet network."""
    app = create_app(settings)
    app.state.token_service = TokenService(SECRET)
    del app.state.alert_store
    granted = _granted(app.state.token_service)
    now = datetime.now(UTC)
    with TestClient(app) as client, pytest.raises(RuntimeError, match="alert_store is not"):
        client.get(
            "/api/v1/alerts",
            params={
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
            },
            headers=granted,
        )
