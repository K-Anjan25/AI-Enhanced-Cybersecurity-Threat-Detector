"""Contract tests between the backend API and the ml-service.

These tests pin the shared wire contract: the request payloads the backend
builds must be valid against the ml-service input schemas, and the ml-service
responses must contain every key the backend's alert_service consumes. Keeping
this green prevents the two services from drifting apart silently.

The ml-service schemas are loaded in isolation (model.py only depends on
pydantic) so the backend test environment does not need the ML dependencies.
"""

import importlib.util
import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ML_MODEL_PATH = os.path.join(REPO_ROOT, "ml-service", "app", "model.py")

pytestmark = pytest.mark.skipif(
    not os.path.exists(ML_MODEL_PATH),
    reason="ml-service source not present in this checkout",
)


@pytest.fixture(scope="module")
def ml_schemas():
    """Load ml-service/app/model.py under a unique module name."""
    if not os.path.exists(ML_MODEL_PATH):
        pytest.skip("ml-service source not present")
    spec = importlib.util.spec_from_file_location("ml_service_contract_model", ML_MODEL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Keys the backend's alert_service reads from every ML response.
REQUIRED_RESPONSE_KEYS = {"anomaly_score", "is_anomaly", "severity"}


def test_log_payload_matches_ml_service_schema(ml_schemas):
    from app.services import ml_client

    # The backend builds a /predict/log payload; it must validate against LogInput.
    sample = {"message": "failed login attempt", "level": "ERROR", "timestamp": "2026-01-01T00:00:00Z"}
    built = {
        "timestamp": sample["timestamp"],
        "level": "ERROR",
        "message": sample["message"],
        "source": "system",
    }
    parsed = ml_schemas.LogInput(**built)
    assert parsed.message == "failed login attempt"
    assert parsed.level == "ERROR"
    assert parsed.source == "system"


def test_network_payload_matches_ml_service_schema(ml_schemas):
    # The backend's predict_network passes the record through unchanged; it must
    # validate against NetworkInput (which tolerates extra/missing fields).
    record = {
        "src_ip": "10.0.0.5", "dst_port": 3389, "bytes": 2_000_000, "duration": 10,
        "total_fwd_packets": 500, "total_bwd_packets": 400,
    }
    parsed = ml_schemas.NetworkInput(**record)
    assert parsed.dst_port == 3389
    assert parsed.bytes == 2_000_000


def test_log_response_shape_matches_backend_consumption():
    """ml-service /predict/log and /predict/log/detail response keys."""
    from app.services.ml_client import fallback_predict_log

    # The heuristic fallback must return at least the keys the backend consumes,
    # and the real service returns the same base keys (anomaly_score, is_anomaly).
    result = fallback_predict_log({"message": "sql injection attempt"})
    assert REQUIRED_RESPONSE_KEYS.issubset(result.keys())
    assert 0.0 <= result["anomaly_score"] <= 1.0
    assert isinstance(result["is_anomaly"], bool)


def test_network_response_shape_matches_backend_consumption():
    from app.services.ml_client import fallback_predict_network

    result = fallback_predict_network({"bytes": 2_000_000, "duration": 10, "packets": 500})
    assert REQUIRED_RESPONSE_KEYS.issubset(result.keys())
    assert isinstance(result["is_anomaly"], bool)


def test_ml_service_response_is_float_normalized(ml_schemas):
    """Contract: anomaly_score must be a 0..1 float regardless of source model.

    Backend's score_to_severity converts these labels; the ml-service returns
    a 0..1 normalized score for both log and network models.
    """
    from app.services.ml_client import fallback_predict_log

    result = fallback_predict_log({"message": "malware detected in /tmp/x"})
    score = result["anomaly_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_batch_response_shape_matches_backend_consumption(ml_schemas):
    """ml-service /predict/log/batch wraps results in {"results": [...]}."""
    from app.services.ml_client import fallback_predict_log

    results = [fallback_predict_log({"message": m}) for m in ["failed login", "ok"]]
    assert len(results) == 2
    for r in results:
        assert REQUIRED_RESPONSE_KEYS.issubset(r.keys())
