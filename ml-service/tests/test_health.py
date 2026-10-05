"""Tests for the model-service health contract (T-003).

Acceptance criterion: the endpoint distinguishes "up, no model" from "up, model
active".
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from aegis_ml.registry.model_registry import ModelInfo, ModelRegistry
from aegis_ml.serving.app import create_app
from fastapi.testclient import TestClient

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry()


@pytest.fixture
def client(registry: ModelRegistry) -> Iterator[TestClient]:
    with TestClient(create_app(registry)) as test_client:
        yield test_client


def test_up_with_no_model_reports_no_model_loaded(client: TestClient) -> None:
    """A freshly started process is healthy but is not yet scoring."""
    response = client.get("/internal/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_state"] == "no_model_loaded"
    assert body["models"] == []


def test_up_with_an_active_model_reports_serving(
    client: TestClient, registry: ModelRegistry
) -> None:
    registry.register(
        ModelInfo(
            model_id="flownet@1.0.0",
            kind="flow",
            status="active",
            sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            loaded_at=T0,
        )
    )

    body = client.get("/internal/healthz").json()

    assert body["model_state"] == "serving"
    assert body["models"][0]["model_id"] == "flownet@1.0.0"


def test_staging_only_model_does_not_count_as_serving(
    client: TestClient, registry: ModelRegistry
) -> None:
    """Shadow-mode models are resident but must not look like they own alerts."""
    registry.register(
        ModelInfo(
            model_id="flownet@1.1.0",
            kind="flow",
            status="staging",
            sha256="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            loaded_at=T0,
        )
    )

    body = client.get("/internal/healthz").json()

    assert body["model_state"] == "no_model_loaded"
    assert [m["status"] for m in body["models"]] == ["staging"]


def test_retired_model_stops_the_service_reporting_serving(
    client: TestClient, registry: ModelRegistry
) -> None:
    registry.register(
        ModelInfo(
            model_id="flownet@1.0.0",
            kind="flow",
            status="active",
            sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            loaded_at=T0,
        )
    )
    registry.retire("flownet@1.0.0")

    assert client.get("/internal/healthz").json()["model_state"] == "no_model_loaded"


def test_health_lists_every_resident_version(client: TestClient, registry: ModelRegistry) -> None:
    registry.register(
        ModelInfo(
            model_id="flownet@1.0.0",
            kind="flow",
            status="active",
            sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            loaded_at=T0,
        )
    )
    registry.register(
        ModelInfo(
            model_id="lognet@1.0.0",
            kind="log",
            status="active",
            sha256="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
            loaded_at=T0,
        )
    )

    body = client.get("/internal/healthz").json()

    assert {m["kind"] for m in body["models"]} == {"flow", "log"}
    assert body["service"] == "aegis-ml-service"
