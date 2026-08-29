"""Phase 77: Risk-based alerting + asset criticality."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    asset_type = Column(String(50), default="host")  # host, user, service, cloud_resource
    ip_address = Column(String(50), nullable=True)
    hostname = Column(String(200), nullable=True)
    # Criticality: 1-5 (5 = most critical, e.g. domain controller, prod db)
    criticality = Column(Integer, default=3)
    business_unit = Column(String(100), nullable=True)
    owner = Column(String(200), nullable=True)
    tags = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)

class RiskBasedRule(Base):
    __tablename__ = "risk_based_rules"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # Rule: if alert severity HIGH and asset criticality 5, then escalate
    conditions_json = Column(JSON, default=dict)  # {min_severity: HIGH, min_criticality: 4, mitre_tactic: ...}
    action = Column(String(50), default="escalate")  # escalate, suppress, adjust_score
    risk_multiplier = Column(Float, default=1.5)  # multiply risk score
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class RiskScoreLog(Base):
    __tablename__ = "risk_score_logs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    alert_id = Column(Integer, ForeignKey("security_alerts.id"), nullable=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    base_score = Column(Float, default=0.0)
    adjusted_score = Column(Float, default=0.0)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
