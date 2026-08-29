"""Phase 111: Incident Commander service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.incident_commander import IncidentCommander, ICDecision, ICRunbook

def _now():
    return datetime.now(timezone.utc)

def create_commander(db: Session, org_id: int, name: str, incident_id: int = None) -> IncidentCommander:
    cmd = IncidentCommander(org_id=org_id, name=name, incident_id=incident_id, commander_type="ai", voice_enabled=True, voice_id="voice-00", status="active")
    db.add(cmd)
    db.commit()
    db.refresh(cmd)
    # Seed runbook
    rb = ICRunbook(commander_id=cmd.id, org_id=org_id, name=f"Runbook for {name}", steps_json=[{"step": 1, "action": "triage", "assignee": "hunter"}, {"step": 2, "action": "contain", "assignee": "responder"}, {"step": 3, "action": "communicate", "assignee": "ic"}], voice_commands_json=["triage incident", "isolate host", "notify stakeholders"], is_autonomous=True)
    db.add(rb)
    db.commit()
    return cmd

def list_commanders(db: Session, org_id: int) -> List[IncidentCommander]:
    return db.query(IncidentCommander).filter(IncidentCommander.org_id == org_id).order_by(IncidentCommander.created_at.desc()).all()

def make_decision(db: Session, org_id: int, commander_id: int, decision_type: str, title: str) -> ICDecision:
    cmd = db.query(IncidentCommander).filter(IncidentCommander.id == commander_id, IncidentCommander.org_id == org_id).first()
    if not cmd:
        raise ValueError("Commander not found")
    decision = ICDecision(commander_id=commander_id, org_id=org_id, decision_type=decision_type, title=title, reasoning_json={"chain_of_thought": f"Analyzing incident {cmd.incident_id}, deciding {decision_type}", "factors": ["severity HIGH", "asset crown jewel"]}, confidence=0.89, delegated_to="responder-agent", status="executed")
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision

def list_decisions(db: Session, org_id: int, commander_id: int = None) -> List[ICDecision]:
    q = db.query(ICDecision).filter(ICDecision.org_id == org_id)
    if commander_id:
        q = q.filter(ICDecision.commander_id == commander_id)
    return q.order_by(ICDecision.created_at.desc()).limit(20).all()

def serialize_commander(c: IncidentCommander) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "incident_id": c.incident_id, "commander_type": c.commander_type, "voice_enabled": c.voice_enabled, "voice_id": c.voice_id, "status": c.status}

def serialize_decision(d: ICDecision) -> Dict[str, Any]:
    return {"id": d.id, "commander_id": d.commander_id, "decision_type": d.decision_type, "title": d.title, "reasoning": d.reasoning_json, "confidence": d.confidence, "delegated_to": d.delegated_to, "status": d.status}
