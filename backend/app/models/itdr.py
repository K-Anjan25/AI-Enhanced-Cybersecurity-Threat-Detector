"""Phase 64: ITDR/UEBA."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class UserBehaviorProfile(Base):
    __tablename__ = "user_behavior_profiles"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Baseline: {"avg_logins_per_day": 5, "usual_hours": [9,17], "usual_ips": ["10.0.0.1"], "usual_locations": ["US"], "devices": ["chrome"]}
    baseline_json = Column(JSON, default=dict)
    login_count = Column(Integer, default=0)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    risk_score = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

class IdentityThreat(Base):
    __tablename__ = "identity_threats"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    threat_type = Column(String(50), nullable=False)  # impossible_travel, brute_force, privilege_escalation, anomalous_login, credential_stuffing
    severity = Column(String(20), default="MEDIUM")
    description = Column(Text, nullable=True)
    evidence_json = Column(JSON, default=dict)
    # e.g. {"src_ip": "1.2.3.4", "dst_ip": "5.6.7.8", "location": "RU", "previous_location": "US", "time_delta_seconds": 3600}
    status = Column(String(20), default="open")  # open, investigating, resolved, false_positive
    related_alert_id = Column(Integer, ForeignKey("security_alerts.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class RiskySignIn(Base):
    __tablename__ = "risky_signins"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    ip_address = Column(String(50), nullable=True)
    location = Column(String(100), nullable=True)
    device = Column(String(200), nullable=True)
    risk_level = Column(String(20), default="MEDIUM")
    risk_reasons = Column(JSON, default=list)  # ["unfamiliar_location", "new_device", "impossible_travel"]
    is_risky = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)
