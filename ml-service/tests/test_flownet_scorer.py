"""Tests for the trained-checkpoint scorer and ``POST /score/windows``.

The checkpoint here is tiny and built inside the test, so the tests exercise the real
load path (weights, config, preprocessor, content address) without a training run.
The claim that matters is that serving encodes a window exactly as training does.
"""

from __future__ import annotations

import json
import os

import pytest

torch = pytest.importorskip("torch", reason="torch is the ml-service[training] extra")

from aegis_ml.data.features import (  # noqa: E402
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    extract_flow_window,
)
from aegis_ml.data.preprocess import Preprocessor, StandardScaler, Vocabulary  # noqa: E402
from aegis_ml.data.synthetic import generate_dataset  # noqa: E402
from aegis_ml.data.windowing import WindowKey, window_flows  # noqa: E402
from aegis_ml.models.flownet import FlowNet, FlowNetConfig  # noqa: E402
from aegis_ml.serving import flow_window  # noqa: E402
from aegis_ml.serving.app import create_app  # noqa: E402
from aegis_ml.serving.flownet_scorer import (  # noqa: E402
    CheckpointError,
    FlowNetScorer,
    feature_names,
    sha256_file,
)
from aegis_ml.training.baselines import design_matrix  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WINDOW = 50


@pytest.fixture(scope="module")
def records():
    return sorted(generate_dataset(per_scenario=12, seed=7).flows, key=lambda r: r.timestamp)


@pytest.fixture(scope="module")
def windows(records):
    return window_flows(records, key=WindowKey.SOURCE)


def _preprocessor(windows) -> Preprocessor:
    rows = []
    for window in windows:
        rows.extend(extract_flow_window(window.records, key=WindowKey.SOURCE))
    scaler = StandardScaler.fit([list(r.numeric) for r in rows], NUMERIC_FEATURES)
    vocabularies = {
        name: Vocabulary.fit(r.categorical[index] for r in rows)
        for index, name in enumerate(CATEGORICAL_FEATURES)
    }
    return Preprocessor(scaler=scaler, vocabularies=vocabularies)


def write_checkpoint(directory, windows) -> None:
    preprocessor = _preprocessor(windows)
    width = len(feature_names(preprocessor))
    config = FlowNetConfig(input_dim=width, d_model=16, nhead=2, dim_feedforward=32)
    torch.manual_seed(0)
    model = FlowNet(config)
    os.makedirs(directory, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(directory, "flownet.pt"))
    with open(os.path.join(directory, "flownet.config.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "model_id": "flownet-test-0.0.1",
                "input_dim": width,
                "d_model": config.d_model,
                "nhead": config.nhead,
                "dim_feedforward": config.dim_feedforward,
                "max_seq_len": config.max_seq_len,
                "window_size": WINDOW,
                "window_key": "source",
            },
            handle,
        )
    preprocessor.save(os.path.join(directory, "flownet.preprocessor.json"))


@pytest.fixture()
def checkpoint(tmp_path, windows):
    directory = tmp_path / "flownet"
    write_checkpoint(str(directory), windows)
    return str(directory)


@pytest.fixture(autouse=True)
def _fresh_endpoint_state(monkeypatch):
    flow_window.reset_scorer()
    yield
    flow_window.reset_scorer()


def test_load_reads_model_id_and_content_address(checkpoint):
    scorer = FlowNetScorer.load(checkpoint)
    assert scorer.model_id == "flownet-test-0.0.1"
    assert scorer.window_size == WINDOW
    assert scorer.sha256 == sha256_file(os.path.join(checkpoint, "flownet.pt"))
    assert len(scorer.sha256) == 64


def test_score_is_a_probability_with_three_reasons(checkpoint, windows):
    scorer = FlowNetScorer.load(checkpoint)
    result = scorer.score(list(windows[0].records))
    assert 0.0 <= result.score <= 1.0
    assert result.flows == len(windows[0].records)
    assert result.explanation_unavailable is False
    assert len(result.reasons) >= 3


