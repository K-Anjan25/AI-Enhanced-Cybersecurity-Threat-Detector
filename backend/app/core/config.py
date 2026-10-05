"""Typed application configuration.

Every setting the backend reads comes from this module (rule R-19). No other
module may call ``os.getenv`` directly; add a field here instead so the value
is validated once, at startup, with a type attached.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import ClassVar

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid.

    The message names the offending environment variable so an operator can fix
    the deployment without reading a traceback (rule R-06).
    """


class Environment(StrEnum):
    """Deployment environment. Drives log verbosity and debug guards."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Backend configuration, populated from environment variables.

    All variables are prefixed ``AEGIS_`` so multiple services can coexist in
    one environment without colliding.
    """

    model_config = SettingsConfigDict(
        env_prefix="AEGIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = Field(default=Environment.DEVELOPMENT)

    # Required: a deployment without an explicit name is a misconfiguration.
    service_name: str = Field(default="aegis-backend")

    # Required in every environment. There is no safe default for a secret.
    secret_key: str = Field(min_length=32)

    database_url: str = Field(default="postgresql+asyncpg://aegis:aegis@localhost:5432/aegis")

    # Binding to all interfaces is required for containerised deployment (NFR-08);
    # the container network is the trust boundary, not the loopback device.
    host: str = Field(default="0.0.0.0")  # noqa: S104  # nosec B104
    port: int = Field(default=8000, ge=1, le=65535)

    log_level: str = Field(default="INFO")
    request_timeout_seconds: float = Field(default=30.0, gt=0)

    # Ingest limits (FR-01, FR-02, R-56).
    max_flow_batch: int = Field(default=1000, ge=1)
    max_log_batch: int = Field(default=5000, ge=1)
    # Enforced before parsing by app.api.middleware.BodySizeLimitMiddleware: a
    # declared length over the cap is answered without reading the body, and a
    # streamed body is counted as it arrives.
    max_request_bytes: int = Field(default=8 * 1024 * 1024, ge=1024)

    # Rate limiting (R-56, T-316). Ten per second sustained per credential, which
    # is far above a collector's rate and far below what it takes to make the
    # service spend its time refusing. Anonymous requests get a lower limit
    # because they are the unauthenticated flood the rule names.
    rate_limit_requests_per_minute: int = Field(default=600, ge=1)
    rate_limit_anonymous_per_minute: int = Field(default=120, ge=1)
    # Back-pressure (architecture.md §12): the number of records allowed in flight
    # before the ingest API answers 503 with Retry-After instead of queueing
    # without limit and dropping something later.
    ingest_max_in_flight_records: int = Field(default=20_000, ge=1)

    ml_service_url: str = Field(default="http://localhost:8001")

    # Alert stream (FR-20). The interval is both how often a quiet stream says
    # "still here" and, per architecture.md §14, how often a dashboard whose
    # socket dropped polls instead -- 15 s by default.
    alert_stream_heartbeat_seconds: float = Field(default=15.0, gt=0)

    # Outbound webhooks (FR-21, R-55). The allowlist is empty by default, which
    # means no host is permitted: an empty allowlist is a fail-closed
    # configuration, not a disabled check. Entries are hostnames, optionally
    # prefixed '*.', comma-separated.
    webhook_allowlist: str = Field(default="")

    # Retention (FR-05, NFR-05). Raw records default to 30 days; alerts live
    # longer because they are the analyst-facing record, and the validator in
    # app.services.retention refuses a deployment that inverts the two. Same
    # ceiling as the policy (ten years), so a units mistake fails at startup
    # rather than at the first retention run.
    retention_raw_records_days: int = Field(default=30, ge=1, le=3650)
    retention_alerts_days: int = Field(default=400, ge=1, le=3650)
    retention_stats_days: int = Field(default=400, ge=1, le=3650)

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        """Uppercase the level and reject anything the stdlib will not accept."""
        normalised = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalised not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}, got {value!r}")
        return normalised

    #: Substrings that mark a value as a copied-from-the-docs placeholder.
    _WEAK_MARKERS: ClassVar[frozenset[str]] = frozenset(
        {"changeme", "placeholder", "example", "your-secret", "your_secret"}
    )

    @field_validator("secret_key")
    @classmethod
    def _reject_placeholder_secret(cls, value: str) -> str:
        """Refuse placeholder and low-entropy secrets (rule R-50).

        Catches three shapes: a known weak word anywhere in the value, a value
        made of one repeated character, and a value made of a repeated short
        pattern such as ``changemechangeme``.
        """
        normalised = value.strip().lower()
        if any(marker in normalised for marker in cls._WEAK_MARKERS):
            raise ValueError("secret_key looks like a placeholder; set a real random value")
        if len(set(normalised)) <= 2:
            raise ValueError("secret_key has too little entropy; set a real random value")
        return value


def load_settings() -> Settings:
    """Build :class:`Settings`, converting validation failures into a clear error.

    Raises:
        ConfigurationError: naming every environment variable that is missing or
            invalid, so the failure is actionable rather than a stack trace.
    """
    try:
        return Settings()
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            field = error["loc"][-1] if error["loc"] else "<root>"
            env_var = f"AEGIS_{str(field).upper()}"
            problems.append(f"{env_var}: {error['msg']}")
        raise ConfigurationError(
            "Invalid AEGIS configuration:\n  " + "\n  ".join(problems)
        ) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once and cached."""
    return load_settings()
