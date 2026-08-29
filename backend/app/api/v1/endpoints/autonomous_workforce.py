"""Phase 126: Autonomous Workforce endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import autonomous_workforce_service

router = APIRouter(prefix="/autonomous-workforce", tags=["Autonomous Workforce P126"])

class WfIn(BaseModel):
    name: str

class TaskIn(BaseModel):
    workforce_id: int
    task_name: str
    assigned_to: str = "hunter-agent"

@router.get("/workforces")
def list_wf(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        wfs = autonomous_workforce_service.list_workforces(db, current_user.org_id)
        return [autonomous_workforce_service.serialize_workforce(w) for w in wfs]
    except Exception:
        return []

@router.post("/workforces")
def create_wf(payload: WfIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        w = autonomous_workforce_service.create_workforce(db, current_user.org_id, payload.name)
        return autonomous_workforce_service.serialize_workforce(w)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/tasks")
def assign_task(payload: TaskIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        t = autonomous_workforce_service.assign_task(db, current_user.org_id, payload.workforce_id, payload.task_name, payload.assigned_to)
        return {"id": t.id, "task_name": t.task_name, "assigned_to": t.assigned_to, "status": t.status}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
