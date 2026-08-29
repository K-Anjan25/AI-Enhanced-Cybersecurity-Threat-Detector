"""Phase 90: Compliance Autopilot endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import compliance_autopilot_service

router = APIRouter(prefix="/compliance-autopilot", tags=["Compliance Autopilot (Phase 90)"])

class RuleIn(BaseModel):
    name: str
    control_id: str
    benchmark: str = "CIS"
    severity: str = "HIGH"
    remediation: Dict[str, Any]
    dry_run: bool = True
    require_approval: bool = True

@router.get("/rules")
def list_rules(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        compliance_autopilot_service.seed_rules(db, current_user.org_id)
        rules = compliance_autopilot_service.list_rules(db, current_user.org_id)
        return [compliance_autopilot_service.serialize_rule(r) for r in rules]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/rules")
def create_rule(payload: RuleIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        rule = compliance_autopilot_service.create_rule(db, current_user.org_id, payload.name, payload.control_id, payload.benchmark, payload.severity, payload.remediation, payload.dry_run, payload.require_approval, created_by_user_id=current_user.id)
        return compliance_autopilot_service.serialize_rule(rule)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/evaluate")
def evaluate(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        execs = compliance_autopilot_service.evaluate_violations(db, current_user.org_id)
        return [compliance_autopilot_service.serialize_execution(e) for e in execs]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/executions")
def list_executions(status: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        execs = compliance_autopilot_service.list_executions(db, current_user.org_id, status=status)
        return [compliance_autopilot_service.serialize_execution(e) for e in execs]
    except Exception:
        return []

@router.post("/executions/{execution_id}/execute")
def execute(execution_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        exec_obj = compliance_autopilot_service.execute_autopilot(db, current_user.org_id, execution_id, executed_by=current_user.username)
        return compliance_autopilot_service.serialize_execution(exec_obj)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/summary")
def summary(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        return compliance_autopilot_service.get_summary(db, current_user.org_id)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
