"""Tests for the model benchmark harness (ml-service)."""

import os

from app.benchmark import run_benchmark, benchmark_log, benchmark_email

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "model")


def test_benchmark_reads_metrics_into_report(tmp_path):
    report = run_benchmark(model_dir=MODEL_DIR, cicids_path="does-not-exist/*.csv", persist=False)
    by_name = {m["model"]: m for m in report["models"]}
    assert "log_model" in by_name and "email_model" in by_name
    assert "version" in report and "run_at" in report


def test_log_benchmark_returns_metrics_dict():
    result = benchmark_log(MODEL_DIR)
    assert result["status"] in ("ok", "skipped")
    if result["status"] == "ok":
        assert {"accuracy", "precision", "recall", "f1"} <= set(result["metrics"].keys())
        assert 0.0 <= result["metrics"]["f1"] <= 1.0


def test_email_benchmark_returns_metrics_dict():
    result = benchmark_email(MODEL_DIR)
    assert result["status"] in ("ok", "skipped")
    if result["status"] == "ok":
        assert {"accuracy", "precision", "recall", "f1"} <= set(result["metrics"].keys())


def test_network_benchmark_skips_without_dataset(tmp_path):
    from app.benchmark import benchmark_network

    result = benchmark_network(MODEL_DIR, "missing/*.csv")
    assert result["status"] == "skipped"


def test_benchmark_endpoint_available():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.get("/benchmark")
    assert resp.status_code == 200
    assert isinstance(resp.json()["models"], list)