"""Phase 138: Infinite Learning endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import infinite_learning_service

router = APIRouter(prefix="/infinite-learning", tags=["Infinite Learning P138"])

class LearnerIn(BaseModel):
    name: str

class TaskIn(BaseModel):
    learner_id: int
    task_name: str = "Detect novel APT"

@router.get("/learners")
def list_learners(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        learners = infinite_learning_service.list_learners(db, current_user.org_id)
        return [infinite_learning_service.serialize_learner(l) for l in learners]
    except Exception:
        return []

@router.post("/learners")
def create_learner(payload: LearnerIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        l = infinite_learning_service.create_learner(db, current_user.org_id, payload.name)
        return infinite_learning_service.serialize_learner(l)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/tasks")
def learn_task(payload: TaskIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        t = infinite_learning_service.learn_task(db, current_user.org_id, payload.learner_id, payload.task_name)
        return {"id": t.id, "task_name": t.task_name, "accuracy_before": t.accuracy_before, "accuracy_after": t.accuracy_after, "status": t.status}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
