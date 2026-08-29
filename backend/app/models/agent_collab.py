"""Phase 83: Agent-to-Agent collaboration."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class AgentCollaboration(Base):
    __tablename__ = "agent_collaborations"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    # Agents involved: e.g. ["hunter", "enricher", "responder", "compliance_checker"]
    agents_json = Column(JSON, default=list)
    status = Column(String(20), default="running")  # running, completed, failed
    # Collaboration result
    result_json = Column(JSON, default=dict)  # final consensus, votes
    consensus_score = Column(Float, default=0.0)  # 0-100 agreement
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class AgentMessage(Base):
    __tablename__ = "agent_messages"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    collaboration_id = Column(Integer, ForeignKey("agent_collaborations.id"), nullable=False, index=True)
    from_agent = Column(String(50), nullable=False)  # hunter, enricher, responder, etc
    to_agent = Column(String(50), nullable=True)  # null = broadcast
    message_type = Column(String(50), default="proposal")  # proposal, vote, tool_result, consensus
    content = Column(Text, nullable=False)
    tool_name = Column(String(50), nullable=True)
    tool_output_json = Column(JSON, nullable=True)
    confidence = Column(Float, default=0.8)
    created_at = Column(DateTime(timezone=True), default=_now)
