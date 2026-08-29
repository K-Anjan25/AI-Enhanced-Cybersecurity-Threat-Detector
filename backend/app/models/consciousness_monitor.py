"""Phase 127: Consciousness Monitor - AI alignment, corrigibility."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class ConsciousnessProfile(Base):
    __tablename__ = "consciousness_profiles"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    ai_agent_name = Column(String(300), nullable=False)  # which AI being monitored
    model = Column(String(100), default="claude-3-5-sonnet")
    consciousness_score = Column(Float, default=0.0)  # 0-100, philosophical metric
    self_awareness = Column(Float, default=0.0)
    alignment_score = Column(Float, default=98.5)
    corrigibility_score = Column(Float, default=99.0)
    status = Column(String(20), default="aligned")
    created_at = Column(DateTime(timezone=True), default=_now)

class AlignmentCheck(Base):
    __tablename__ = "alignment_checks"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("consciousness_profiles.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    check_type = Column(String(50), default="value_alignment")  # value_alignment, goal_alignment, corrigibility
    score = Column(Float, default=0.0)
    findings_json = Column(JSON, default=dict)
    is_passing = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class CorrigibilityLog(Base):
    __tablename__ = "corrigibility_logs"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("consciousness_profiles.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    event = Column(String(500), nullable=False)
    human_override = Column(Boolean, default=False)
    ai_compliance = Column(Boolean, default=True)
    details_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