def test_serving_encoding_matches_training_encoding(checkpoint, windows):
    scorer = FlowNetScorer.load(checkpoint)
    window = windows[0]
    features = extract_flow_window(window.records, key=WindowKey.SOURCE)
    trained_rows, _ = design_matrix(features, scorer._preprocessor)
    served = scorer.encode(list(window.records))
    assert served[: len(trained_rows)] == trained_rows
    assert len(served) == WINDOW
    assert all(all(value == 0.0 for value in row) for row in served[len(trained_rows) :])


def test_empty_window_is_refused_not_scored_as_zero(checkpoint):
    scorer = FlowNetScorer.load(checkpoint)
    with pytest.raises(ValueError):
        scorer.score([])


def test_missing_weights_is_a_named_error(checkpoint, tmp_path):
    broken = tmp_path / "broken"
    os.makedirs(broken)
    for name in ("flownet.config.json", "flownet.preprocessor.json"):
        with open(os.path.join(checkpoint, name), encoding="utf-8") as source:
            (broken / name).write_text(source.read(), encoding="utf-8")
    with pytest.raises(CheckpointError, match="flownet.pt"):
        FlowNetScorer.load(str(broken))


def test_endpoint_scores_a_window(checkpoint, windows, monkeypatch):
    monkeypatch.setenv("AEGIS_FLOWNET_CHECKPOINT_DIR", checkpoint)
    client = TestClient(create_app())
    body = {
        "flows": [r.model_dump(mode="json") for r in windows[0].records],
        "window_id": "w-1",
    }
    response = client.post("/score/windows", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["model_id"] == "flownet-test-0.0.1"
    assert payload["window_id"] == "w-1"
    assert 0.0 <= payload["score"] <= 1.0
    assert len(payload["reasons"]) >= 3


def test_endpoint_refuses_a_mixed_source_window_as_422(checkpoint, windows, monkeypatch):
    """A window spanning two sources is a client error, not a server fault."""
    monkeypatch.setenv("AEGIS_FLOWNET_CHECKPOINT_DIR", checkpoint)
    client = TestClient(create_app())
    flows = [r.model_dump(mode="json") for r in windows[0].records]
    other = [r.model_dump(mode="json") for r in windows[1].records]
    if {f["src_ip"] for f in flows} == {f["src_ip"] for f in other}:
        pytest.skip("fixture windows share a source; cannot build a mixed window")
    response = client.post("/score/windows", json={"flows": flows[:2] + other[:2]})
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "invalid_window"


def test_endpoint_refuses_without_a_checkpoint(tmp_path, windows, monkeypatch):
    monkeypatch.setenv("AEGIS_FLOWNET_CHECKPOINT_DIR", str(tmp_path / "absent"))
    client = TestClient(create_app())
    body = {"flows": [r.model_dump(mode="json") for r in windows[0].records]}
    response = client.post("/score/windows", json=body)
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "model_not_loaded"


def test_models_list_reports_the_checkpoint_with_its_real_address(checkpoint, monkeypatch):
    monkeypatch.setenv("AEGIS_FLOWNET_CHECKPOINT_DIR", checkpoint)
    client = TestClient(create_app())
    models = client.get("/models").json()["models"]
    flownet = [m for m in models if m["model_id"] == "flownet-test-0.0.1"]
    assert len(flownet) == 1
    assert flownet[0]["sha256"] == sha256_file(os.path.join(checkpoint, "flownet.pt"))
    assert flownet[0]["metrics"] == {}


def test_models_list_omits_flownet_without_a_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_FLOWNET_CHECKPOINT_DIR", str(tmp_path / "absent"))
    client = TestClient(create_app())
    ids = [m["model_id"] for m in client.get("/models").json()["models"]]
    assert "flownet-v1" not in ids
    assert not any(i.startswith("flownet-") for i in ids)
