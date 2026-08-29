"""Phase 139: Existential Risk endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import existential_risk_service

router = APIRouter(prefix="/existential-risk", tags=["Existential Risk P139"])

class XRiskIn(BaseModel):
    risk_name: str
    risk_category: str = "ai"
    probability: float = 0.001

class ScenarioIn(BaseModel):
    scenario_name: str
    risk_ids: List[int] = []

@router.get("/risks")
def list_risks(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        risks = existential_risk_service.list_xrisks(db, current_user.org_id)
        return [existential_risk_service.serialize_xrisk(r) for r in risks]
    except Exception:
        return []

@router.post("/risks")
def create_risk(payload: XRiskIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        r = existential_risk_service.create_xrisk(db, current_user.org_id, payload.risk_name, payload.risk_category, payload.probability)
        return existential_risk_service.serialize_xrisk(r)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/scenarios")
def create_scenario(payload: ScenarioIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        s = existential_risk_service.create_scenario(db, current_user.org_id, payload.scenario_name, payload.risk_ids)
        return {"id": s.id, "scenario_name": s.scenario_name, "cascade_probability": s.cascade_probability, "simulation_result": s.simulation_result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
