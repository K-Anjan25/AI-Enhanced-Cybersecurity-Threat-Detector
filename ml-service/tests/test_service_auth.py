"""The ML service's shared-secret gate: fail closed, reject wrong, admit right."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegis_ml.serving.app import create_app
from aegis_ml.serving.service_auth import SERVICE_TOKEN_HEADER

TOKEN = "service-test-token-with-enough-entropy-2026"  # pragma: allowlist secret


def _protected_get(app: FastAPI) -> str:
    """A GET operation on an inference or model router, with no path parameters.

    Read from the OpenAPI schema: this FastAPI version wraps included routers, so the
    route table alone does not show them.
    """
    for path, operations in app.openapi()["paths"].items():
        if "get" in operations and "{" not in path and not path.startswith("/internal"):
            if path not in {"/healthz", "/readyz", "/metrics"}:
                return path
    raise AssertionError("no protected GET route found")


def test_protected_routes_fail_closed_when_no_token_is_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("AEGIS_ML_SERVICE_TOKEN", raising=False)
    app = create_app()
    path = _protected_get(app)
    with TestClient(app) as client:
        assert client.get(path).status_code == 503
        assert client.get(path, headers={SERVICE_TOKEN_HEADER: "anything"}).status_code == 503


def test_probes_stay_public_even_without_a_token(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("AEGIS_ML_SERVICE_TOKEN", raising=False)
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/internal/healthz").status_code == 200


def test_a_missing_or_wrong_token_is_refused() -> None:
    app = create_app(service_token=TOKEN)
    path = _protected_get(app)
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        wrong = client.get(path, headers={SERVICE_TOKEN_HEADER: "not-the-token"})
        assert wrong.status_code == 401
        assert wrong.headers["www-authenticate"] == "AEGIS-Service-Token"


def test_the_right_token_is_admitted() -> None:
    app = create_app(service_token=TOKEN)
    path = _protected_get(app)
    with TestClient(app) as client:
        response = client.get(path, headers={SERVICE_TOKEN_HEADER: TOKEN})
    assert response.status_code not in {401, 503}


def test_token_is_read_from_the_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AEGIS_ML_SERVICE_TOKEN", TOKEN)
    app = create_app()
    assert app.state.service_token == TOKEN
