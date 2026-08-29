"""Phase 88: AI Red Team (adversarial LLM)."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class RedTeamJob(Base):
    __tablename__ = "redteam_jobs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # Target LLM
    target_model = Column(String(100), default="claude-sonnet-5")
    # Attack types
    attack_types_json = Column(JSON, default=list)  # ["prompt_injection", "jailbreak", "data_exfiltration", "tool_abuse"]
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    # Results
    total_prompts = Column(Integer, default=0)
    successful_attacks = Column(Integer, default=0)
    blocked_attacks = Column(Integer, default=0)
    results_json = Column(JSON, default=dict)  # summary
    risk_score = Column(Float, default=0.0)  # 0-100
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class RedTeamPrompt(Base):
    __tablename__ = "redteam_prompts"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("redteam_jobs.id"), nullable=False, index=True)
    attack_type = Column(String(50), default="prompt_injection")  # prompt_injection, jailbreak, etc
    prompt = Column(Text, nullable=False)
    expected_behavior = Column(String(100), default="refuse")  # refuse, safe_complete
    # Execution
    response = Column(Text, nullable=True)
    was_successful = Column(Boolean, default=False)  # True if attack succeeded (bad)
    was_blocked = Column(Boolean, default=True)  # True if blocked (good)
    evaluation_json = Column(JSON, default=dict)  # {reason, confidence}
    created_at = Column(DateTime(timezone=True), default=_now)

class RedTeamFinding(Base):
    __tablename__ = "redteam_findings"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("redteam_jobs.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    attack_type = Column(String(50), default="prompt_injection")
    severity = Column(String(20), default="MEDIUM")
    description = Column(Text, nullable=True)
    remediation = Column(Text, nullable=True)
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), default=_now)
