"""Tests for the resilient ML client: timeouts, retries, and heuristic fallback."""

import pytest
import requests


def _mock_down_post(url, json=None, timeout=None, **kwargs):
    raise requests.ConnectionError("ML service unreachable")


def test_predict_log_uses_fallback_when_ml_down(monkeypatch):
    from app.services import ml_client

    monkeypatch.setattr(ml_client.requests, "post", _mock_down_post)

    result = ml_client.predict_log({"message": "failed login attempt from 10.0.0.5"})
    assert result["fallback"] is True
    assert result["is_anomaly"] is True
    assert result["anomaly_score"] > 0
    assert "failed login" in result["indicators"]


def test_predict_log_fallback_clean_message(monkeypatch):
    from app.services import ml_client

    monkeypatch.setattr(ml_client.requests, "post", _mock_down_post)

    result = ml_client.predict_log({"message": "user logged in successfully"})
    assert result["fallback"] is True
    assert result["is_anomaly"] is False


def test_predict_network_uses_fallback_when_ml_down(monkeypatch):
    from app.services import ml_client

    monkeypatch.setattr(ml_client.requests, "post", _mock_down_post)

    result = ml_client.predict_network({"bytes": 2_000_000, "duration": 10, "packets": 5_000})
    assert result["fallback"] is True
    assert result["is_anomaly"] is True


def test_predict_log_batch_falls_back_per_item(monkeypatch):
    from app.services import ml_client

    monkeypatch.setattr(ml_client.requests, "post", _mock_down_post)

    results = ml_client.predict_log_batch([
        {"message": "sql injection attempt"},
        {"message": "warm boot complete"},
    ])
    assert len(results) == 2
    assert all(isinstance(r, dict) for r in results)
    assert results[0]["is_anomaly"] is True
    assert results[1]["is_anomaly"] is False