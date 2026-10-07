"""Tests for configuration loading (T-002: fail startup with a named error)."""

from __future__ import annotations

import pytest
from app.core.config import ConfigurationError, Environment, Settings, load_settings
from pydantic import ValidationError


def test_missing_secret_key_raises_configuration_error_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The error must name AEGIS_SECRET_KEY, not dump a pydantic traceback."""
    monkeypatch.delenv("AEGIS_SECRET_KEY", raising=False)
    monkeypatch.setattr(Settings, "model_config", Settings.model_config | {"env_file": None})

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()

    message = str(excinfo.value)
    assert "AEGIS_SECRET_KEY" in message
    assert "Invalid AEGIS configuration" in message


def test_placeholder_secret_is_rejected() -> None:
    """A secret padded out of the word 'changeme' is not a secret (R-50)."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            env=Environment.TEST,
            secret_key="changeme" * 5,  # 40 chars, so it clears min_length first
        )

    assert "placeholder" in str(excinfo.value).lower()


def test_single_character_secret_is_rejected() -> None:
    """Length alone is not entropy."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(env=Environment.TEST, secret_key="a" * 40)

    assert "entropy" in str(excinfo.value).lower()


def test_short_secret_is_rejected() -> None:
    """Secrets must carry enough entropy to be usable for signing."""
    with pytest.raises(ValidationError):
        Settings(env=Environment.TEST, secret_key="too-short")


def test_invalid_log_level_is_rejected() -> None:
    """An unparseable level fails loudly instead of silently logging nothing."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            env=Environment.TEST, secret_key="K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu", log_level="VERBOSE"
        )

    assert "log_level" in str(excinfo.value).lower()


def test_log_level_is_normalised_to_uppercase() -> None:
    """Operators write 'info'; the stdlib wants 'INFO'."""
    settings = Settings(
        env=Environment.TEST, secret_key="K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu", log_level="debug"
    )

    assert settings.log_level == "DEBUG"


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The AEGIS_ prefix maps environment variables onto typed fields (R-19)."""
    monkeypatch.setattr(Settings, "model_config", Settings.model_config | {"env_file": None})
    monkeypatch.setenv("AEGIS_SECRET_KEY", "K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu")
    monkeypatch.setenv("AEGIS_ENV", "production")
    monkeypatch.setenv("AEGIS_SERVICE_NAME", "aegis-backend-prod")
    monkeypatch.setenv("AEGIS_PORT", "9000")
    monkeypatch.setenv("AEGIS_MAX_FLOW_BATCH", "250")
    monkeypatch.setenv("AEGIS_BOOTSTRAP_ADMIN_EMAIL", "Operator@Example.Test")
    monkeypatch.setenv("AEGIS_BOOTSTRAP_ADMIN_PASSWORD", "test-only-strong-password-2026")

    settings = load_settings()

    assert settings.env is Environment.PRODUCTION
    assert settings.service_name == "aegis-backend-prod"
    assert settings.port == 9000
    assert settings.max_flow_batch == 250
    assert settings.secret_key == "K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu"
    assert settings.bootstrap_admin_email == "operator@example.test"
    assert settings.bootstrap_admin_password is not None
    assert settings.bootstrap_admin_password.get_secret_value() == "test-only-strong-password-2026"


def test_production_requires_an_explicit_bootstrap_account() -> None:
    with pytest.raises(ValidationError, match="production requires AEGIS_BOOTSTRAP_ADMIN_EMAIL"):
        Settings(env=Environment.PRODUCTION, secret_key="K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu")


def test_bootstrap_credentials_must_be_configured_as_a_pair() -> None:
    with pytest.raises(ValidationError, match="set both AEGIS_BOOTSTRAP_ADMIN_EMAIL"):
        Settings(
            env=Environment.DEVELOPMENT,
            secret_key="K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu",
            bootstrap_admin_email="operator@example.test",
        )


def test_development_setup_flag_is_rejected_outside_development() -> None:
    with pytest.raises(ValidationError, match="permitted only in development"):
        Settings(
            env=Environment.TEST,
            secret_key="K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu",
            dev_auth_setup_enabled=True,
        )


def test_out_of_range_port_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bounds declared on the field are enforced at load time."""
    monkeypatch.setattr(Settings, "model_config", Settings.model_config | {"env_file": None})
    monkeypatch.setenv("AEGIS_SECRET_KEY", "K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu")
    monkeypatch.setenv("AEGIS_PORT", "99999")

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()

    assert "AEGIS_PORT" in str(excinfo.value)
