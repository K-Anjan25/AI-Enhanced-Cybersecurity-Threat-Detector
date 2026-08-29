"""Phase 103: Autonomous Hunting Swarm."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class HuntSwarm(Base):
    __tablename__ = "hunt_swarms"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    objective = Column(String(500), nullable=True)  # e.g., "Find lateral movement"
    swarm_size = Column(Integer, default=5)
    coordination_strategy = Column(String(50), default="consensus")  # consensus, leader_follower, auction
    status = Column(String(20), default="idle")  # idle, hunting, completed
    created_at = Column(DateTime(timezone=True), default=_now)

class SwarmAgent(Base):
    __tablename__ = "swarm_agents"
    id = Column(Integer, primary_key=True, index=True)
    swarm_id = Column(Integer, ForeignKey("hunt_swarms.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False)
    agent_type = Column(String(50), default="hunter")  # hunter, enricher, correlator, validator
    assigned_hypothesis = Column(String(500), nullable=True)
    status = Column(String(20), default="idle")
    findings_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)

class SwarmFinding(Base):
    __tablename__ = "swarm_findings"
    id = Column(Integer, primary_key=True, index=True)
    swarm_id = Column(Integer, ForeignKey("hunt_swarms.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("swarm_agents.id"), nullable=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    severity = Column(String(20), default="MEDIUM")
    confidence = Column(Float, default=0.0)
    evidence_json = Column(JSON, default=dict)
    consensus_score = Column(Float, default=0.0)  # agreement among swarm
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), default=_now)
