"""Phase 118: Autonomous Red Team v2 LLM-powered adversary."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class AdversaryAgent(Base):
    __tablename__ = "adversary_agents"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    adversary_type = Column(String(50), default="apt")  # apt, ransomware, insider, script_kiddie
    llm_model = Column(String(100), default="claude-3-5-sonnet")
    personality_json = Column(JSON, default=dict)  # {aggressiveness, stealth, sophistication}
    status = Column(String(20), default="idle")
    created_at = Column(DateTime(timezone=True), default=_now)

class AttackPlan(Base):
    __tablename__ = "attack_plans"
    id = Column(Integer, primary_key=True, index=True)
    adversary_id = Column(Integer, ForeignKey("adversary_agents.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    objective = Column(String(500), nullable=True)  # e.g., "Exfiltrate customer DB"
    kill_chain_json = Column(JSON, default=list)  # ordered TTPs
    estimated_success = Column(Float, default=0.0)
    status = Column(String(20), default="draft")  # draft, ready, executing, completed
    created_at = Column(DateTime(timezone=True), default=_now)

class AdversaryExecution(Base):
    __tablename__ = "adversary_executions"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("attack_plans.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    step_number = Column(Integer, default=1)
    ttp_id = Column(String(50), nullable=True)
    action_json = Column(JSON, default=dict)
    result_json = Column(JSON, default=dict)
    detected = Column(Boolean, default=False)
    detection_time_seconds = Column(Float, nullable=True)
    status = Column(String(20), default="completed")
    created_at = Column(DateTime(timezone=True), default=_now)
