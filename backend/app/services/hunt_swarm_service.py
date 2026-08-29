"""Phase 103: Hunt Swarm service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.hunt_swarm import HuntSwarm, SwarmAgent, SwarmFinding

def _now():
    return datetime.now(timezone.utc)

def create_swarm(db: Session, org_id: int, name: str, objective: str, size: int = 5) -> HuntSwarm:
    swarm = HuntSwarm(org_id=org_id, name=name, objective=objective, swarm_size=size, coordination_strategy="consensus", status="idle")
    db.add(swarm)
    db.commit()
    db.refresh(swarm)
    # Create agents
    types = ["hunter","enricher","correlator","validator","hunter"]
    for i in range(size):
        agent = SwarmAgent(swarm_id=swarm.id, org_id=org_id, agent_name=f"Agent-{i+1}-{types[i%len(types)]}", agent_type=types[i%len(types)], assigned_hypothesis=f"Hypothesis {i+1}: {objective}", status="idle")
        db.add(agent)
    db.commit()
    return swarm

def list_swarms(db: Session, org_id: int) -> List[HuntSwarm]:
    return db.query(HuntSwarm).filter(HuntSwarm.org_id == org_id).order_by(HuntSwarm.created_at.desc()).all()

def launch_swarm(db: Session, org_id: int, swarm_id: int) -> HuntSwarm:
    swarm = db.query(HuntSwarm).filter(HuntSwarm.id == swarm_id, HuntSwarm.org_id == org_id).first()
    if not swarm:
        raise ValueError("Swarm not found")
    swarm.status = "hunting"
    db.commit()
    # Mock findings from agents
    agents = db.query(SwarmAgent).filter(SwarmAgent.swarm_id == swarm_id).all()
    for agent in agents[:3]:
        agent.status = "hunting"
        finding = SwarmFinding(swarm_id=swarm_id, agent_id=agent.id, org_id=org_id, title=f"{agent.agent_type} found lateral movement pattern", severity="HIGH", confidence=0.82, evidence_json={"hypothesis": agent.assigned_hypothesis, "logs": ["event1","event2"]}, consensus_score=0.75, status="open")
        db.add(finding)
        agent.findings_count += 1
    swarm.status = "completed"
    db.commit()
    db.refresh(swarm)
    return swarm

def list_findings(db: Session, org_id: int, swarm_id: int = None) -> List[SwarmFinding]:
    q = db.query(SwarmFinding).filter(SwarmFinding.org_id == org_id)
    if swarm_id:
        q = q.filter(SwarmFinding.swarm_id == swarm_id)
    return q.order_by(SwarmFinding.created_at.desc()).limit(50).all()

def serialize_swarm(s: HuntSwarm) -> Dict[str, Any]:
    return {"id": s.id, "name": s.name, "objective": s.objective, "swarm_size": s.swarm_size, "coordination_strategy": s.coordination_strategy, "status": s.status}

def serialize_finding(f: SwarmFinding) -> Dict[str, Any]:
    return {"id": f.id, "swarm_id": f.swarm_id, "agent_id": f.agent_id, "title": f.title, "severity": f.severity, "confidence": f.confidence, "evidence": f.evidence_json, "consensus_score": f.consensus_score, "status": f.status}
