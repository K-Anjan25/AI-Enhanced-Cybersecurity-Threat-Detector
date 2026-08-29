from datetime import datetime,timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)
    org = relationship("Org", back_populates="users")
    username = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    profile_image = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_blocked = Column(Boolean, default=False)

    role = Column(String(50), default="user", nullable=False)
    clearance_level = Column(Integer, nullable=True)
    department = Column(String(100), nullable=True)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Phase 40: SSO/SCIM
    external_id = Column(String(255), nullable=True, index=True)  # IdP sub
    sso_provider = Column(String(50), nullable=True)  # e.g. oidc:google, oidc:azure
    is_sso_user = Column(Boolean, default=False, nullable=False)
    scim_external_id = Column(String(255), nullable=True, index=True)  # SCIM externalId

    alerts = relationship("SecurityAlert", back_populates="user")
    scanned_alerts = relationship("ScannedAlert", back_populates="user")
    scan_batches = relationship("ScanBatch", back_populates="user")