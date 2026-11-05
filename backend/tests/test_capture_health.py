"""Real capture health is reported by supervised Docker sensors, never inferred."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.main import create_app
from app.services.audit_log import AuditAction
from app.services.capture_health import CaptureHealthCapacityError, CaptureHealthRegistry
from fastapi.testclient import TestClient

SECRET = "capture-health-test-secret-key-long-enough-0123456789"  # pragma: allowlist secret


def test_registry_reports_unknown_then_expires_a_real_sensor_heartbeat() -> None:
    monotonic = 10.0
    now = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
    registry = CaptureHealthRegistry(
        timeout_seconds=45,
        now=lambda: now,
        monotonic=lambda: monotonic,
    )

    assert registry.snapshot() == {
        "status": "unknown",
        "heartbeat_timeout_seconds": 45,
        "sensors": [],
    }

    recorded = registry.record("docker-host-capture", ["zeek", "suricata", "tshark"])
    assert recorded["status"] == "healthy"
    assert registry.snapshot()["status"] == "healthy"

    monotonic += 46
    now += timedelta(seconds=46)
    snapshot = registry.snapshot()
    assert snapshot["status"] == "stale"
    sensor = snapshot["sensors"][0]  # type: ignore[index]
    assert sensor["age_seconds"] == 46
    assert sensor["last_seen_at"] == datetime(2026, 11, 5, 10, 0, tzinfo=UTC)


def test_registry_is_bounded_and_replaces_only_an_expired_sensor() -> None:
    monotonic = 10.0
    registry = CaptureHealthRegistry(
        max_sensors=1,
        monotonic=lambda: monotonic,
    )
    registry.record("linux-edge-1", ["zeek"])

    with pytest.raises(CaptureHealthCapacityError):
        registry.record("linux-edge-2", ["suricata"])

    monotonic += 46
    registry.record("linux-edge-2", ["suricata"])
    snapshot = registry.snapshot()
    assert snapshot["status"] == "healthy"
    sensors = snapshot["sensors"]
    assert len(sensors) == 1  # type: ignore[arg-type]
    assert sensors[0]["sensor_id"] == "linux-edge-2"  # type: ignore[index]


def test_capture_heartbeat_is_ingest_authenticated_and_status_is_readable() -> None:
    settings = Settings(
        env="test",
        service_name="aegis-capture-test",
        secret_key=SECRET,
        log_level="WARNING",
    )
    tokens = TokenService(SECRET)
    app = create_app(settings)
    app.state.token_service = tokens
    app.state.capture_health = CaptureHealthRegistry(max_sensors=1)
    paths = list(app.openapi()["paths"])
    capture_index = paths.index("/api/v1/capture/heartbeat")
    assert capture_index < paths.index("/metrics")
    assert capture_index < paths.index("/api/v1/ingest/flows")
    with TestClient(app) as client:
        body = {"sensor_id": "linux-edge-1", "engines": ["zeek", "suricata", "tshark"]}
        assert client.post("/api/v1/capture/heartbeat", json=body).status_code == 401

        viewer = tokens.issue("viewer@corp", "viewer")
        viewer_headers = {"Authorization": f"Bearer {viewer.access_token}"}
        assert (
            client.post("/api/v1/capture/heartbeat", json=body, headers=viewer_headers).status_code
            == 403
        )

        analyst = tokens.issue("sensor@corp", "analyst")
        analyst_headers = {"Authorization": f"Bearer {analyst.access_token}"}
        response = client.post("/api/v1/capture/heartbeat", json=body, headers=analyst_headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "healthy"
        assert response.json()["engines"] == body["engines"]
        entries = app.state.audit_trail.entries(
            start=datetime.now(UTC) - timedelta(minutes=1),
            end=datetime.now(UTC) + timedelta(minutes=1),
        )
        assert len(entries) == 1
        audit = entries[0].record
        assert audit.action is AuditAction.capture_heartbeat
        assert audit.actor == "sensor@corp"
        assert audit.target_type == "capture_sensor"
        assert audit.target_id == body["sensor_id"]
        assert audit.detail == {"engines": body["engines"]}

        status_response = client.get("/api/v1/capture/status", headers=viewer_headers)
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "healthy"
        assert status_response.json()["sensors"][0]["sensor_id"] == "linux-edge-1"

        at_capacity = client.post(
            "/api/v1/capture/heartbeat",
            json={"sensor_id": "linux-edge-2", "engines": ["zeek"]},
            headers=analyst_headers,
        )
        assert at_capacity.status_code == 429
