"""Phase 100: NOCTRA OS - Autonomous SOC Operating System."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class NOCTRA_OS_Config(Base):
    __tablename__ = "noctra_os_configs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    # OS config: autonomous levels
    autonomy_level = Column(String(20), default="supervised")  # manual, supervised, autonomous, fully_autonomous
    # Modules enabled
    modules_json = Column(JSON, default=list)  # list of enabled modules P49-100
    # Policies: what AI can do autonomously
    policies_json = Column(JSON, default=dict)  # {auto_triage: true, auto_contain: false, auto_remediate: false}
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class NOCTRA_OS_Metric(Base):
    __tablename__ = "noctra_os_metrics"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    # OS-level metrics
    metric_name = Column(String(100), nullable=False)  # autonomy_score, cases_auto_resolved, analyst_hours_saved, etc
    metric_value = Column(Float, nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=_now)

class NOCTRA_OS_Log(Base):
    __tablename__ = "noctra_os_logs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    log_type = Column(String(50), default="decision")  # decision, action, learning, error
    # What happened
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    # Decision trace
    decision_json = Column(JSON, default=dict)  # {input, reasoning, action, confidence}
    created_at = Column(DateTime(timezone=True), default=_now)
