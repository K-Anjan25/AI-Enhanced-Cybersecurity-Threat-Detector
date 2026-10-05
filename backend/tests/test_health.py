"""Tests for the health and readiness endpoints (T-002)."""

from __future__ import annotations

from app.services.health_service import ProbeResult
from fastapi.testclient import TestClient


def test_healthz_returns_ok_with_service_metadata(client: TestClient) -> None:
    """Liveness reports the process identity and never fails on dependencies."""
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "aegis-backend-test"
    assert body["environment"] == "test"
    assert body["version"]


def test_readyz_reports_ready_when_no_probes_registered(client: TestClient) -> None:
    """With no declared dependencies there is nothing that can make us unready."""
    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == []


def test_readyz_returns_503_when_a_dependency_is_unavailable(client: TestClient) -> None:
    """An unready process must stop receiving traffic (NFR-03)."""
    client.app.state.readiness.register(
        "postgres",
        lambda: ProbeResult(name="postgres", status="unavailable", detail="connection refused"),
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"] == [
        {"name": "postgres", "status": "unavailable", "detail": "connection refused"}
    ]


def test_readyz_treats_a_raising_probe_as_unavailable(client: TestClient) -> None:
    """A broken probe must not break readiness reporting itself (R-06)."""

    def exploding_probe() -> ProbeResult:
        raise RuntimeError("probe exploded")

    client.app.state.readiness.register("kafka", exploding_probe)

    response = client.get("/readyz")

    assert response.status_code == 503
    check = response.json()["checks"][0]
    assert check["name"] == "kafka"
    assert check["status"] == "unavailable"
    assert check["detail"] == "RuntimeError"


def test_a_degraded_probe_also_blocks_readiness(client: TestClient) -> None:
    """Only an explicitly ``ok`` probe counts as ready."""
    client.app.state.readiness.register(
        "ml-service", lambda: ProbeResult(name="ml-service", status="degraded")
    )

    assert client.get("/readyz").status_code == 503


def test_healthz_stays_ok_while_a_dependency_is_down(client: TestClient) -> None:
    """Liveness must not flap on dependency failure, or restarts loop."""
    client.app.state.readiness.register(
        "postgres", lambda: ProbeResult(name="postgres", status="unavailable")
    )

    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz").status_code == 200


def test_generated_request_id_is_returned_on_the_response(client: TestClient) -> None:
    """Every response carries a correlation id for tracing (NFR-07)."""
    response = client.get("/healthz")

    assert len(response.headers["X-Request-ID"]) == 32


def test_inbound_request_id_is_reused_for_the_trace(client: TestClient) -> None:
    """An upstream id is honoured so a trace survives the hop."""
    response = client.get("/healthz", headers={"X-Request-ID": "trace-from-upstream"})

    assert response.headers["X-Request-ID"] == "trace-from-upstream"
