"""Phase 144: Unified Consciousness endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import unified_consciousness_service

router = APIRouter(prefix="/unified-consciousness", tags=["Unified Consciousness P144"])

class In(BaseModel):
    name: str

class DecideIn(BaseModel):
    hive_id: int
    proposal: str = "Activate collective defense against omniverse threat"

@router.get("/hives")
def list_hives(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        hives = unified_consciousness_service.list_hives(db, current_user.org_id)
        return [unified_consciousness_service.serialize_hive(h) for h in hives]
    except Exception:
        return []

@router.post("/hives")
def create_hive(payload: In, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        h = unified_consciousness_service.create_hive(db, current_user.org_id, payload.name)
        return unified_consciousness_service.serialize_hive(h)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/decide")
def decide(payload: DecideIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        d = unified_consciousness_service.decide(db, current_user.org_id, payload.hive_id, payload.proposal)
        return {"id": d.id, "proposal": d.proposal_json, "votes_for": d.votes_for, "votes_against": d.votes_against, "consensus": d.consensus_reached, "final": d.final_decision}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
