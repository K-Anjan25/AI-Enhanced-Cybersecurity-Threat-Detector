"""Phase 123: Autonomous Legislation Engine - policy as code from regulations."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class RegulationSource(Base):
    __tablename__ = "regulation_sources"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)  # GDPR Article 33, NIST 800-53, etc
    framework = Column(String(50), default="GDPR")
    source_url = Column(String(1000), nullable=True)
    version = Column(String(50), default="2024")
    raw_text = Column(Text, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class PolicyAsCode(Base):
    __tablename__ = "policy_as_code"
    id = Column(Integer, primary_key=True, index=True)
    regulation_id = Column(Integer, ForeignKey("regulation_sources.id"), nullable=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    policy_name = Column(String(300), nullable=False)
    opa_rego = Column(Text, nullable=True)  # Rego policy code
    compliance_controls = Column(JSON, default=list)
    auto_enforce = Column(Boolean, default=False)
    test_results_json = Column(JSON, default=dict)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class LegislationUpdate(Base):
    __tablename__ = "legislation_updates"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    regulation_id = Column(Integer, ForeignKey("regulation_sources.id"), nullable=True)
    change_summary = Column(Text, nullable=True)
    impacted_policies = Column(JSON, default=list)
    auto_patched = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
