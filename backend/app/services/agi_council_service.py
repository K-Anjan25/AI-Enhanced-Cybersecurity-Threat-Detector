"""Phase 122: AGI Council service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.agi_council import AGICouncil, AGIMember, CouncilDecision

def _now():
    return datetime.now(timezone.utc)

def create_council(db: Session, org_id: int, name: str) -> AGICouncil:
    council = AGICouncil(org_id=org_id, name=name, council_type="security", quorum_required=3, consensus_strategy="supermajority", status="active")
    db.add(council)
    db.commit()
    db.refresh(council)
    # Seed 5 AGI members
    members = [
        {"member_name": "Athena", "specialization": "threat_analysis", "model": "claude-3-5-sonnet", "voting_weight": 1.2},
        {"member_name": "Sentinel", "specialization": "defense", "model": "gpt-4o", "voting_weight": 1.0},
        {"member_name": "Oracle", "specialization": "prophecy", "model": "gemini-2.0", "voting_weight": 1.0},
        {"member_name": "Guardian", "specialization": "ethics", "model": "claude-3-5-sonnet", "voting_weight": 1.5},
        {"member_name": "Sage", "specialization": "strategy", "model": "claude-3-opus", "voting_weight": 1.3},
    ]
    for m in members:
        member = AGIMember(council_id=council.id, org_id=org_id, **m, alignment_score=98.5, status="active")
        db.add(member)
    db.commit()
    return council

def list_councils(db: Session, org_id: int) -> List[AGICouncil]:
    return db.query(AGICouncil).filter(AGICouncil.org_id == org_id).all()

def convene_council(db: Session, org_id: int, council_id: int, topic: str) -> CouncilDecision:
    council = db.query(AGICouncil).filter(AGICouncil.id == council_id, AGICouncil.org_id == org_id).first()
    if not council:
        raise ValueError("Council not found")
    members = db.query(AGIMember).filter(AGIMember.council_id == council_id).all()
    votes = []
    for mem in members:
        vote = "approve" if mem.member_name != "Guardian" or "ethical" not in topic.lower() else "abstain"
        votes.append({"member": mem.member_name, "vote": vote, "reasoning": f"{mem.specialization} analysis: {topic} is acceptable", "weight": mem.voting_weight})
    consensus = len([v for v in votes if v["vote"]=="approve"]) >= council.quorum_required
    decision = CouncilDecision(council_id=council_id, org_id=org_id, topic=topic, votes_json=votes, consensus_reached=consensus, final_decision=f"Council decided: {topic} - APPROVED with supermajority" if consensus else "No consensus", dissenting_opinions=[])
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision

def serialize_council(c: AGICouncil) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "council_type": c.council_type, "quorum_required": c.quorum_required, "consensus_strategy": c.consensus_strategy, "status": c.status}

def serialize_decision(d: CouncilDecision) -> Dict[str, Any]:
    return {"id": d.id, "council_id": d.council_id, "topic": d.topic, "votes": d.votes_json, "consensus_reached": d.consensus_reached, "final_decision": d.final_decision}
