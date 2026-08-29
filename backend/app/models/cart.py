"""Phase 94: Continuous Automated Red Teaming (CART)."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class CART_Job(Base):
    __tablename__ = "cart_jobs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # Schedule: cron
    schedule_cron = Column(String(100), default="0 2 * * *")  # daily 2am
    is_scheduled = Column(Boolean, default=True)
    # Config: techniques, assets in scope
    config_json = Column(JSON, default=dict)  # {techniques: [T1059, T1078], assets: [1,2], intensity: low}
    status = Column(String(20), default="scheduled")  # scheduled, running, completed
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class CART_Execution(Base):
    __tablename__ = "cart_executions"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("cart_jobs.id"), nullable=False)
    status = Column(String(20), default="running")  # running, completed, failed
    # Results
    total_steps = Column(Integer, default=0)
    detected_steps = Column(Integer, default=0)
    detection_rate = Column(Float, default=0.0)  # 0-100
    results_json = Column(JSON, default=dict)  # {steps: [{technique, detected, time_to_detect}]}
    started_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class CART_Finding(Base):
    __tablename__ = "cart_findings"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    execution_id = Column(Integer, ForeignKey("cart_executions.id"), nullable=False)
    title = Column(String(500), nullable=False)
    technique_id = Column(String(20), nullable=True)
    severity = Column(String(20), default="MEDIUM")
    description = Column(Text, nullable=True)
    is_detection_gap = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)
