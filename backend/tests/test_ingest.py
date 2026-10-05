"""T-304: batch ingest with per-record validation errors (FR-01, FR-02, FR-04).

The acceptance criterion is that a batch with one malformed record returns a
per-record error list and accepts the rest, and that no partial batch is
silently dropped. "Silently" is the operative word, so the tests assert the
arithmetic -- ``received == accepted + rejected``, one error entry per rejected
record -- rather than only that the good records came through. A batch could
satisfy the first half while quietly losing records.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.schemas.ingest import (
    MAX_FLOW_RECORDS,
    MAX_LOG_LINES,
    FlowRecordIn,
    LogRecordIn,
)
from app.services.ingest_service import (
    BatchTooLarge,
    UnsupportedMediaType,
    ingest_batch,
    split_ndjson,
)
from fastapi.testclient import TestClient

NDJSON = "application/x-ndjson"
SECRET = "i" * 48


def flow(**overrides: Any) -> dict[str, Any]:
    """A valid flow@1 record, with overrides applied."""
    record: dict[str, Any] = {
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
    record.update(overrides)
    return record


def log(**overrides: Any) -> dict[str, Any]:
    """A valid log@1 record, with overrides applied."""
    record: dict[str, Any] = {
        "timestamp": "2026-03-15T10:00:00Z",
        "host": "web-01",
        "service": "sshd",
        "level": "info",
        "message": "Accepted publickey for alice",
    }
    record.update(overrides)
    return record


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    from app.main import create_app

    built = create_app(settings)
    built.state.token_service = auth
    return TestClient(built)


def headers(auth: TokenService, role: str = "analyst") -> dict[str, str]:
    pair = auth.issue("collector", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


# --- the acceptance criterion ----------------------------------------------


def test_one_bad_record_does_not_fail_the_batch() -> None:
    """FR-04: reject the record, not the batch."""
    body = json.dumps([flow(), flow(protocol="carrier-pigeon"), flow()]).encode()
    response, accepted = ingest_batch(body, FlowRecordIn, limit=MAX_FLOW_RECORDS)

    assert response.received == 3
    assert response.accepted == 2
    assert response.rejected == 1
    assert len(accepted) == 2


def test_the_arithmetic_never_loses_a_record() -> None:
    """The property behind "no partial batch is silently dropped"."""
    batch = [flow(), flow(dst_port=-1), flow(), "not-a-record", flow(src_port=70000)]
    body = json.dumps(batch).encode()
    response, accepted = ingest_batch(body, FlowRecordIn, limit=MAX_FLOW_RECORDS)

    assert response.received == response.accepted + response.rejected
    assert response.received == 5
    assert len(accepted) == response.accepted


def test_every_rejected_record_has_at_least_one_error_entry() -> None:
    batch = [flow(), flow(protocol="nope"), flow(duration=-1.0), flow()]
    response, _ = ingest_batch(json.dumps(batch).encode(), FlowRecordIn, limit=MAX_FLOW_RECORDS)

    reported = {e.index for e in response.errors}
    assert reported == {1, 2}
    assert response.rejected == len(reported)


def test_all_errors_on_one_record_are_reported_not_just_the_first() -> None:
    """A client fixing one field at a time should not need three round trips."""
    batch = [flow(protocol="nope", src_port=99999, duration=-1.0)]
    response, _ = ingest_batch(json.dumps(batch).encode(), FlowRecordIn, limit=MAX_FLOW_RECORDS)

    fields = {e.field for e in response.errors}
    assert fields == {"protocol", "src_port", "duration"}


def test_a_wholly_valid_batch_reports_no_errors() -> None:
    batch = [flow(), flow(), flow()]
    response, accepted = ingest_batch(
        json.dumps(batch).encode(), FlowRecordIn, limit=MAX_FLOW_RECORDS
    )

    assert response.rejected == 0
    assert response.errors == []
    assert len(accepted) == 3


def test_an_empty_batch_is_accepted() -> None:
    response, accepted = ingest_batch(b"[]", FlowRecordIn, limit=MAX_FLOW_RECORDS)
    assert (response.received, response.accepted, response.rejected) == (0, 0, 0)
    assert accepted == []


def test_an_empty_body_is_not_an_error() -> None:
    response, _ = ingest_batch(b"", FlowRecordIn, limit=MAX_FLOW_RECORDS)
    assert response.received == 0


# --- NDJSON -----------------------------------------------------------------


def test_ndjson_is_accepted() -> None:
    body = b"\n".join(json.dumps(flow()).encode() for _ in range(3))
    response, accepted = ingest_batch(
        body, FlowRecordIn, limit=MAX_FLOW_RECORDS, content_type=NDJSON
    )
    assert response.accepted == 3
    assert len(accepted) == 3


def test_an_unparseable_ndjson_line_is_a_per_record_error() -> None:
    """Not a whole-batch failure: the other lines must still be accepted."""
    body = (json.dumps(flow()) + "\nNOT JSON\n" + json.dumps(flow()) + "\n").encode()
    response, accepted = ingest_batch(
        body, FlowRecordIn, limit=MAX_FLOW_RECORDS, content_type=NDJSON
    )

    assert response.received == 3
    assert response.accepted == 2
    assert len(accepted) == 2
    assert [e.stage for e in response.errors] == ["parse"]


def test_ndjson_error_indexes_point_at_the_real_line_number() -> None:
    """Dropping a bad line must not shift the positions of the ones after it."""
    body = (
        json.dumps(flow())
        + "\nNOT JSON\n"
        + json.dumps(flow(protocol="nope"))
        + "\n"
        + json.dumps(flow())
        + "\n"
    ).encode()
    response, _ = ingest_batch(body, FlowRecordIn, limit=MAX_FLOW_RECORDS, content_type=NDJSON)

    assert sorted(e.index for e in response.errors) == [1, 2]


def test_a_trailing_newline_is_not_a_malformed_record() -> None:
    body = (json.dumps(flow()) + "\n").encode()
    response, _ = ingest_batch(body, FlowRecordIn, limit=MAX_FLOW_RECORDS, content_type=NDJSON)
    assert response.rejected == 0
    assert response.received == 1


def test_blank_lines_are_skipped() -> None:
    body = (json.dumps(flow()) + "\n\n\n" + json.dumps(flow()) + "\n").encode()
    parsed, errors = split_ndjson(body)
    assert len(parsed) == 2
    assert errors == []


# --- limits -----------------------------------------------------------------


def test_the_flow_limit_is_1000() -> None:
    assert MAX_FLOW_RECORDS == 1_000
    body = json.dumps([flow() for _ in range(1_001)]).encode()
    with pytest.raises(BatchTooLarge) as exc:
        ingest_batch(body, FlowRecordIn, limit=MAX_FLOW_RECORDS)
    assert exc.value.received == 1_001


def test_exactly_at_the_limit_is_accepted() -> None:
    """The limit is inclusive; FR-01 says "up to" 1,000."""
    body = json.dumps([flow() for _ in range(MAX_FLOW_RECORDS)]).encode()
    response, _ = ingest_batch(body, FlowRecordIn, limit=MAX_FLOW_RECORDS)
    assert response.accepted == MAX_FLOW_RECORDS


def test_the_log_limit_is_5000() -> None:
    assert MAX_LOG_LINES == 5_000


def test_a_malformed_body_that_is_not_json_or_ndjson_is_refused() -> None:
    with pytest.raises(UnsupportedMediaType):
        ingest_batch(b"<html>not json</html>", FlowRecordIn, limit=MAX_FLOW_RECORDS)


def test_a_json_scalar_is_refused() -> None:
    with pytest.raises(UnsupportedMediaType):
        ingest_batch(b"42", FlowRecordIn, limit=MAX_FLOW_RECORDS)


def test_a_single_object_is_treated_as_a_batch_of_one() -> None:
    response, accepted = ingest_batch(
        json.dumps(flow()).encode(), FlowRecordIn, limit=MAX_FLOW_RECORDS
    )
    assert response.accepted == 1
    assert len(accepted) == 1


# --- log records ------------------------------------------------------------


def test_log_records_validate_against_log_at_1() -> None:
    batch = [log(), log(level="not-a-level"), log(message="")]
    response, accepted = ingest_batch(
        batch and json.dumps(batch).encode(), LogRecordIn, limit=MAX_LOG_LINES
    )
    assert response.accepted == 1
    assert response.rejected == 2
    assert len(accepted) == 1


def test_unknown_extra_fields_are_rejected() -> None:
    """Both contracts are extra="forbid"; a typo must not pass silently."""
    response, _ = ingest_batch(
        json.dumps([flow(surprise=1)]).encode(), FlowRecordIn, limit=MAX_FLOW_RECORDS
    )
    assert response.rejected == 1


# --- over HTTP --------------------------------------------------------------


def test_flows_endpoint_accepts_a_batch(client: TestClient, auth: TokenService) -> None:
    response = client.post(
        "/api/v1/ingest/flows",
        content=json.dumps([flow(), flow(protocol="nope")]).encode(),
        headers=headers(auth),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["received"] == 2
    assert body["accepted"] == 1
    assert body["rejected"] == 1
    assert len(body["errors"]) == 1


def test_logs_endpoint_accepts_ndjson(client: TestClient, auth: TokenService) -> None:
    body = (json.dumps(log()) + "\nBAD LINE\n" + json.dumps(log()) + "\n").encode()
    response = client.post(
        "/api/v1/ingest/logs", content=body, headers={**headers(auth), "Content-Type": NDJSON}
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 2


def test_an_oversized_batch_is_413(client: TestClient, auth: TokenService) -> None:
    body = json.dumps([flow() for _ in range(1_001)]).encode()
    response = client.post("/api/v1/ingest/flows", content=body, headers=headers(auth))
    assert response.status_code == 413


def test_a_viewer_cannot_ingest(client: TestClient, auth: TokenService) -> None:
    """R-53 makes viewer read-only."""
    response = client.post(
        "/api/v1/ingest/flows",
        content=json.dumps([flow()]).encode(),
        headers=headers(auth, "viewer"),
    )
    assert response.status_code == 403


def test_an_analyst_can_ingest(client: TestClient, auth: TokenService) -> None:
    response = client.post(
        "/api/v1/ingest/flows",
        content=json.dumps([flow()]).encode(),
        headers=headers(auth, "analyst"),
    )
    assert response.status_code == 200


def test_an_unauthenticated_ingest_is_401(client: TestClient) -> None:
    response = client.post("/api/v1/ingest/flows", content=b"[]")
    assert response.status_code == 401


def test_an_unparseable_ndjson_body_returns_415_not_422(
    client: TestClient, auth: TokenService
) -> None:
    """A body that is not JSON at all is a media-type problem.

    Not a per-record one: there is no record to attribute it to.
    """
    response = client.post("/api/v1/ingest/flows", content=b"<<>>", headers=headers(auth))
    assert response.status_code == 415
