"""Phase 118: Adversary LLM endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import adversary_llm_service

router = APIRouter(prefix="/adversary-llm", tags=["Adversary LLM P118"])

class AdvIn(BaseModel):
    name: str
    adversary_type: str = "apt"

class PlanIn(BaseModel):
    adversary_id: int
    name: str
    objective: str = "Exfiltrate customer DB"

@router.get("/adversaries")
def list_adv(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        advs = adversary_llm_service.list_adversaries(db, current_user.org_id)
        return [adversary_llm_service.serialize_adversary(a) for a in advs]
    except Exception:
        return []

@router.post("/adversaries")
def create_adv(payload: AdvIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        a = adversary_llm_service.create_adversary(db, current_user.org_id, payload.name, payload.adversary_type)
        return adversary_llm_service.serialize_adversary(a)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/plans")
def create_plan(payload: PlanIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        p = adversary_llm_service.create_attack_plan(db, current_user.org_id, payload.adversary_id, payload.name, payload.objective)
        return adversary_llm_service.serialize_plan(p)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.post("/plans/{plan_id}/execute")
def exec_plan(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        execs = adversary_llm_service.execute_plan(db, current_user.org_id, plan_id)
        return [{"step": e.step_number, "ttp": e.ttp_id, "detected": e.detected, "detection_time": e.detection_time_seconds} for e in execs]
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
