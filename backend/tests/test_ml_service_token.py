"""Backend calls to the ML service carry the shared secret, under the agreed header name."""

from __future__ import annotations

from typing import Any

from aegis_ml.serving.service_auth import SERVICE_TOKEN_HEADER as ML_HEADER
from app.services.ml_auth import SERVICE_TOKEN_HEADER, ml_request_headers
from app.services.ml_window_scorer import MlWindowScorer

SECRET = "backend-test-token-with-enough-entropy-2026"  # pragma: allowlist secret


def test_backend_and_ml_service_agree_on_the_header_name() -> None:
    assert SERVICE_TOKEN_HEADER == ML_HEADER


def test_header_is_added_only_when_a_token_is_configured() -> None:
    assert ml_request_headers(SECRET)[SERVICE_TOKEN_HEADER] == SECRET
    assert SERVICE_TOKEN_HEADER not in ml_request_headers(None)
    assert ml_request_headers(None)["Content-Type"] == "application/json"


def test_window_scorer_sends_the_token(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float = 0) -> None:
        seen["headers"] = dict(request.header_items())
        raise OSError("stop after capturing the request")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    scorer = MlWindowScorer("http://ml-service:8001", token=SECRET)
    flows: list[dict[str, object]] = [{"src": "10.0.0.1", "dst": "10.0.0.2"}]
    try:
        scorer.score(flows)
    except OSError:
        pass
    assert seen["headers"].get(SERVICE_TOKEN_HEADER.capitalize()) == SECRET or any(
        key.lower() == SERVICE_TOKEN_HEADER.lower() and value == SECRET
        for key, value in seen["headers"].items()
    )
