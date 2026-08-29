"""Phase 131: Multiverse SOC - many-worlds threat modeling."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class Multiverse(Base):
    __tablename__ = "multiverses"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    branching_factor = Column(Integer, default=10)  # parallel worlds
    divergence_point = Column(String(500), nullable=True)
    coherence_score = Column(Float, default=92.0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class UniverseBranch(Base):
    __tablename__ = "universe_branches"
    id = Column(Integer, primary_key=True, index=True)
    multiverse_id = Column(Integer, ForeignKey("multiverses.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    branch_id = Column(String(100), nullable=False)  # universe-0, universe-1
    timeline_json = Column(JSON, default=dict)  # events in this branch
    threat_outcome = Column(String(50), default="contained")  # contained, breach, catastrophic
    probability = Column(Float, default=0.1)
    created_at = Column(DateTime(timezone=True), default=_now)

class CrossUniverseIntel(Base):
    __tablename__ = "cross_universe_intels"
    id = Column(Integer, primary_key=True, index=True)
    multiverse_id = Column(Integer, ForeignKey("multiverses.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    intel_type = Column(String(50), default="threat_pattern")
    shared_across_branches = Column(JSON, default=list)
    consensus_probability = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
