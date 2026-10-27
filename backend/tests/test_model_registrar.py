"""The model registrar mirrors the ML service's catalogue into the registry.

Regression: the ML service lists the statistical fallback and FlowNet both as
``active``. The registry allows one active version per kind, so the second
registration was refused on every poll and logged as a failure.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from app.services import model_registrar as registrar_module
from app.services.model_ops import ModelOpsService, UnknownModel
from app.services.model_registrar import ModelRegistrar

CATALOGUE: dict[str, Any] = {
    "models": [
        {
            "model_id": "statistical-anomaly-v1",
            "kind": "flow",
            "status": "active",
            "artifact_uri": "ml-service://statistical-anomaly-v1",
            "sha256": "a" * 64,
        },
        {
            "model_id": "flownet-v1",
            "kind": "flow",
            "status": "active",
            "artifact_uri": "ml-service://flownet-v1",
            "sha256": "b" * 64,
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


# --- R-68: a version is identified by its content address -------------------------


def test_an_entry_without_a_content_address_is_refused_not_placeholdered(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: every entry used to register under sha256 "0" * 64.

    That is valid hex and identifies nothing.
    """
    caplog.set_level(logging.WARNING, logger=registrar_module.logger.name)
    registrar, ops = _registrar(monkeypatch)
    monkeypatch.setattr(
        registrar_module,
        "_fetch_json",
        lambda url, timeout: {
            "models": [{"model_id": "lognet-v1", "kind": "log", "status": "active"}]
        },
    )

    registrar._register_models()
    registrar._register_models()

    with pytest.raises(UnknownModel):
        ops.get("lognet-v1")
    assert caplog.text.count("model_registrar_refused_no_content_address model_id=lognet-v1") == 1


EVAL_FIXTURE = Path(__file__).parent / "fixtures" / "eval" / "flownet-v0.1.0.eval.json"
FLOWNET_CATALOGUE: dict[str, Any] = {
    "models": [
        {
            "model_id": "flownet-v0.1.0",
            "kind": "flow",
            "status": "active",
            "artifact_uri": "ml-service://flownet-v0.1.0",
            "sha256": "c" * 64,
        }
    ]
}


def _eval_dir(tmp_path: Path, *, model_id: str = "flownet-v0.1.0") -> Path:
    """A reports directory holding the real eval@2 report, optionally re-labelled."""
    directory = tmp_path / "eval"
    directory.mkdir()
    report = json.loads(EVAL_FIXTURE.read_text(encoding="utf-8"))
    report["model_id"] = model_id
    (directory / "flownet.eval.json").write_text(json.dumps(report), encoding="utf-8")
    (directory / "flownet.config.json").write_text(
        json.dumps({"split_policy": "temporal-only"}), encoding="utf-8"
    )
    return directory


def test_a_matching_report_is_attached_with_its_split_and_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(registrar_module, "_fetch_json", lambda url, timeout: FLOWNET_CATALOGUE)
    ops = ModelOpsService()
    registrar = ModelRegistrar(
        "http://ml", ops, interval=60, eval_reports_dir=str(_eval_dir(tmp_path))
    )

    registrar._register_models()

    version = ops.get("flownet-v0.1.0")
    assert version.metrics is not None
    assert version.metrics.split == "temporal-only"
    assert version.metrics.points["roc_auc"].artifact == "flownet.eval.json"


def test_a_report_for_another_model_is_skipped_and_registration_continues(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(registrar_module, "_fetch_json", lambda url, timeout: FLOWNET_CATALOGUE)
    ops = ModelOpsService()
    registrar = ModelRegistrar(
        "http://ml",
        ops,
        interval=60,
        eval_reports_dir=str(_eval_dir(tmp_path, model_id="some-other-model")),
    )

    registrar._register_models()

    assert ops.get("flownet-v0.1.0").metrics is None


def test_no_reports_directory_means_no_evaluations_and_no_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registrar_module, "_fetch_json", lambda url, timeout: FLOWNET_CATALOGUE)
    ops = ModelOpsService()
    registrar = ModelRegistrar("http://ml", ops, interval=60)

    registrar._register_models()

    assert ops.get("flownet-v0.1.0").metrics is None
    assert registrar.stats["errors"] == 0
