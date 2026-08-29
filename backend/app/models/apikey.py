"""Phase 47: API keys + service accounts.

- ApiKey: org-scoped bearer token for machine-to-machine, hashed secret, prefix for lookup.
- ServiceAccount: modeled as User with is_service_account=True (added column) OR dedicated model.
  We use both: ServiceAccount model links to User row for authz.

Design:
- key format: `sk_{prefix}_{secret}` where prefix 8 chars identifies key, secret 32 chars random.
- Stored: prefix, hashed_secret (bcrypt), last 4 chars for display.
- Scopes: comma-separated list e.g. "alerts:read,alerts:write,ingest:write"
- Rate limiting: per-org token bucket, Redis optional, in-memory fallback.

"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class ServiceAccount(Base):
    """Phase 47: machine identity, distinct from human user.

    Linked to a User row for ABAC (role/permissions). The User has is_service_account=True.
    ServiceAccount holds metadata like description, owner.
    """

    __tablename__ = "service_accounts"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)
    org = relationship("Org", backref="service_accounts")

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    user = relationship("User", backref="service_account", foreign_keys=[user_id])

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by = relationship("User", backref="created_service_accounts", foreign_keys=[created_by_user_id])

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)
    org = relationship("Org", backref="api_keys")

    name = Column(String(255), nullable=False)
    prefix = Column(String(16), nullable=False, unique=True, index=True)  # 8 char prefix, unique for lookup
    hashed_secret = Column(String(255), nullable=False)  # bcrypt hash of secret part
    last4 = Column(String(4), nullable=False)  # last 4 chars for UI display

    # who created it
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by = relationship("User", backref="api_keys", foreign_keys=[created_by_user_id])

    # scopes e.g. "alerts:read,alerts:write,ingest:write"
    scopes = Column(String(1000), nullable=True, default="alerts:read")

    # service account linkage
    service_account_id = Column(Integer, ForeignKey("service_accounts.id", ondelete="SET NULL"), nullable=True)
    service_account = relationship("ServiceAccount", backref="api_keys", foreign_keys=[service_account_id])

    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_at = Column(DateTime, nullable=True)
