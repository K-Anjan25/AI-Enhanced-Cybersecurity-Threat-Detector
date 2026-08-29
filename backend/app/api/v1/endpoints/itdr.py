"""Phase 64: ITDR endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import itdr_service

router = APIRouter(prefix="/itdr", tags=["itdr"])

class ImpossibleTravelIn(BaseModel):
    user_id: int
    new_ip: str
    new_location: str
    previous_location: str
    time_delta_seconds: int

@router.post("/baseline/{user_id}")
def build_baseline(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        profile = itdr_service.build_baseline(db, current_user.org_id, user_id)
        return itdr_service.serialize_profile(profile)
    except Exception as e:
        return {"status": "error", "detail": str(e), "ocsf": {"class_uid": 4001, "activity_id": 99}}

@router.post("/detect/impossible-travel")
def detect_impossible_travel(payload: ImpossibleTravelIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        threat = itdr_service.detect_impossible_travel(db, current_user.org_id, payload.user_id, payload.new_ip, payload.new_location, payload.previous_location, payload.time_delta_seconds)
        if threat:
            return itdr_service.serialize_threat(threat)
        return {"status": "ok", "message": "No impossible travel detected"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/threats")
def list_threats(status: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        threats = itdr_service.list_threats(db, current_user.org_id, status=status, limit=limit)
        return [itdr_service.serialize_threat(t) for t in threats]
    except Exception as e:
        return []

@router.get("/risky-signins")
def list_risky_signins(limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        items = itdr_service.list_risky_signins(db, current_user.org_id, limit=limit)
        return [{"id": r.id, "user_id": r.user_id, "risk_level": r.risk_level, "risk_reasons": r.risk_reasons, "ip": r.ip_address, "created_at": r.created_at.isoformat() if r.created_at else None} for r in items]
    except Exception as e:
        return []
