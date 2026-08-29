"""SSO provider + SCIM token models — enterprise auth.

Phase 40: small teams grow into enterprise, they need SSO (OIDC) and SCIM
provisioning. Honest scope:

- SSO: OIDC Authorization Code flow with JIT provisioning. Configured per-org
  or globally via env vars. No SAML yet — documented as gap.
- SCIM: token-based provisioning per org. Implements Users CRUD + ServiceProviderConfig,
  ResourceTypes, Schemas. Groups is minimal (list only). Auth is Bearer token
  hashed at rest.
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
)

from app.core.database import Base


class SsoProvider(Base):
    __tablename__ = "sso_providers"
    __table_args__ = (
        UniqueConstraint("org_id", "provider_type", name="uq_sso_org_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)
    provider_type = Column(String(20), nullable=False, default="oidc")  # oidc | saml (saml not implemented)
    display_name = Column(String(120), nullable=False, default="Corporate SSO")

    # OIDC
    issuer = Column(Text, nullable=True)  # e.g. https://accounts.google.com or https://login.microsoftonline.com/tenant/v2.0
    client_id = Column(String(255), nullable=True)
    client_secret_encrypted = Column(Text, nullable=True)  # encrypted at rest
    scopes = Column(String(500), nullable=True, default="openid email profile")

    # SAML placeholder (not implemented, but schema exists)
    saml_metadata_url = Column(Text, nullable=True)

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
