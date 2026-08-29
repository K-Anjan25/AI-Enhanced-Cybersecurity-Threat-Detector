"""Phase 116: Neural Co-Pilot service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.neural_copilot import NeuralProfile, CoPilotSession, CognitiveMetric

def _now():
    return datetime.now(timezone.utc)

def create_profile(db: Session, org_id: int, user_id: int, name: str) -> NeuralProfile:
    profile = NeuralProfile(user_id=user_id, org_id=org_id, profile_name=name, cognitive_preferences_json={"learning_style": "visual", "decision_style": "analytical"}, baseline_metrics_json={"cognitive_load_baseline": 45, "focus_baseline": 80}, bci_device="none", status="active")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile

def list_profiles(db: Session, org_id: int, user_id: int = None) -> List[NeuralProfile]:
    q = db.query(NeuralProfile).filter(NeuralProfile.org_id == org_id)
    if user_id:
        q = q.filter(NeuralProfile.user_id == user_id)
    return q.all()

def create_session(db: Session, org_id: int, user_id: int, name: str, intent: str = "Investigate alert") -> CoPilotSession:
    session = CoPilotSession(user_id=user_id, org_id=org_id, session_name=name, intent=intent, suggestions_json=[{"suggestion": "Check related alerts for same IP", "confidence": 0.85}, {"suggestion": "Enrich with VT", "confidence": 0.9}], accepted_suggestions=0, status="active")
    db.add(session)
    db.commit()
    db.refresh(session)
    # Cognitive metric
    metric = CognitiveMetric(session_id=session.id, org_id=org_id, metric_type="cognitive_load", value=62.5, context_json={"alerts_reviewed": 5})
    db.add(metric)
    db.commit()
    return session

def list_sessions(db: Session, org_id: int) -> List[CoPilotSession]:
    return db.query(CoPilotSession).filter(CoPilotSession.org_id == org_id).order_by(CoPilotSession.created_at.desc()).limit(20).all()

def serialize_profile(p: NeuralProfile) -> Dict[str, Any]:
    return {"id": p.id, "profile_name": p.profile_name, "cognitive_preferences": p.cognitive_preferences_json, "baseline_metrics": p.baseline_metrics_json, "bci_device": p.bci_device, "status": p.status}

def serialize_session(s: CoPilotSession) -> Dict[str, Any]:
    return {"id": s.id, "session_name": s.session_name, "intent": s.intent, "suggestions": s.suggestions_json, "accepted_suggestions": s.accepted_suggestions, "status": s.status}
