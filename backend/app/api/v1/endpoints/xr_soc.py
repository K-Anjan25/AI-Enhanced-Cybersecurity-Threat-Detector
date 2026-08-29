"""Phase 108: XR SOC endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import xr_soc_service

router = APIRouter(prefix="/xr-soc", tags=["XR SOC P108"])

class SessionIn(BaseModel):
    name: str
    xr_type: str = "vr"

@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        sessions = xr_soc_service.list_sessions(db, current_user.org_id)
        return [xr_soc_service.serialize_session(s) for s in sessions]
    except Exception:
        return []

@router.post("/sessions")
def create_session(payload: SessionIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        sess = xr_soc_service.create_session(db, current_user.org_id, current_user.id, payload.name, payload.xr_type)
        return xr_soc_service.serialize_session(sess)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/sessions/{session_id}/spawn")
def spawn_entities(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        entities = xr_soc_service.spawn_spatial_entities(db, current_user.org_id, session_id)
        return [{"id": e.id, "entity_type": e.entity_type, "position": e.position_json} for e in entities]
    except Exception as e:
        return {"status": "error", "detail": str(e)}
