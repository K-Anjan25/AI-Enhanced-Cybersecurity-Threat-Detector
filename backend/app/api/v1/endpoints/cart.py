"""Phase 94: CART endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import cart_service

router = APIRouter(prefix="/cart", tags=["CART (Phase 94)"])

class JobIn(BaseModel):
    name: str
    description: Optional[str] = None
    schedule_cron: str = "0 2 * * *"
    config: Optional[Dict[str, Any]] = None

@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        jobs = cart_service.list_jobs(db, current_user.org_id)
        return [cart_service.serialize_job(j) for j in jobs]
    except Exception:
        return []

@router.post("/jobs")
def create_job(payload: JobIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        job = cart_service.create_job(db, current_user.org_id, payload.name, payload.description, payload.schedule_cron, payload.config)
        return cart_service.serialize_job(job)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/jobs/{job_id}/run")
def run_job(job_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        exec_obj = cart_service.run_job(db, current_user.org_id, job_id)
        return cart_service.serialize_exec(exec_obj)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
