"""Tests for the LogNet promotion gate and the MLflow lifecycle around it.

The gate tests are pure and always run. The lifecycle tests need the ``mlops`` and
``training`` extras and use a throw-away MLflow store under ``tmp_path``, so they
never touch the real store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from aegis_ml.lifecycle.mlflow_lifecycle import GateConfig, evaluate_gate

# ── the gate (pure) ───────────────────────────────────────────────────────────


def test_gate_passes_when_auc_clears_floor_and_beats_baseline() -> None:
    result = evaluate_gate({"roc_auc": 0.93, "baseline_severity_auc": 0.90})
    assert result.passed
    assert result.reasons == []


def test_gate_refuses_below_the_floor_even_if_it_beats_baseline() -> None:
    result = evaluate_gate({"roc_auc": 0.70, "baseline_severity_auc": 0.40})
    assert not result.passed
    assert any("below the floor" in reason for reason in result.reasons)


def test_gate_refuses_when_the_severity_rule_is_as_good() -> None:
    result = evaluate_gate({"roc_auc": 0.92, "baseline_severity_auc": 0.95})
    assert not result.passed
    assert any("does not beat the severity baseline" in r for r in result.reasons)


def test_gate_refuses_when_one_class_was_missing_from_eval() -> None:
    result = evaluate_gate({"roc_auc": None, "baseline_severity_auc": 0.9})
    assert not result.passed
    assert any("lack one class" in reason for reason in result.reasons)


def test_gate_refuses_a_run_without_a_baseline() -> None:
    result = evaluate_gate({"roc_auc": 0.99})
    assert not result.passed
    assert any("no severity baseline" in reason for reason in result.reasons)


def test_gate_margin_is_applied() -> None:
    metrics = {"roc_auc": 0.92, "baseline_severity_auc": 0.90}
    assert evaluate_gate(metrics, GateConfig(margin_over_baseline=0.01)).passed is True
    strict = evaluate_gate(metrics, GateConfig(margin_over_baseline=0.05))
    assert not strict.passed
    assert strict.reasons


def test_gate_decision_is_serialisable_for_mlflow_tags() -> None:
    import json

    tag = json.loads(evaluate_gate({"roc_auc": 0.5, "baseline_severity_auc": 1.0}).as_tag())
    assert tag["passed"] is False
    assert tag["config"]["min_roc_auc"] == 0.8


# ── the lifecycle (MLflow + torch) ────────────────────────────────────────────

pytest.importorskip("mlflow", reason="mlflow is the ml-service[mlops] extra")
torch = pytest.importorskip("torch", reason="torch is the ml-service[training] extra")

from aegis_ml.lifecycle import mlflow_lifecycle as lc  # noqa: E402
from aegis_ml.serving.lognet_bundle import LogNetBundle  # noqa: E402
from aegis_ml.training.lognet_train import (  # noqa: E402
    LogNetTrainConfig,
    LogLine,
    digest_lines,
    train_bundle,
)

PASSING = evaluate_gate({"roc_auc": 0.95, "baseline_severity_auc": 0.5})
FAILING = evaluate_gate({"roc_auc": 0.40, "baseline_severity_auc": 0.5})


def _lines(seed: int) -> list[LogLine]:
    base = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    out: list[LogLine] = []
    for i in range(160):
        burst = 130 <= i < 142  # held-out part (cut at 70% of 160 lines)
        out.append(
            LogLine(
                epoch=base + i + seed,
                message=(f"fault code {i} on bus {i % 7}" if burst else f"heartbeat ok node {i % 5}"),
                anomalous=burst,
                flagged=burst,
            )
        )
    return out


@pytest.fixture
def mlf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    db = tmp_path / "mlflow.db"
    monkeypatch.setenv("AEGIS_MLFLOW_TRACKING_URI", f"sqlite:///{db}")
    monkeypatch.setenv("AEGIS_MLFLOW_ARTIFACT_ROOT", (tmp_path / "artifacts").as_uri())
    return lc.client()


def _train(tmp_path: Path, mlf, name: str, seed: int) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    lines = _lines(seed)
    out = tmp_path / name
    cfg = LogNetTrainConfig(window=8, stride=4, epochs=2, batch_size=8, d_model=32, nhead=4, dim_feedforward=64, seed=seed)
    train_bundle(lines, out, cfg)
    sha = digest_lines(lines)
    run = lc.log_run(mlf, out, experiment="test-lognet", data_sha256=sha)
    version = lc.register_version(mlf, run, data_sha256=sha)
    return run.run_id, version


def test_promote_then_rollback_moves_the_champion_along_the_history(tmp_path: Path, mlf) -> None:  # type: ignore[no-untyped-def]
    dest = tmp_path / "verify"
    _, v1 = _train(tmp_path, mlf, "a", seed=1)
    _, v2 = _train(tmp_path, mlf, "b", seed=2)

    assert lc.promote(mlf, v1, PASSING, download_dir=dest) is None
    assert str(lc.champion(mlf).version) == v1
    assert lc.promote(mlf, v2, PASSING, download_dir=dest) == v1
    current = lc.champion(mlf)
    assert str(current.version) == v2
    assert current.tags[lc.PREVIOUS_TAG] == v1

    assert lc.rollback(mlf, download_dir=dest) == v1
    assert str(lc.champion(mlf).version) == v1
    withdrawn = mlf.get_model_version(lc.MODEL_NAME, v2)
    assert withdrawn.tags[lc.ROLLED_BACK_TAG]

    with pytest.raises(lc.NothingToRollBack):
        lc.rollback(mlf, download_dir=dest)  # v1 has no earlier version


def test_a_failed_gate_leaves_the_champion_unchanged(tmp_path: Path, mlf) -> None:  # type: ignore[no-untyped-def]
    dest = tmp_path / "verify"
    _, v1 = _train(tmp_path, mlf, "a", seed=1)
    _, v2 = _train(tmp_path, mlf, "b", seed=2)
    lc.promote(mlf, v1, PASSING, download_dir=dest)
    with pytest.raises(lc.GateRefused, match="below the floor"):
        lc.promote(mlf, v2, FAILING, download_dir=dest)
    assert str(lc.champion(mlf).version) == v1


def test_promotion_refuses_weights_changed_after_training(tmp_path: Path, mlf) -> None:  # type: ignore[no-untyped-def]
    dest = tmp_path / "verify"
    run_id, v1 = _train(tmp_path, mlf, "a", seed=1)
    stored = [
        p
        for p in (tmp_path / "artifacts").rglob("lognet.pt")
        if run_id in p.as_posix()
    ]
    assert stored, "the weights should be in the tracking artifact store"
    stored[0].write_bytes(stored[0].read_bytes() + b"\x00tampered")

    with pytest.raises(lc.IntegrityError, match="does not match"):
        lc.promote(mlf, v1, PASSING, download_dir=dest)
    assert lc.champion(mlf) is None


def test_fetch_champion_returns_a_bundle_that_loads(tmp_path: Path, mlf) -> None:  # type: ignore[no-untyped-def]
    _, v1 = _train(tmp_path, mlf, "a", seed=1)
    lc.promote(mlf, v1, PASSING, download_dir=tmp_path / "verify")
    bundle_dir = lc.fetch_champion(mlf, tmp_path / "serving")
    bundle = LogNetBundle.load(bundle_dir)
    assert bundle.model_id.startswith("lognet-v1-")


def test_run_records_the_baseline_and_the_data_digest(tmp_path: Path, mlf) -> None:  # type: ignore[no-untyped-def]
    run_id, _ = _train(tmp_path, mlf, "a", seed=1)
    run = mlf.get_run(run_id)
    assert "baseline_severity_auc" in run.data.metrics
    assert run.data.tags[lc.DATA_SHA_TAG] == digest_lines(_lines(1))
    assert run.data.tags[lc.WEIGHTS_SHA_TAG]
