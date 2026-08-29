"""Phase 122: AGI Council - council of AGIs voting consensus."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class AGICouncil(Base):
    __tablename__ = "agi_councils"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    council_type = Column(String(50), default="security")  # security, ethics, strategy
    quorum_required = Column(Integer, default=3)
    consensus_strategy = Column(String(50), default="supermajority")  # unanimous, majority, supermajority, weighted
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class AGIMember(Base):
    __tablename__ = "agi_members"
    id = Column(Integer, primary_key=True, index=True)
    council_id = Column(Integer, ForeignKey("agi_councils.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    member_name = Column(String(200), nullable=False)  # Athena, Sentinel, Oracle, Guardian, Sage
    specialization = Column(String(100), default="threat_analysis")
    model = Column(String(100), default="claude-3-5-sonnet")
    voting_weight = Column(Float, default=1.0)
    alignment_score = Column(Float, default=98.5)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class CouncilDecision(Base):
    __tablename__ = "council_decisions"
    id = Column(Integer, primary_key=True, index=True)
    council_id = Column(Integer, ForeignKey("agi_councils.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    topic = Column(String(500), nullable=False)
    votes_json = Column(JSON, default=list)  # [{member, vote, reasoning}]
    consensus_reached = Column(Boolean, default=False)
    final_decision = Column(Text, nullable=True)
    dissenting_opinions = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=_now)
