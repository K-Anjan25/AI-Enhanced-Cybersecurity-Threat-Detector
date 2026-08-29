"""Phase 110: Self-Healing Infrastructure."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class SelfHealingPolicy(Base):
    __tablename__ = "self_healing_policies"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    trigger_type = Column(String(50), default="alert")  # alert, anomaly, compliance_violation, manual
    trigger_config_json = Column(JSON, default=dict)  # conditions
    healing_actions_json = Column(JSON, default=list)  # list of actions
    rollback_plan_json = Column(JSON, default=dict)
    requires_approval = Column(Boolean, default=False)
    autonomy_level = Column(String(20), default="supervised")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class HealingExecution(Base):
    __tablename__ = "healing_executions"
    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(Integer, ForeignKey("self_healing_policies.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    triggered_by = Column(String(200), nullable=True)
    execution_steps_json = Column(JSON, default=list)
    status = Column(String(20), default="running")  # running, succeeded, failed, rolled_back
    result_json = Column(JSON, default=dict)
    duration_seconds = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)

class HealingVerification(Base):
    __tablename__ = "healing_verifications"
    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey("healing_executions.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    verification_type = Column(String(50), default="health_check")  # health_check, compliance, security_scan
    passed = Column(Boolean, default=False)
    details_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
