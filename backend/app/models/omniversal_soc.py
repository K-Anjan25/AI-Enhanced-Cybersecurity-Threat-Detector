"""Phase 141: Omniversal SOC - beyond multiverse, infinite multiverses."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class Omniverse(Base):
    __tablename__ = "omniverses"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    total_multiverses = Column(Integer, default=1000)  # infinite multiverses
    branching_factor = Column(Integer, default=100)  # 100x multiverse
    coherence_score = Column(Float, default=99.9)  # omniverse coherence
    divergence_point = Column(String(200), default="big_bang")
    status = Column(String(20), default="observing")
    created_at = Column(DateTime(timezone=True), default=_now)

class OmniverseBranch(Base):
    __tablename__ = "omniverse_branches"
    id = Column(Integer, primary_key=True, index=True)
    omniverse_id = Column(Integer, ForeignKey("omniverses.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    multiverse_signature = Column(String(100), nullable=False)  # signature of child multiverse
    threat_outcome = Column(String(50), default="contained")  # contained, breach, catastrophic, omniverse_collapse, vacuum_decay
    probability = Column(Float, default=0.01)
    divergence_score = Column(Float, default=0.05)
    timeline_json = Column(JSON, default=dict)  # timeline of this multiverse
    created_at = Column(DateTime(timezone=True), default=_now)

class CrossOmniverseIntel(Base):
    __tablename__ = "cross_omniverse_intel"
    id = Column(Integer, primary_key=True, index=True)
    omniverse_id = Column(Integer, ForeignKey("omniverses.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    intel_type = Column(String(100), default="omniverse_threat")
    source_multiverse = Column(String(100), nullable=True)
    target_multiverse = Column(String(100), nullable=True)
    intel_json = Column(JSON, default=dict)
    confidence = Column(Float, default=0.99)
    created_at = Column(DateTime(timezone=True), default=_now)
