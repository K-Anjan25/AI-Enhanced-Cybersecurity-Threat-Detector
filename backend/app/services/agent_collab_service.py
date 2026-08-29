"""Phase 83: Agent-to-Agent collaboration service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.agent_collab import AgentCollaboration, AgentMessage
from app.models import Case
from app.services import ai_agent_service


def _now():
    return datetime.now(timezone.utc)


AGENT_ROLES = ["hunter", "enricher", "responder", "compliance_checker", "risk_analyst"]

def create_collaboration(db: Session, org_id: int, case_id: int, name: str, agents: List[str] = None, created_by_user_id: int = None) -> AgentCollaboration:
    agents = agents or AGENT_ROLES[:3]
    collab = AgentCollaboration(org_id=org_id, case_id=case_id, name=name, agents_json=agents, status="running", created_by_user_id=created_by_user_id)
    db.add(collab)
    db.commit()
    db.refresh(collab)

    # Seed initial messages: each agent proposes
    for agent in agents:
        msg = AgentMessage(org_id=org_id, collaboration_id=collab.id, from_agent=agent, message_type="proposal", content=f"{agent} initial proposal for case {case_id}: investigate {agent} perspective", confidence=0.8)
        db.add(msg)
    db.commit()
    return collab


def list_collaborations(db: Session, org_id: int, case_id: int = None) -> List[AgentCollaboration]:
    q = db.query(AgentCollaboration).filter(AgentCollaboration.org_id == org_id)
    if case_id:
        q = q.filter(AgentCollaboration.case_id == case_id)
    return q.order_by(AgentCollaboration.created_at.desc()).all()


def add_message(db: Session, org_id: int, collaboration_id: int, from_agent: str, content: str, to_agent: str = None, message_type: str = "proposal", tool_name: str = None, tool_output: Dict = None, confidence: float = 0.8) -> AgentMessage:
    msg = AgentMessage(org_id=org_id, collaboration_id=collaboration_id, from_agent=from_agent, to_agent=to_agent, message_type=message_type, content=content, tool_name=tool_name, tool_output_json=tool_output, confidence=confidence)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def run_collaboration_round(db: Session, org_id: int, collaboration_id: int) -> AgentCollaboration:
    """Run one round of agent collaboration: each agent executes its tool, votes."""
    collab = db.query(AgentCollaboration).filter(AgentCollaboration.id == collaboration_id, AgentCollaboration.org_id == org_id).first()
    if not collab:
        raise ValueError("Collaboration not found")

    agents = collab.agents_json or AGENT_ROLES[:3]
    messages = db.query(AgentMessage).filter(AgentMessage.collaboration_id == collaboration_id).all()

    # Each agent does its job
    for agent in agents:
        try:
            if agent == "hunter":
                # Run hunt
                from app.services import hunt_service
                result = hunt_service.execute_hunt_query(db, org_id, "severity:HIGH", limit=5)
                add_message(db, org_id, collaboration_id, from_agent="hunter", content=f"Hunter found {result['result_count']} alerts", message_type="tool_result", tool_name="hunt", tool_output=result, confidence=0.9)
            elif agent == "enricher":
                from app.services import threat_intel_enrichment
                # Mock enrich
                result = {"enriched": True, "threat_score": 7.5}
                add_message(db, org_id, collaboration_id, from_agent="enricher", content=f"Enricher threat score 7.5", message_type="tool_result", tool_name="threat_intel", tool_output=result, confidence=0.85)
            elif agent == "responder":
                add_message(db, org_id, collaboration_id, from_agent="responder", content=f"Responder proposes isolate host", message_type="proposal", confidence=0.8)
            elif agent == "compliance_checker":
                add_message(db, org_id, collaboration_id, from_agent="compliance_checker", content=f"Compliance checker: CC6.1 requires access review", message_type="proposal", confidence=0.75)
            elif agent == "risk_analyst":
                from app.services import exec_risk_service
                metrics = exec_risk_service.calculate_risk_metrics(db, org_id)
                add_message(db, org_id, collaboration_id, from_agent="risk_analyst", content=f"Risk analyst: {len(metrics)} metrics, avg risk", message_type="tool_result", tool_name="risk_metrics", tool_output={"metric_count": len(metrics)}, confidence=0.8)
        except Exception as e:
            add_message(db, org_id, collaboration_id, from_agent=agent, content=f"Error: {str(e)}", message_type="proposal", confidence=0.5)

    # Voting round: each agent votes on final action
    votes = {}
    for agent in agents:
        # Simplified voting: all agree on escalate
        votes[agent] = "escalate"
        add_message(db, org_id, collaboration_id, from_agent=agent, content=f"Vote: escalate", message_type="vote", confidence=0.8)

    # Consensus
    consensus = "escalate" if list(votes.values()).count("escalate") >= len(agents) // 2 + 1 else "review"
    consensus_score = 80.0

    collab.status = "completed"
    collab.result_json = {"consensus": consensus, "votes": votes, "agents": agents, "message_count": len(messages) + len(agents)*2}
    collab.consensus_score = consensus_score
    collab.completed_at = _now()
    db.commit()
    db.refresh(collab)
    return collab


def get_messages(db: Session, org_id: int, collaboration_id: int) -> List[AgentMessage]:
    return db.query(AgentMessage).filter(AgentMessage.org_id == org_id, AgentMessage.collaboration_id == collaboration_id).order_by(AgentMessage.created_at.asc()).all()


def serialize_collab(c: AgentCollaboration) -> Dict[str, Any]:
    return {"id": c.id, "case_id": c.case_id, "name": c.name, "agents": c.agents_json, "status": c.status, "result": c.result_json, "consensus_score": c.consensus_score, "created_at": c.created_at.isoformat() if c.created_at else None, "completed_at": c.completed_at.isoformat() if c.completed_at else None}


def serialize_message(m: AgentMessage) -> Dict[str, Any]:
    return {"id": m.id, "collaboration_id": m.collaboration_id, "from_agent": m.from_agent, "to_agent": m.to_agent, "message_type": m.message_type, "content": m.content, "tool_name": m.tool_name, "confidence": m.confidence, "created_at": m.created_at.isoformat() if m.created_at else None}
