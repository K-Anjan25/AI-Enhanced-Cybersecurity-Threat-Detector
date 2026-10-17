"""The model registrar mirrors the ML service's catalogue into the registry.

Regression: the ML service lists the statistical fallback and FlowNet both as
``active``. The registry allows one active version per kind, so the second
registration was refused on every poll and logged as a failure.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from app.services import model_registrar as registrar_module
from app.services.model_ops import ModelOpsService
from app.services.model_registrar import ModelRegistrar

CATALOGUE: dict[str, Any] = {
    "models": [
        {
            "model_id": "statistical-anomaly-v1",
            "kind": "flow",
            "status": "active",
            "artifact_uri": "ml-service://statistical-anomaly-v1",
        },
        {
            "model_id": "flownet-v1",
            "kind": "flow",
            "status": "active",
            "artifact_uri": "ml-service://flownet-v1",
        },
    ]
}


def _registrar(monkeypatch: pytest.MonkeyPatch) -> tuple[ModelRegistrar, ModelOpsService]:
    monkeypatch.setattr(registrar_module, "_fetch_json", lambda url, timeout: CATALOGUE)
    ops = ModelOpsService()
    return ModelRegistrar("http://ml.test", ops, interval=3600.0), ops


def test_a_second_active_model_is_staged_not_failed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    registrar, ops = _registrar(monkeypatch)

    registrar._register_models()

    assert registrar.stats["errors"] == 0
    assert "model_registrar_register_failed" not in caplog.text
    assert ops.get("statistical-anomaly-v1").status == "active"
    assert ops.get("flownet-v1").status == "staging"
    assert set(registrar.stats["registered"]) == {"statistical-anomaly-v1", "flownet-v1"}
    assert "model_registrar_staged model_id=flownet-v1" in caplog.text


def test_a_staged_model_is_not_promoted_and_repolling_is_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registrar, ops = _registrar(monkeypatch)

    registrar._register_models()
    registrar._register_models()

    # Promotion would retire the incumbent; the loop must not do that on its own.
    assert ops.get("statistical-anomaly-v1").status == "active"
    assert ops.get("flownet-v1").status == "staging"
    assert registrar.stats["registrations"] == 2
    assert registrar.stats["errors"] == 0
