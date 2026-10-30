"""Tests for the LogNet training pipeline and the bundle it writes.

The helpers are tested without torch. The training and scoring tests need torch and
are skipped without it, the same way test_lognet.py is.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from aegis_ml.training.lognet_train import (
    FIRST_TEMPLATE_ID,
    LogLine,
    LogNetTrainConfig,
    classify_metrics,
    digest_lines,
    make_windows,
    roc_auc,
    threshold_from,
)

# ── pure helpers ──────────────────────────────────────────────────────────────


def test_windows_label_a_window_anomalous_when_any_line_is() -> None:
    tokens = list(range(10, 20))
    labels = [False] * 10
    labels[5] = True
    x, y, starts = make_windows(tokens, labels, window=4, stride=2)
    assert x.shape == (4, 4)
    assert list(starts) == [0, 2, 4, 6]
    assert list(y) == [0, 1, 1, 0]  # windows at 2 and 4 contain line 5


def test_windows_refuse_a_stream_shorter_than_one_window() -> None:
    with pytest.raises(ValueError, match="at least 5 lines"):
        make_windows([1, 2], [False, False], window=5, stride=1)


def test_windows_refuse_mismatched_inputs() -> None:
    with pytest.raises(ValueError, match="same length"):
        make_windows([1, 2, 3], [False], window=2, stride=1)


def test_roc_auc_is_one_for_perfect_separation_and_half_for_ties() -> None:
    scores = np.array([0.1, 0.2, 0.8, 0.9])
    labels = np.array([0, 0, 1, 1])
    assert roc_auc(scores, labels) == pytest.approx(1.0)
    assert roc_auc(np.zeros(4), labels) == pytest.approx(0.5)


def test_roc_auc_is_none_when_one_class_is_absent() -> None:
    assert roc_auc(np.array([0.1, 0.9]), np.array([0, 0])) is None


def test_threshold_is_a_quantile_of_clean_distances() -> None:
    distances = np.arange(100, dtype=float)
    assert threshold_from(distances, 0.95) == pytest.approx(94.05)
    with pytest.raises(ValueError, match="no clean"):
        threshold_from(np.zeros(0), 0.95)


def test_classify_metrics_counts_and_rates() -> None:
    distances = np.array([0.1, 0.9, 0.8, 0.2])
    labels = np.array([0, 1, 0, 1])
    metrics = classify_metrics(distances, labels, threshold=0.5)
    assert (metrics["tp"], metrics["fp"], metrics["fn"], metrics["tn"]) == (1, 1, 1, 1)
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)


def test_config_rejects_settings_that_would_fail_inside_the_loop() -> None:
    with pytest.raises(ValueError, match="stride"):
        LogNetTrainConfig(window=10, stride=11)
    with pytest.raises(ValueError, match="train_fraction"):
        LogNetTrainConfig(train_fraction=0.99)


def test_digest_changes_when_any_line_changes() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    a = [LogLine(epoch=base.timestamp(), message="x", anomalous=False)]
    b = [LogLine(epoch=(base + timedelta(seconds=1)).timestamp(), message="x", anomalous=False)]
    assert digest_lines(a) != digest_lines(b)
    assert digest_lines(a) == digest_lines(list(a))


# ── training, bundle and scorer (need torch) ──────────────────────────────────

torch = pytest.importorskip("torch", reason="torch is the ml-service[training] extra")


def _synthetic_lines(count: int = 160) -> list[LogLine]:
    """Regular traffic with a burst of unusual messages in the second half."""
    base = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    lines: list[LogLine] = []
    for i in range(count):
        if count // 2 <= i < count // 2 + 12:
            message = f"fault code {i} on bus {i % 7} unrecoverable"
            anomalous = True
        else:
            message = f"heartbeat ok from node {i % 5}"
            anomalous = False
        lines.append(LogLine(epoch=base + i, message=message, anomalous=anomalous))
    return lines


def _tiny_config(seed: int = 3) -> LogNetTrainConfig:
    return LogNetTrainConfig(
        window=8,
        stride=4,
        epochs=2,
        batch_size=8,
        d_model=32,
        nhead=4,
        dim_feedforward=64,
        seed=seed,
    )


def test_masked_batch_always_hides_at_least_one_position() -> None:
    from aegis_ml.training.lognet_train import MASK_ID, mask_batch

    generator = torch.Generator().manual_seed(0)
    x = torch.full((2, 6), 7, dtype=torch.long)
    inputs, targets, mask = mask_batch(x, mask_ratio=1e-9, generator=generator)
    assert bool(mask.any())
    assert bool((inputs[mask] == MASK_ID).all())
    assert torch.equal(targets, x)


def test_training_writes_a_bundle_that_loads_and_scores(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from aegis_ml.serving.lognet_bundle import LogNetBundle, anomaly_score
    from aegis_ml.training.lognet_train import META_FILE, WEIGHTS_FILE, train_bundle

    lines = _synthetic_lines()
    metrics = train_bundle(lines, tmp_path, _tiny_config())

    assert (tmp_path / WEIGHTS_FILE).is_file()
    meta = json.loads((tmp_path / META_FILE).read_text(encoding="utf-8"))
    assert meta["schema"] == "lognet-bundle@1"
    assert meta["data_sha256"] == digest_lines(lines)
    assert metrics["windows"] == meta["metrics"]["windows"]
    assert meta["model_config"]["vocab_size"] >= FIRST_TEMPLATE_ID + 1

    bundle = LogNetBundle.load(tmp_path)
    assert bundle.model_id == meta["model_id"]
    scored = bundle.score(["heartbeat ok from node 1"] * 8)
    assert scored is not None
    assert 0.0 <= scored.score <= 1.0
    assert scored.threshold == pytest.approx(meta["threshold"])
    assert anomaly_score(scored.threshold, scored.threshold) == pytest.approx(0.5)


def test_bundle_loader_refuses_a_missing_or_foreign_bundle(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from aegis_ml.serving.lognet_bundle import BundleError, LogNetBundle

    with pytest.raises(BundleError, match="no LogNet bundle"):
        LogNetBundle.load(tmp_path)
    (tmp_path / "lognet.json").write_text(json.dumps({"schema": "other@9"}), encoding="utf-8")
    (tmp_path / "lognet.pt").write_bytes(b"")
    with pytest.raises(BundleError, match="unsupported bundle schema"):
        LogNetBundle.load(tmp_path)


def test_scoring_uses_the_bundle_when_loaded(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from aegis_ml.serving import scoring
    from aegis_ml.serving.lognet_bundle import LogNetBundle
    from aegis_ml.training.lognet_train import train_bundle

    train_bundle(_synthetic_lines(), tmp_path, _tiny_config())
    bundle = LogNetBundle.load(tmp_path)
    monkeypatch.setattr(scoring, "_lognet_bundle", bundle)
    monkeypatch.setattr(scoring, "_models_loaded", True)

    logs = [
        scoring.LogRecord(timestamp="2026-01-01T00:00:00Z", source="node-1", level="info", message="heartbeat ok from node 1")
        for _ in range(8)
    ]
    response = scoring.score_log_window(scoring.ScoreRequest(logs=logs))
    assert response.scoring_method == "lognet"
    assert response.model_id == bundle.model_id
    assert response.explanations[0].startswith("LogNet distance")
