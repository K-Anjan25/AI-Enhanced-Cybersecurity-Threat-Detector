"""Phase 116: Neural Co-Pilot endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import neural_copilot_service

router = APIRouter(prefix="/neural-copilot", tags=["Neural Co-Pilot P116"])

class ProfileIn(BaseModel):
    profile_name: str

class SessionIn(BaseModel):
    session_name: str
    intent: str = "Investigate alert"

@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        profiles = neural_copilot_service.list_profiles(db, current_user.org_id, current_user.id)
        return [neural_copilot_service.serialize_profile(p) for p in profiles]
    except Exception:
        return []

@router.post("/profiles")
def create_profile(payload: ProfileIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        p = neural_copilot_service.create_profile(db, current_user.org_id, current_user.id, payload.profile_name)
        return neural_copilot_service.serialize_profile(p)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/sessions")
def create_session(payload: SessionIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        s = neural_copilot_service.create_session(db, current_user.org_id, current_user.id, payload.session_name, payload.intent)
        return neural_copilot_service.serialize_session(s)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        sessions = neural_copilot_service.list_sessions(db, current_user.org_id)
        return [neural_copilot_service.serialize_session(s) for s in sessions]
    except Exception:
        return []
