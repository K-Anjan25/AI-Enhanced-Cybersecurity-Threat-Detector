"""Phase 126: Autonomous Workforce - AI workforce management."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class AIWorkforce(Base):
    __tablename__ = "ai_workforces"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    workforce_type = Column(String(50), default="soc")  # soc, engineering, compliance, all
    total_agents = Column(Integer, default=20)
    human_count = Column(Integer, default=5)
    ai_count = Column(Integer, default=15)
    autonomy_ratio = Column(Float, default=0.75)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class SkillMatrix(Base):
    __tablename__ = "skill_matrices"
    id = Column(Integer, primary_key=True, index=True)
    workforce_id = Column(Integer, ForeignKey("ai_workforces.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    skill_name = Column(String(200), nullable=False)  # threat_hunting, forensics, malware_analysis
    human_proficiency = Column(Float, default=0.0)
    ai_proficiency = Column(Float, default=0.0)
    gap = Column(Float, default=0.0)
    training_needed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)

class WorkforceTask(Base):
    __tablename__ = "workforce_tasks"
    id = Column(Integer, primary_key=True, index=True)
    workforce_id = Column(Integer, ForeignKey("ai_workforces.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    task_name = Column(String(500), nullable=False)
    assigned_to = Column(String(200), nullable=True)  # human or AI agent name
    assignment_type = Column(String(20), default="ai")  # ai, human, hybrid
    priority = Column(String(20), default="high")
    status = Column(String(20), default="assigned")
    created_at = Column(DateTime(timezone=True), default=_now)
