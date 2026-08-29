"""Phase 148: Cosmic Threat endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import cosmic_threat_service

router = APIRouter(prefix="/cosmic-threat", tags=["Cosmic Threat P148"])

class In(BaseModel):
    name: str
    threat_type: str = "vacuum_decay"
    probability: float = 0.0001

class SimIn(BaseModel):
    simulation_name: str
    threat_ids: List[int] = []

@router.get("/threats")
def list_threats(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        threats = cosmic_threat_service.list_threats(db, current_user.org_id)
        return [cosmic_threat_service.serialize_threat(t) for t in threats]
    except Exception:
        return []

@router.post("/threats")
def create_threat(payload: In, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        t = cosmic_threat_service.create_threat(db, current_user.org_id, payload.name, payload.threat_type, payload.probability)
        return cosmic_threat_service.serialize_threat(t)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/simulations")
def create_sim(payload: SimIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        s = cosmic_threat_service.create_simulation(db, current_user.org_id, payload.simulation_name, payload.threat_ids)
        return {"id": s.id, "simulation_name": s.simulation_name, "survival_probability": s.survival_probability, "result": s.simulation_result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
