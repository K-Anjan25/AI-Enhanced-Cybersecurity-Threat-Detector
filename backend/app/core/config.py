from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    PROJECT_NAME: str = "NOCTRA API"
    VERSION: str = "2.0.0"

    DATABASE_URL: str = "postgresql://postgres:root@localhost:5432/threat_ai_db"

    JWT_SECRET_KEY: str = "YOUR_SUPER_SECRET_KEY_CHANGE_THIS"
    JWT_REFRESH_SECRET_KEY: str = "YOUR_REFRESH_SECRET_KEY"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 1440

    # Runtime environment (development | production). In production, dev-only
    # conveniences such as returning a password-reset link in the API response
    # are disabled.
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Push-webhook ingest: max requests per connector per minute. Counted in
    # this process, so with N workers the effective ceiling is N x this value.
    # 0 disables the limiter.
    CONNECTOR_INGEST_RATE_LIMIT: int = 120

    # Separate key for connector credential encryption at rest. When not set,
    # falls back to JWT_SECRET_KEY for back-compat (with the documented trade
    # that rotating JWT_SECRET_KEY invalidates stored credentials). Setting
    # this allows JWT rotation without losing connector secrets.
    CONNECTOR_ENCRYPTION_KEY: str | None = None

    # Chat rate limiting: max questions per case per minute per user.
    ANALYST_CHAT_RATE_LIMIT: int = 20

    # Connector scheduled polling (Phase 39) — watches continuously without manual sync
    CONNECTOR_POLL_ENABLED: bool = True
    CONNECTOR_POLL_INTERVAL_SECONDS: int = 900  # 15 min
    CONNECTOR_POLL_JITTER_SECONDS: int = 60
    CONNECTOR_POLL_BACKOFF_BASE_SECONDS: int = 300  # 5 min base backoff on error
    CONNECTOR_POLL_BACKOFF_MAX_SECONDS: int = 3600  # 1 hour max

    # SSO / SCIM (Phase 40) — enterprise auth
    SSO_ENABLED: bool = False
    SSO_OIDC_ISSUER: str | None = None  # e.g. https://accounts.google.com
    SSO_OIDC_CLIENT_ID: str | None = None
    SSO_OIDC_CLIENT_SECRET: str | None = None
    SSO_OIDC_SCOPES: str = "openid email profile"
    SSO_JIT_PROVISIONING: bool = True  # create user on first SSO login
    SSO_DEFAULT_ROLE: str = "USER"  # role for JIT provisioned users

    SCIM_ENABLED: bool = False
    # Fallback global token (hashed comparison) — per-org tokens in DB are preferred
    SCIM_TOKEN: str | None = None

    # SAML (Phase 41)
    SSO_SAML_ENABLED: bool = False
    SSO_SAML_METADATA_URL: str | None = None
    SSO_SAML_ENTITY_ID: str | None = None
    SSO_SAML_ACS_URL: str | None = None
    SSO_SAML_SSO_URL: str | None = None
    SSO_SAML_CERTIFICATE: str | None = None
    # SAML hardening (Phase 43) — when True, fail closed if signature invalid or xmlsec missing
    SSO_SAML_REQUIRE_SIGNED_ASSERTIONS: bool = False
    SSO_SAML_REQUIRE_SIGNED_RESPONSE: bool = False

    # SCIM Groups→Roles mapping (Phase 43)
    SCIM_GROUPS_ROLE_MAPPING_ENABLED: bool = True

    # Connector OAuth (Phase 41) — GitHub App + Slack OAuth
    GITHUB_OAUTH_CLIENT_ID: str | None = None
    GITHUB_OAUTH_CLIENT_SECRET: str | None = None
    SLACK_OAUTH_CLIENT_ID: str | None = None
    SLACK_OAUTH_CLIENT_SECRET: str | None = None
    # Phase 46 — Google Workspace + AzureAD
    GOOGLE_OAUTH_CLIENT_ID: str | None = None
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = None
    AZUREAD_OAUTH_CLIENT_ID: str | None = None
    AZUREAD_OAUTH_CLIENT_SECRET: str | None = None
    AZUREAD_OAUTH_TENANT_ID: str | None = None  # e.g. common or tenant GUID
    CONNECTOR_OAUTH_REDIRECT_BASE: str | None = None  # e.g. http://localhost:8000 or frontend URL

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Auth security
    COOKIE_AUTH: bool = False
    COOKIE_SECURE: bool = True
    # Cookie SameSite policy. The dashboard is served from the same origin via
    # the Vite/nginx proxy, so "lax" suffices in a normal tab. When the preview
    # is embedded in a cross-site iframe (Arena live preview), "none" + Secure +
    # Partitioned (CHIPS) is required for the browser to store/send the cookie.
    COOKIE_SAMESITE: str = "lax"
    COOKIE_PARTITIONED: bool = False
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 10

    # Stream processing
    ENABLE_KAFKA: bool = False
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    RAW_LOG_TOPIC: str = "raw-logs"
    RAW_FLOW_TOPIC: str = "raw-flows"
    NORMALIZED_TOPIC: str = "events.normalized"
    ALERT_TOPIC: str = "alerts.raised"
    ACTION_TOPIC: str = "actions.executed"
    AUDIT_TOPIC: str = "audit.events"
    ML_SERVICE_URL: str = "http://localhost:8001"

    # LLM (Anthropic) reasoning for the autonomous analyst. Optional: when no
    # API key is configured the analyst degrades to a deterministic templated
    # narrative so the product loop still works end-to-end (see llm_client).
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"
    LLM_ENABLED: bool = True
    LLM_TIMEOUT: float = 30.0
    LLM_MAX_TOKENS: int = 1024

    # Email / SMTP settings (accepts both MAIL_* and SMTP_* env names)
    SMTP_HOST: str | None = Field(default=None, alias="MAIL_SERVER")
    SMTP_PORT: int | None = Field(default=None, alias="MAIL_PORT")
    SMTP_USER: str | None = Field(default=None, alias="MAIL_USERNAME")
    SMTP_PASSWORD: str | None = Field(default=None, alias="MAIL_PASSWORD")
    EMAIL_FROM: str | None = Field(default=None, alias="MAIL_DEFAULT_SENDER")

    # Threat detection engine defaults
    ENGINE_SENSITIVITY: str = "MEDIUM"      # LOW | MEDIUM | HIGH
    MAX_CONCURRENT_SCANS: int = 10
    AUTO_QUARANTINE: bool = False
    LOG_RETENTION_DAYS: int = 30

    # Phase 47: org isolation + API keys + rate limiting
    REDIS_URL: str | None = None  # e.g. redis://localhost:6379/0
    ORG_RATE_LIMIT_ENABLED: bool = True
    ORG_RATE_LIMIT_RPS: int = 100
    ORG_RATE_LIMIT_BURST: int = 200
    API_KEY_ENABLED: bool = True

    # Phase 49: threat intel enrichment
    VT_API_KEY: str | None = None
    ABUSEIPDB_API_KEY: str | None = None
    SHODAN_API_KEY: str | None = None
    OTX_API_KEY: str | None = None
    THREAT_INTEL_ENABLED: bool = True
    THREAT_INTEL_CACHE_TTL_SECONDS: int = 3600  # 1 hour
    THREAT_INTEL_TIMEOUT: float = 5.0

    # Phase 50: SOAR real execution
    SOAR_WEBHOOK_ENABLED: bool = True
    SOAR_SLACK_WEBHOOK_URL: str | None = None
    SOAR_JIRA_URL: str | None = None
    SOAR_JIRA_TOKEN: str | None = None
    SOAR_PAGERDUTY_KEY: str | None = None

    # Phase 53: compliance + S3
    S3_ENDPOINT: str | None = None
    S3_BUCKET: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None

    # Phase 54: org invites
    INVITE_TOKEN_EXPIRE_HOURS: int = 72
    MAX_USERS_PER_ORG: int = 100

    # Phase 58: HA
    REDIS_EVENTBUS_ENABLED: bool = False

    # Phase 60: billing
    BILLING_ENABLED: bool = False
    BILLING_FREE_ALERTS_PER_MONTH: int = 10000


settings = Settings()
