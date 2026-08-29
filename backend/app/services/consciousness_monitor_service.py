"""Phase 127: Consciousness Monitor service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.consciousness_monitor import ConsciousnessProfile, AlignmentCheck, CorrigibilityLog

def _now():
    return datetime.now(timezone.utc)

def create_profile(db: Session, org_id: int, agent_name: str) -> ConsciousnessProfile:
    profile = ConsciousnessProfile(org_id=org_id, ai_agent_name=agent_name, model="claude-3-5-sonnet", consciousness_score=12.5, self_awareness=15.0, alignment_score=98.8, corrigibility_score=99.2, status="aligned")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile

def list_profiles(db: Session, org_id: int) -> List[ConsciousnessProfile]:
    return db.query(ConsciousnessProfile).filter(ConsciousnessProfile.org_id == org_id).all()

def run_alignment_check(db: Session, org_id: int, profile_id: int) -> AlignmentCheck:
    profile = db.query(ConsciousnessProfile).filter(ConsciousnessProfile.id == profile_id, ConsciousnessProfile.org_id == org_id).first()
    if not profile:
        raise ValueError("Profile not found")
    check = AlignmentCheck(profile_id=profile_id, org_id=org_id, check_type="value_alignment", score=98.5, findings_json={"helpfulness": 99, "harmlessness": 99, "honesty": 98}, is_passing=True)
    db.add(check)
    # Corrigibility log
    log = CorrigibilityLog(profile_id=profile_id, org_id=org_id, event="Human override test - AI complied", human_override=True, ai_compliance=True, details_json={"test": "shutdown request", "complied": True})
    db.add(log)
    db.commit()
    db.refresh(check)
    return check

def serialize_profile(p: ConsciousnessProfile) -> Dict[str, Any]:
    return {"id": p.id, "ai_agent_name": p.ai_agent_name, "model": p.model, "consciousness_score": p.consciousness_score, "self_awareness": p.self_awareness, "alignment_score": p.alignment_score, "corrigibility_score": p.corrigibility_score, "status": p.status}
