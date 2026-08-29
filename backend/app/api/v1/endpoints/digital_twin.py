"""Phase 104: Digital Twin endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import digital_twin_service

router = APIRouter(prefix="/digital-twin", tags=["Digital Twin P104"])

class TwinIn(BaseModel):
    name: str
    twin_type: str = "infrastructure"

class SimIn(BaseModel):
    twin_id: int
    scenario: str = "ransomware"

@router.get("/twins")
def list_twins(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        twins = digital_twin_service.list_twins(db, current_user.org_id)
        return [digital_twin_service.serialize_twin(t) for t in twins]
    except Exception:
        return []

@router.post("/twins")
def create_twin(payload: TwinIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        t = digital_twin_service.create_twin(db, current_user.org_id, payload.name, payload.twin_type)
        return digital_twin_service.serialize_twin(t)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/simulate")
def simulate(payload: SimIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        sim = digital_twin_service.run_simulation(db, current_user.org_id, payload.twin_id, payload.scenario)
        return digital_twin_service.serialize_sim(sim)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        return {"status": "error", "detail": str(e)}
