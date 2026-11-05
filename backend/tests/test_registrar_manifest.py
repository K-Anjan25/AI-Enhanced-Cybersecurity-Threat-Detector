"""The registrar takes the manifest flag from the ML service instead of assuming one."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest
from app.services import model_registrar as mr
from app.services.model_ops import MissingManifest, ModelOpsService

SHA = "c" * 64


def _entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "model_id": "flownet-v0.1.0",
        "kind": "flow",
        "status": "staging",
        "sha256": SHA,
        "artifact_uri": "ml-service://flownet-v0.1.0",
    }
    entry.update(overrides)
    return entry


def _register(entries: list[dict[str, Any]]) -> ModelOpsService:
    ops = ModelOpsService()
    registrar = mr.ModelRegistrar("http://ml-service:8001", ops)
    with mock.patch.object(mr, "_fetch_json", return_value={"models": entries}):
        registrar._register_models()
    return ops


def test_missing_manifest_flag_is_recorded_as_missing() -> None:
    ops = _register([_entry()])
    assert ops.get("flownet-v0.1.0").manifest_present is False


def test_complete_manifest_flag_is_recorded_as_present() -> None:
    ops = _register([_entry(manifest_present=True)])
    assert ops.get("flownet-v0.1.0").manifest_present is True


def test_version_without_manifest_cannot_be_promoted() -> None:
    ops = _register([_entry()])
    with pytest.raises(MissingManifest):
        ops.promote("flownet-v0.1.0", actor="test", justification="check the refusal")
