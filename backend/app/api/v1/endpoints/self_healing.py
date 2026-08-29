"""Phase 110: Self-Healing endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import self_healing_service

router = APIRouter(prefix="/self-healing", tags=["Self-Healing P110"])

class PolicyIn(BaseModel):
    name: str
    trigger_type: str = "alert"

class ExecIn(BaseModel):
    policy_id: int
    triggered_by: str = "alert-123"

@router.get("/policies")
def list_policies(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        policies = self_healing_service.list_policies(db, current_user.org_id)
        return [self_healing_service.serialize_policy(p) for p in policies]
    except Exception:
        return []

@router.post("/policies")
def create_policy(payload: PolicyIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        pol = self_healing_service.create_policy(db, current_user.org_id, payload.name, payload.trigger_type)
        return self_healing_service.serialize_policy(pol)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/execute")
def execute(payload: ExecIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        exec_obj = self_healing_service.execute_healing(db, current_user.org_id, payload.policy_id, payload.triggered_by)
        return self_healing_service.serialize_execution(exec_obj)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.get("/executions")
def list_execs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        execs = self_healing_service.list_executions(db, current_user.org_id)
        return [self_healing_service.serialize_execution(e) for e in execs]
    except Exception:
        return []
