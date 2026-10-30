"""Self-service signup (viewer only, off by default) and capture-control access rules."""

from __future__ import annotations

from datetime import UTC, datetime

from app.auth.rbac import UNAUTHENTICATED_ROUTES, Role
from app.core.config import Environment, Settings
from app.main import create_app
from app.services.audit_log import AuditAction
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = "signup-test-signing-key-with-enough-entropy-2026"  # pragma: allowlist secret
PASSWORD = "a-strong-signup-password"  # pragma: allowlist secret
NEW = {"email": "New.Viewer@Example.test", "password": PASSWORD}


def _app(**overrides: object) -> FastAPI:
    values: dict[str, object] = {"env": Environment.TEST, "secret_key": SECRET}
    values.update(overrides)
    return create_app(Settings(**values))  # type: ignore[arg-type]


def _token(app: FastAPI, role: Role, subject: str = "ops@example.test") -> dict[str, str]:
    pair = app.state.token_service.issue(subject, role.value)
    return {"Authorization": f"Bearer {pair.access_token}"}


def _actions(app: FastAPI) -> list[AuditAction]:
    entries = app.state.audit_trail.entries(
        start=datetime.min.replace(tzinfo=UTC), end=datetime.max.replace(tzinfo=UTC)
    )
    return [entry.record.action for entry in entries]


def test_signup_is_off_by_default_and_hidden_as_not_found() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/signup", json=NEW)
    assert response.status_code == 404


def test_signup_creates_only_a_viewer_and_that_account_can_sign_in() -> None:
    app = _app(signup_enabled=True)
    with TestClient(app) as client:
        created = client.post("/api/v1/auth/signup", json=NEW)
        assert created.status_code == 202
        login = client.post("/api/v1/auth/login", json=NEW)
    assert login.status_code == 200
    assert login.json()["role"] == "viewer"
    assert login.json()["subject"] == "new.viewer@example.test"
    assert AuditAction.auth_signup in _actions(app)


def test_signup_reply_is_identical_for_a_taken_address() -> None:
    app = _app(signup_enabled=True)
    with TestClient(app) as client:
        first = client.post("/api/v1/auth/signup", json=NEW)
        second = client.post("/api/v1/auth/signup", json=NEW)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert _actions(app).count(AuditAction.auth_signup) == 1


def test_signup_cannot_grant_a_role_and_is_not_an_admin_back_door() -> None:
    app = _app(signup_enabled=True)
    with TestClient(app) as client:
        client.post("/api/v1/auth/signup", json={**NEW, "role": "admin"})  # extra field
        assert client.post("/api/v1/auth/signup", json=NEW).status_code == 202
        login = client.post("/api/v1/auth/login", json=NEW)
    assert login.json()["role"] == "viewer"


def test_signup_route_is_declared_unauthenticated() -> None:
    assert "/api/v1/auth/signup" in UNAUTHENTICATED_ROUTES


def test_capture_state_requires_a_token_and_an_operator_role() -> None:
    app = _app()
    with TestClient(app) as client:
        assert client.get("/api/v1/capture/state").status_code == 401
        for role in (Role.VIEWER, Role.ANALYST):
            headers = _token(app, role)
            assert client.get("/api/v1/capture/state", headers=headers).status_code == 403
            assert (
                client.put(
                    "/api/v1/capture/state", json={"running": True}, headers=headers
                ).status_code
                == 403
            )


def test_responder_and_admin_can_start_and_stop_and_every_change_is_audited() -> None:
    app = _app()
    with TestClient(app) as client:
        headers = _token(app, Role.RESPONDER)
        started = client.put(
            "/api/v1/capture/state",
            json={"running": True, "engines": ["zeek", "Suricata", "zeek"]},
            headers=headers,
        )
        assert started.status_code == 200
        body = started.json()
        assert body["running"] is True
        assert body["engines"] == ["zeek", "suricata"]  # normalised, de-duplicated
        assert body["version"] == 1
        assert body["changed_by"] == "ops@example.test"

        stopped = client.put(
            "/api/v1/capture/state",
            json={"running": False, "engines": []},
            headers=_token(app, Role.ADMIN, "admin@example.test"),
        )
        assert stopped.json()["version"] == 2
        assert client.get("/api/v1/capture/state", headers=headers).json()["running"] is False
    assert _actions(app).count(AuditAction.capture_state) == 2


def test_unknown_engine_and_start_without_an_engine_are_refused() -> None:
    app = _app()
    with TestClient(app) as client:
        headers = _token(app, Role.ADMIN)
        unknown = client.put(
            "/api/v1/capture/state",
            json={"running": True, "engines": ["wireshark"]},
            headers=headers,
        )
        none = client.put(
            "/api/v1/capture/state", json={"running": True, "engines": []}, headers=headers
        )
        extra = client.put(
            "/api/v1/capture/state",
            json={"running": True, "engines": ["zeek"], "shell": "rm -rf /"},
            headers=headers,
        )
    assert unknown.status_code == 422
    assert none.status_code == 422
    assert extra.status_code == 422
    assert AuditAction.capture_state not in _actions(app)
