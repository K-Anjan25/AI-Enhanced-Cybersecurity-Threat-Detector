"""Phase 135: Self-Replicating Defense endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import self_replicating_service

router = APIRouter(prefix="/self-replicating", tags=["Self-Replicating P135"])

class FleetIn(BaseModel):
    fleet_name: str
    replicator_type: str = "defense_probe"

@router.get("/fleets")
def list_fleets(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        fleets = self_replicating_service.list_fleets(db, current_user.org_id)
        return [self_replicating_service.serialize_fleet(f) for f in fleets]
    except Exception:
        return []

@router.post("/fleets")
def create_fleet(payload: FleetIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        f = self_replicating_service.create_fleet(db, current_user.org_id, payload.fleet_name, payload.replicator_type)
        return self_replicating_service.serialize_fleet(f)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/fleets/{fleet_id}/replicate")
def replicate(fleet_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        f = self_replicating_service.replicate(db, current_user.org_id, fleet_id)
        return self_replicating_service.serialize_fleet(f)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
