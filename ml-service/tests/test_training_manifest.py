"""A FlowNet artifact reports a complete R-63 training manifest only when it has one."""

from __future__ import annotations

import json
from pathlib import Path

from aegis_ml.serving.models import flownet_entry, manifest_complete

HASH = "a" * 64


def _manifest(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": "training_manifest@1",
        "model_id": "flownet-v0.1.0",
        "dataset_files": [{"name": "Friday.csv", "sha256": HASH}],
        "git_sha": "f" * 40,
        "seed": 7,
        "config": {},
        "metrics": {"roc_auc": 0.9},
        "baseline": {"name": "baselines.json", "sha256": "b" * 64},
    }
    base.update(overrides)
    return base


def _write(path: Path, manifest: dict[str, object]) -> str:
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return str(path)


def test_complete_manifest_is_accepted(tmp_path: Path) -> None:
    assert manifest_complete(_write(tmp_path / "m.json", _manifest())) is True


def test_missing_file_is_incomplete(tmp_path: Path) -> None:
    assert manifest_complete(str(tmp_path / "absent.json")) is False


def test_synthetic_run_without_dataset_files_is_incomplete(tmp_path: Path) -> None:
    assert manifest_complete(_write(tmp_path / "m.json", _manifest(dataset_files=[]))) is False


def test_run_without_baseline_is_incomplete(tmp_path: Path) -> None:
    assert manifest_complete(_write(tmp_path / "m.json", _manifest(baseline=None))) is False


def test_bad_dataset_hash_is_incomplete(tmp_path: Path) -> None:
    files = [{"name": "Friday.csv", "sha256": "not-a-hash"}]
    assert manifest_complete(_write(tmp_path / "m.json", _manifest(dataset_files=files))) is False


def test_flownet_entry_reports_no_manifest_when_absent(tmp_path: Path) -> None:
    (tmp_path / "flownet.pt").write_bytes(b"weights")
    (tmp_path / "flownet.config.json").write_text(
        json.dumps({"model_id": "flownet-v0.1.0"}), encoding="utf-8"
    )
    entry = flownet_entry(str(tmp_path))
    assert entry is not None
    assert entry["manifest_present"] is False


def test_flownet_entry_reports_manifest_when_complete(tmp_path: Path) -> None:
    (tmp_path / "flownet.pt").write_bytes(b"weights")
    (tmp_path / "flownet.config.json").write_text(
        json.dumps({"model_id": "flownet-v0.1.0"}), encoding="utf-8"
    )
    _write(tmp_path / "training_manifest.json", _manifest())
    entry = flownet_entry(str(tmp_path))
    assert entry is not None
    assert entry["manifest_present"] is True
