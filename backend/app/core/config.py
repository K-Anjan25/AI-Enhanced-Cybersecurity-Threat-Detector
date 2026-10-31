"""Typed application configuration.

Every setting the backend reads comes from this module (rule R-19). No other
module may call ``os.getenv`` directly; add a field here instead so the value
is validated once, at startup, with a type attached.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import ClassVar

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
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


class LogStoreMode(StrEnum):
    """Whether reads are answered from the log store, the tail, or by inference.

    T-419. ``AUTO`` is the interesting one: the store is used when the deployment
    *named* a database URL (``AEGIS_DATABASE_URL`` is set), and the tail is used
    when it did not. The distinction is between a URL the deployment chose and the
    built-in default, which exists so ``alembic`` has something to dial -- the
    default must not silently switch a process's read path to a database it was
    never told about. ``ON`` and ``OFF`` are for a deployment that wants to be
    explicit either way, and both are recorded in the response's ``source``.
    """

    AUTO = "auto"
    ON = "on"
    OFF = "off"


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

    # Authentication bootstrap (T-417). Passwords are hashed immediately and are
    # never logged or returned. Production must configure an initial operator; a
    # local setup form is separately opt-in and development-only.
    bootstrap_admin_email: str | None = Field(default=None, max_length=254)
    bootstrap_admin_password: SecretStr | None = Field(default=None, repr=False)
    dev_auth_setup_enabled: bool = Field(default=False)
    #: Self-service viewer accounts. Off by default: an open signup form on a
    #: deployment is a decision the operator makes, and it only ever creates viewers.
    signup_enabled: bool = Field(default=False)
    #: Assistant backend: "rules" (default, no model) or "openai" (an OpenAI-compatible server).
    assistant_backend: str = Field(default="rules", pattern="^(rules|openai)$")
    assistant_base_url: str = Field(default="http://localhost:11434/v1", max_length=300)
    assistant_model: str = Field(default="qwen2.5:1.5b", max_length=200)
    assistant_timeout_seconds: float = Field(default=20.0, gt=0, le=120)

    # Required: a deployment without an explicit name is a misconfiguration.
    service_name: str = Field(default="aegis-backend")

    # Required in every environment. There is no safe default for a secret.
    secret_key: str = Field(min_length=32)

    # T-323. The dialect is part of the contract with the deployment: the driver
    # named here is the one backend/pyproject.toml declares, so a plain install
    # can open the URL it ships with -- checked statically by
    # scripts/check_compose.py and through a subprocess by
    # tests/test_database_driver.py. Alembic opens the same URL with a
    # *synchronous* engine at deploy time, which is why the driver is psycopg 3
    # rather than an async-only one.
    database_url: str = Field(default="postgresql+psycopg://aegis:aegis@localhost:5432/aegis")

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

    # Shared state (memory.md multi-replica note). Empty keeps every counter in the
    # process. Set, the login throttle counts failures in Redis so N replicas share
    # one limit rather than allowing N times the guesses. Compose caps Redis memory.
    redis_url: str = Field(default="")
    # Login throttle (T4 credential abuse). Per account, and per source address with
    # a larger allowance because many users can share one NAT address.
    login_account_max_failures: int = Field(default=5, ge=1)
    login_address_max_failures: int = Field(default=100, ge=1)
    login_window_seconds: int = Field(default=900, ge=1)

    # Tracing (NFR-07, T-317). Empty means no exporter: spans are still created
    # and their ids still propagate to the alert record, and nothing leaves the
    # process. Set it to an OTLP/HTTP endpoint to ship spans to a collector.
    otel_exporter_endpoint: str = Field(default="")

    ml_service_url: str = Field(default="http://localhost:8001")
    #: Shared secret for the ML service (AEGIS_ML_SERVICE_TOKEN). Sent on every call;
    #: the ML service refuses protected routes without it.
    ml_service_token: SecretStr | None = Field(default=None, repr=False)

    # Kafka bootstrap servers (host:port). Empty keeps the flow path in-process (the
    # rule-based DetectionEngine). Set, flows go to flows.raw and a live consumer
    # scores them (D-085). Compose sets kafka:9092.
    kafka_bootstrap_servers: str = Field(default="")

    # Directory of ``eval@2`` reports (``*.eval.json`` with their ``*.config.json``)
    # to attach to registered model versions. Empty means no evaluations are loaded.
    ml_eval_reports_dir: str = Field(default="")

    # Score each source window with the trained flow model in the detection cycle
    # (2b). Rules run either way; a model that cannot be reached adds no alerts.
    ml_detection_enabled: bool = Field(default=True)

    # Alert stream (FR-20). The interval is both how often a quiet stream says
    # "still here" and, per architecture.md §14, how often a dashboard whose
    # socket dropped polls instead -- 15 s by default.
    alert_stream_heartbeat_seconds: float = Field(default=15.0, gt=0)

    # T-407. The log tail is bounded in both directions and both bounds come from
    # here: a deployment that wants an hour of lines or half a minute can say so,
    # and neither can be set to "unbounded". 20,000 lines is enough for the screen's
    # own promise -- ten thousand identical lines collapse into one row with a
    # count -- because the fold sees the whole tail rather than a page of it.
    log_tail_lines: int = Field(default=20_000, ge=1)
    log_tail_max_age_seconds: float = Field(default=900.0, gt=0)

    # T-419. Which of the two log read models answers. ``auto`` means "the store
    # when AEGIS_DATABASE_URL was named, the tail otherwise" -- see LogStoreMode.
    log_store: LogStoreMode = Field(default=LogStoreMode.AUTO)
    # How long the store's description of itself (its oldest and newest line and
    # how many it holds) is reused. It changes slowly and a read is not worth three
    # aggregate queries, but a number nobody refreshes is a lie with a timestamp, so
    # the cache is short and its age is reported with the read.
    log_store_coverage_ttl_seconds: float = Field(default=30.0, gt=0)

    # T-418. Which of the two flow read models answers, decided by the same rule as the
    # log store: ``auto`` means "the store when AEGIS_DATABASE_URL was named, the
    # in-process rollup otherwise". Separate from ``log_store`` on purpose -- a
    # deployment may store its logs and roll its traffic up in memory, and the two
    # screens say which they got rather than sharing one answer.
    flow_store: LogStoreMode = Field(default=LogStoreMode.AUTO)
    # Where user accounts and their password hashes live (T-417). ``auto`` means "the
    # Postgres users table when AEGIS_DATABASE_URL was named, process memory otherwise"
    # -- the same rule as the stores above. In memory, every account is lost on restart.
    user_store: LogStoreMode = Field(default=LogStoreMode.AUTO)
    # The rollup's retention, in minutes. The default is the widest range the traffic
    # explorer offers, so every offered window is fully answerable by a rollup; a wider
    # one is answered for the part it still holds, and the caveats say so.
    flow_rollup_minutes: int = Field(default=60, ge=1)

    # Outbound webhooks (FR-21, R-55). The allowlist is empty by default, which
    # means no host is permitted: an empty allowlist is a fail-closed
    # configuration, not a disabled check. Entries are hostnames, optionally
    # prefixed '*.', comma-separated.
    webhook_allowlist: str = Field(default="")

    # FR-43. OIDC sign-in for enterprise deployments. Off by default: the local
    # password path is the v1.0 baseline. When enabled, every field below is
    # required and the validator refuses a non-HTTPS issuer or redirect outside
    # development (see app.auth.oidc for what the flow checks).
    oidc_enabled: bool = Field(default=False)
    oidc_issuer: str = Field(default="")
    oidc_client_id: str = Field(default="")
    oidc_client_secret: SecretStr | None = Field(default=None)
    oidc_redirect_uri: str = Field(default="")

    # Retention (FR-05, NFR-05). Raw records default to 30 days; alerts live
    # longer because they are the analyst-facing record, and the validator in
    # app.services.retention refuses a deployment that inverts the two. Same
    # ceiling as the policy (ten years), so a units mistake fails at startup
    # rather than at the first retention run.
    retention_raw_records_days: int = Field(default=30, ge=1, le=3650)
    retention_alerts_days: int = Field(default=400, ge=1, le=3650)
    retention_stats_days: int = Field(default=400, ge=1, le=3650)
    # How often the scheduler runs retention (NFR-05). Retention used to run only when an
    # operator called the route, so an unattended deployment kept everything. 0 turns the
    # scheduler off; it is not created at all, rather than started and left idle.
    retention_interval_seconds: int = Field(default=86_400, ge=0, le=604_800)
    # FR-05's raw window, applied by the broker to the flow topic (``retention.ms``).
    # Kafka is where raw records live, so it may not hold them longer than the policy
    # promises: the validator below refuses a value above the raw window.
    kafka_retention_hours: int = Field(default=720, ge=1, le=87_600)
    # The longest a flow waits for its 50-flow window before the window is scored partial
    # (live path). 0 scores every flow as it arrives; large values approach batch windows.
    live_max_window_wait_seconds: float = Field(default=2.0, ge=0.0, le=300.0)
    # FR-15: a repeat of the same (entity, family) inside this window is absorbed into
    # the open alert as one more occurrence, not raised as a new alert.
    alert_cool_down_minutes: int = Field(default=15, ge=1, le=1440)

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        """Uppercase the level and reject anything the stdlib will not accept."""
        normalised = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalised not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}, got {value!r}")
        return normalised

    @field_validator("bootstrap_admin_email", mode="before")
    @classmethod
    def _empty_bootstrap_email_is_unset(cls, value: object) -> object:
        """Let environment forwarding of an unset optional email stay unset."""
        return None if value == "" else value

    @field_validator("bootstrap_admin_password", mode="before")
    @classmethod
    def _empty_bootstrap_password_is_unset(cls, value: object) -> object:
        """Let environment forwarding of an unset optional password stay unset."""
        return None if value == "" else value

    @field_validator("bootstrap_admin_email")
    @classmethod
    def _normalise_bootstrap_email(cls, value: str | None) -> str | None:
        """Canonicalise the one configured bootstrap address."""
        if value is None:
            return None
        normalised = value.strip().casefold()
        local, separator, domain = normalised.partition("@")
        if (
            not separator
            or not local
            or not domain
            or "@" in domain
            or any(character.isspace() for character in normalised)
        ):
            raise ValueError("AEGIS_BOOTSTRAP_ADMIN_EMAIL must be a valid email address")
        return normalised

    @model_validator(mode="after")
    def _validate_kafka_retention(self) -> Settings:
        """Refuse a Kafka window that outlives the raw-record window FR-05 promises."""
        raw_hours = self.retention_raw_records_days * 24
        if self.kafka_retention_hours > raw_hours:
            raise ValueError(
                f"AEGIS_KAFKA_RETENTION_HOURS ({self.kafka_retention_hours}) must not exceed "
                f"the raw-record window, AEGIS_RETENTION_RAW_RECORDS_DAYS x 24 = {raw_hours}: "
                "Kafka holding raw records longer than the policy is the inversion FR-05 forbids"
            )
        return self

    @model_validator(mode="after")
    def _validate_auth_bootstrap(self) -> Settings:
        """Require a real configured production entry point; keep setup opt-in."""
        email = self.bootstrap_admin_email
        password = self.bootstrap_admin_password
        if (email is None) != (password is None):
            raise ValueError(
                "set both AEGIS_BOOTSTRAP_ADMIN_EMAIL and "
                "AEGIS_BOOTSTRAP_ADMIN_PASSWORD, or neither"
            )
        if password is not None and len(password.get_secret_value()) < 12:
            raise ValueError("AEGIS_BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters")
        if self.dev_auth_setup_enabled and self.env is not Environment.DEVELOPMENT:
            raise ValueError("AEGIS_DEV_AUTH_SETUP_ENABLED is permitted only in development")
        if self.oidc_enabled:
            missing = [
                name
                for name, value in (
                    ("AEGIS_OIDC_ISSUER", self.oidc_issuer),
                    ("AEGIS_OIDC_CLIENT_ID", self.oidc_client_id),
                    ("AEGIS_OIDC_REDIRECT_URI", self.oidc_redirect_uri),
                )
                if not value
            ]
            if missing or self.oidc_client_secret is None:
                raise ValueError(
                    "AEGIS_OIDC_ENABLED requires AEGIS_OIDC_ISSUER, AEGIS_OIDC_CLIENT_ID, "
                    "AEGIS_OIDC_CLIENT_SECRET and AEGIS_OIDC_REDIRECT_URI"
                )
            if self.env is not Environment.DEVELOPMENT:
                for name, value in (
                    ("AEGIS_OIDC_ISSUER", self.oidc_issuer),
                    ("AEGIS_OIDC_REDIRECT_URI", self.oidc_redirect_uri),
                ):
                    if not value.startswith("https://"):
                        raise ValueError(f"{name} must be an https URL outside development")
        if self.env is Environment.PRODUCTION and email is None:
            raise ValueError(
                "production requires AEGIS_BOOTSTRAP_ADMIN_EMAIL and AEGIS_BOOTSTRAP_ADMIN_PASSWORD"
            )
        return self

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
