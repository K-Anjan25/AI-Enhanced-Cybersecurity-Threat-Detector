"""Phase 91: Federated Threat Intel Sharing."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class IntelSharePackage(Base):
    __tablename__ = "intel_share_packages"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    # STIX bundle + privacy
    stix_bundle_json = Column(JSON, default=dict)
    # Privacy: anonymized, DP, TLP
    tlp = Column(String(20), default="AMBER")  # WHITE, GREEN, AMBER, RED
    is_anonymized = Column(Boolean, default=True)
    recipient_orgs = Column(JSON, default=list)  # org_ids or "all"
    status = Column(String(20), default="shared")  # draft, shared, revoked
    created_at = Column(DateTime(timezone=True), default=_now)

class IntelShareConsent(Base):
    __tablename__ = "intel_share_consents"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    share_package_id = Column(Integer, ForeignKey("intel_share_packages.id"), nullable=False)
    consent_type = Column(String(50), default="allow")  # allow, deny, allow_anonymized
    created_at = Column(DateTime(timezone=True), default=_now)
