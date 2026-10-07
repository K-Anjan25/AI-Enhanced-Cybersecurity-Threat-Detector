"""Authentication composition and T-417's account/session boundary."""

from __future__ import annotations

from datetime import UTC, datetime

from app.auth.rbac import UNAUTHENTICATED_ROUTES
from app.core.config import Environment, Settings
from app.main import create_app
from app.services.audit_log import AuditAction
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = "auth-test-signing-key-with-enough-entropy-2026"  # pragma: allowlist secret
PASSWORD = "a-strong-test-password-for-auth"  # pragma: allowlist secret


def _settings(**overrides: object) -> Settings:
    """Build isolated test settings without reading the developer's environment."""
    values: dict[str, object] = {"env": Environment.TEST, "secret_key": SECRET}
    values.update(overrides)
    return Settings(**values)


def _audit_actions(app: FastAPI) -> list[AuditAction]:
    """Read the in-memory audit actions through its public query contract."""
    trail = app.state.audit_trail
    entries = trail.entries(
        start=datetime.min.replace(tzinfo=UTC),
        end=datetime.max.replace(tzinfo=UTC),
    )
    return [entry.record.action for entry in reversed(entries)]


def test_factory_installs_token_service_and_unconfigured_protected_routes_return_401() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        health = client.get("/healthz")
        models = client.get("/api/v1/models")

    assert health.status_code == 200
    assert models.status_code == 401
    assert models.headers["www-authenticate"] == "Bearer"


def test_development_setup_creates_a_user_chosen_admin_and_a_usable_session() -> None:
    app = create_app(_settings(env=Environment.DEVELOPMENT, dev_auth_setup_enabled=True))
    with TestClient(app) as client:
        status = client.get("/api/v1/auth/status")
        created = client.post(
            "/api/v1/auth/setup",
            json={"email": "Operator@Localhost", "password": PASSWORD},
        )
        assert created.status_code == 201
        pair = created.json()
        access = {"Authorization": f"Bearer {pair['access_token']}"}

        models = client.get("/api/v1/models", headers=access)
        users = client.get("/api/v1/users", headers=access)
        overview = client.get(
            "/api/v1/overview?start=2026-10-06T00:00:00Z&end=2026-10-07T00:00:00Z",
            headers=access,
        )
        wrong_login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "operator@localhost",
                "password": "not-the-password",  # pragma: allowlist secret
            },
        )
        second_setup = client.post(
            "/api/v1/auth/setup",
            json={"email": "another@localhost", "password": PASSWORD},
        )

    assert status.json() == {
        "setup_enabled": True,
        "setup_available": True,
        "account_exists": False,
    }
    assert status.headers["cache-control"] == "no-store"
    assert pair["role"] == "admin"
    assert pair["subject"] == "operator@localhost"
    assert PASSWORD not in created.text
    assert models.status_code == 200
    assert users.status_code == 200
    assert users.json()["items"][0]["email"] == "operator@localhost"
    assert overview.status_code == 200
    assert wrong_login.status_code == 401
    assert second_setup.status_code == 409
    assert _audit_actions(app) == [AuditAction.auth_setup]


def test_login_refresh_and_logout_use_password_and_rotating_refresh_credentials() -> None:
    app = create_app(
        _settings(
            bootstrap_admin_email="operator@localhost",
            bootstrap_admin_password=PASSWORD,
        )
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "OPERATOR@LOCALHOST", "password": PASSWORD},
        )
        original = login.json()
        rotated = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": original["refresh_token"]},
        )
        replay = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": original["refresh_token"]},
        )
        logout = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": rotated.json()["refresh_token"]},
        )
        after_logout = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": rotated.json()["refresh_token"]},
        )

    assert login.status_code == 200
    assert rotated.status_code == 200
    assert rotated.json()["access_token"] != original["access_token"]
    assert replay.status_code == 401
    assert logout.status_code == 204
    assert after_logout.status_code == 401
    assert _audit_actions(app) == [
        AuditAction.auth_login,
        AuditAction.auth_refresh,
        AuditAction.auth_logout,
    ]
    audit_records = app.state.audit_trail.entries(
        start=datetime.min.replace(tzinfo=UTC),
        end=datetime.max.replace(tzinfo=UTC),
    )
    assert PASSWORD not in repr(audit_records)
    assert original["refresh_token"] not in repr(audit_records)
    assert rotated.json()["refresh_token"] not in repr(audit_records)


def test_login_does_not_disclose_unknown_account_versus_wrong_password() -> None:
    app = create_app(
        _settings(
            bootstrap_admin_email="operator@localhost",
            bootstrap_admin_password=PASSWORD,
        )
    )
    with TestClient(app) as client:
        wrong_password = client.post(
            "/api/v1/auth/login",
            json={
                "email": "operator@localhost",
                "password": "another-wrong-password",  # pragma: allowlist secret
            },
        )
        unknown_account = client.post(
            "/api/v1/auth/login",
            json={"email": "missing@localhost", "password": PASSWORD},
        )

    assert wrong_password.status_code == unknown_account.status_code == 401
    assert wrong_password.json() == unknown_account.json()


def test_development_setup_is_closed_by_default_and_routes_are_explicitly_public() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        status = client.get("/api/v1/auth/status")
        setup = client.post(
            "/api/v1/auth/setup",
            json={"email": "operator@localhost", "password": PASSWORD},
        )

    assert status.status_code == 200
    assert status.json() == {
        "setup_enabled": False,
        "setup_available": False,
        "account_exists": False,
    }
    assert setup.status_code == 404
    assert {
        "/api/v1/auth/status",
        "/api/v1/auth/setup",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
    } <= UNAUTHENTICATED_ROUTES
