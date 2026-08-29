"""Phase 144: Unified Consciousness Network - hive mind collective defense."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class HiveMind(Base):
    __tablename__ = "hive_minds"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    connected_consciousness_count = Column(Integer, default=1000000)  # 1M minds
    coherence = Column(Float, default=95.5)
    collective_intelligence_score = Column(Float, default=180.0)  # IQ beyond human
    consensus_threshold = Column(Float, default=0.66)
    status = Column(String(20), default="unified")
    created_at = Column(DateTime(timezone=True), default=_now)

class ConsciousnessNode(Base):
    __tablename__ = "consciousness_nodes"
    id = Column(Integer, primary_key=True, index=True)
    hive_id = Column(Integer, ForeignKey("hive_minds.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    node_type = Column(String(50), default="human")  # human, ai, hybrid, alien, posthuman
    consciousness_level = Column(Float, default=75.0)
    contribution_score = Column(Float, default=85.0)
    status = Column(String(20), default="connected")
    created_at = Column(DateTime(timezone=True), default=_now)

class HiveDecision(Base):
    __tablename__ = "hive_decisions"
    id = Column(Integer, primary_key=True, index=True)
    hive_id = Column(Integer, ForeignKey("hive_minds.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    decision_type = Column(String(100), default="threat_response")
    proposal_json = Column(JSON, default=dict)
    votes_for = Column(Integer, default=0)
    votes_against = Column(Integer, default=0)
    consensus_reached = Column(Boolean, default=False)
    final_decision = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
