"""Phase 113: Threat Actor DNA - behavioral genome."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class ActorDNA(Base):
    __tablename__ = "actor_dnas"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    actor_name = Column(String(300), nullable=False)  # APT29, Lazarus
    dna_hash = Column(String(200), nullable=False)
    behavior_genome_json = Column(JSON, default=dict)  # {initial_access: [T1078], persistence: [T1053]}
    sophistication_score = Column(Float, default=0.0)
    first_seen = Column(DateTime(timezone=True), nullable=True)
    last_seen = Column(DateTime(timezone=True), default=_now)
    created_at = Column(DateTime(timezone=True), default=_now)

class TTPPattern(Base):
    __tablename__ = "ttp_patterns"
    id = Column(Integer, primary_key=True, index=True)
    actor_dna_id = Column(Integer, ForeignKey("actor_dnas.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    ttp_id = Column(String(50), nullable=False)  # T1078, T1021
    frequency = Column(Float, default=0.0)
    sequence_position = Column(Integer, default=0)
    context_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)

class ActorAttribution(Base):
    __tablename__ = "actor_attributions"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    actor_dna_id = Column(Integer, ForeignKey("actor_dnas.id"), nullable=True)
    confidence = Column(Float, default=0.0)
    evidence_json = Column(JSON, default=dict)
    status = Column(String(20), default="suspected")
    created_at = Column(DateTime(timezone=True), default=_now)
