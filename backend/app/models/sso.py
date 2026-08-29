"""SSO provider + SCIM token + SCIM Group + Connector OAuth models — enterprise auth.

Phase 40: OIDC + SCIM Users minimal
Phase 41: SAML, SCIM Groups membership sync + Bulk, Connector OAuth (GitHub App, Slack OAuth)

Honest scope:
- SSO: OIDC + SAML 2.0 (SP-initiated). SAML verifies signature if xmlsec available, else logs warning and parses without verification (documented gap).
- SCIM: Users CRUD + Groups CRUD + membership sync + Bulk
- Connector OAuth: GitHub App + Slack OAuth for real API tokens, encrypted at rest
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
)

from app.core.database import Base


class SsoProvider(Base):
    __tablename__ = "sso_providers"
    __table_args__ = (
        UniqueConstraint("org_id", "provider_type", name="uq_sso_org_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)
    provider_type = Column(String(20), nullable=False, default="oidc")  # oidc | saml
    display_name = Column(String(120), nullable=False, default="Corporate SSO")

    # OIDC
    issuer = Column(Text, nullable=True)  # e.g. https://accounts.google.com or https://login.microsoftonline.com/tenant/v2.0
    client_id = Column(String(255), nullable=True)
    client_secret_encrypted = Column(Text, nullable=True)  # encrypted at rest
    scopes = Column(String(500), nullable=True, default="openid email profile")

    # SAML (Phase 41)
    saml_metadata_url = Column(Text, nullable=True)
    saml_entity_id = Column(Text, nullable=True)  # SP entity ID
    saml_acs_url = Column(Text, nullable=True)  # Assertion Consumer Service URL
    saml_sso_url = Column(Text, nullable=True)  # IdP SSO URL (from metadata or manual)
    saml_certificate = Column(Text, nullable=True)  # IdP cert for verification
    saml_nameid_format = Column(String(255), nullable=True, default="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress")

    enabled = Column(Boolean, default=True, nullable=False)
    jit_provisioning = Column(Boolean, default=True, nullable=False)  # create user on first SSO login

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ScimToken(Base):
    __tablename__ = "scim_tokens"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)

    # token is shown once on creation, stored as hash
    token_hash = Column(String(255), nullable=False, unique=True, index=True)
    token_prefix = Column(String(20), nullable=False)  # first 8 chars for display
    name = Column(String(120), nullable=False, default="SCIM Provisioning Token")

    created_by = Column(String(120), nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class ScimGroup(Base):
    """SCIM Group — Phase 41 Groups membership sync."""

    __tablename__ = "scim_groups"
    __table_args__ = (
        UniqueConstraint("org_id", "display_name", name="uq_scim_group_org_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)

    display_name = Column(String(255), nullable=False)
    external_id = Column(String(255), nullable=True, index=True)

    # Members stored as JSON array of {value: user_id, display: username, type: User}
    members = Column(JSON, nullable=True, default=list)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ConnectorOAuth(Base):
    """Connector OAuth tokens — Phase 41 GitHub App + Slack OAuth.

    Stores encrypted access/refresh tokens per org per connector.
    """

    __tablename__ = "connector_oauth"
    __table_args__ = (
        UniqueConstraint("org_id", "connector_id", name="uq_connector_oauth_org"),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)
    connector_id = Column(String(40), nullable=False, index=True)  # github | slack

    provider = Column(String(50), nullable=False)  # github | slack
    access_token_encrypted = Column(Text, nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)
    token_type = Column(String(20), nullable=True, default="Bearer")
    expires_at = Column(DateTime, nullable=True)
    scopes = Column(String(500), nullable=True)
    account_id = Column(String(255), nullable=True)  # GitHub installation id or Slack team id
    account_name = Column(String(255), nullable=True)  # org name or team name

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
