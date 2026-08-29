"""Phase 85: Approval Workflows endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import approval_workflow_service

router = APIRouter(prefix="/approval-workflows", tags=["Approval Workflows (Phase 85)"])

class WorkflowIn(BaseModel):
    name: str
    description: Optional[str] = None
    steps: List[Dict[str, Any]]
    trigger: Optional[Dict[str, Any]] = None

class RequestIn(BaseModel):
    workflow_id: int
    action_type: str
    target: str
    soar_action_id: Optional[int] = None
    case_id: Optional[int] = None

class DecisionIn(BaseModel):
    decision: str = "approved"  # approved, rejected
    comment: Optional[str] = None

@router.get("/")
def list_workflows(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        approval_workflow_service.seed_workflows(db, current_user.org_id)
        wfs = approval_workflow_service.list_workflows(db, current_user.org_id)
        return [approval_workflow_service.serialize_workflow(w) for w in wfs]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/")
def create_workflow(payload: WorkflowIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        wf = approval_workflow_service.create_workflow(db, current_user.org_id, payload.name, payload.description, payload.steps, payload.trigger, created_by_user_id=current_user.id)
        return approval_workflow_service.serialize_workflow(wf)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/instances")
def list_instances(status: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        insts = approval_workflow_service.list_instances(db, current_user.org_id, status=status)
        return [approval_workflow_service.serialize_instance(i) for i in insts]
    except Exception:
        return []

@router.post("/request")
def request_approval(payload: RequestIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        inst = approval_workflow_service.request_approval(db, current_user.org_id, payload.workflow_id, payload.action_type, payload.target, payload.soar_action_id, payload.case_id, requested_by_user_id=current_user.id)
        return approval_workflow_service.serialize_instance(inst)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/instances/{instance_id}/decide")
def decide(payload: DecisionIn, instance_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        inst = approval_workflow_service.approve_instance(db, current_user.org_id, instance_id, current_user.id, payload.decision, payload.comment)
        return approval_workflow_service.serialize_instance(inst)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
