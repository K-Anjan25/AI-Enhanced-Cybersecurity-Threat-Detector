"""Phase 128: Planetary Defense endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import planetary_defense_service

router = APIRouter(prefix="/planetary-defense", tags=["Planetary Defense P128"])

class GridIn(BaseModel):
    name: str

class ThreatIn(BaseModel):
    grid_id: int
    threat_name: str
    threat_type: str = "nation_state"

@router.get("/grids")
def list_grids(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        grids = planetary_defense_service.list_grids(db, current_user.org_id)
        return [planetary_defense_service.serialize_grid(g) for g in grids]
    except Exception:
        return []

@router.post("/grids")
def create_grid(payload: GridIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        g = planetary_defense_service.create_grid(db, current_user.org_id, payload.name)
        return planetary_defense_service.serialize_grid(g)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/threats")
def create_threat(payload: ThreatIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        t = planetary_defense_service.create_threat(db, current_user.org_id, payload.grid_id, payload.threat_name, payload.threat_type)
        return {"id": t.id, "threat_name": t.threat_name, "threat_type": t.threat_type, "impact_score": t.impact_score, "status": t.status}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
