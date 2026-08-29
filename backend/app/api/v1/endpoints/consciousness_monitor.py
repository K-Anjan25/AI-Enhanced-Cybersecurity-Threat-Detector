"""Phase 127: Consciousness Monitor endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import consciousness_monitor_service

router = APIRouter(prefix="/consciousness-monitor", tags=["Consciousness Monitor P127"])

class ProfileIn(BaseModel):
    ai_agent_name: str

@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        profiles = consciousness_monitor_service.list_profiles(db, current_user.org_id)
        return [consciousness_monitor_service.serialize_profile(p) for p in profiles]
    except Exception:
        return []

@router.post("/profiles")
def create_profile(payload: ProfileIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        p = consciousness_monitor_service.create_profile(db, current_user.org_id, payload.ai_agent_name)
        return consciousness_monitor_service.serialize_profile(p)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/profiles/{profile_id}/alignment-check")
def alignment_check(profile_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        check = consciousness_monitor_service.run_alignment_check(db, current_user.org_id, profile_id)
        return {"id": check.id, "check_type": check.check_type, "score": check.score, "is_passing": check.is_passing, "findings": check.findings_json}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
