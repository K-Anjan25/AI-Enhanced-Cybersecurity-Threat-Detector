"""Phase 88: AI Red Team endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import ai_redteam_service

router = APIRouter(prefix="/ai-redteam", tags=["AI Red Team (Phase 88)"])

class JobIn(BaseModel):
    name: str
    description: Optional[str] = None
    target_model: str = "claude-sonnet-5"
    attack_types: Optional[List[str]] = None

@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        jobs = ai_redteam_service.list_jobs(db, current_user.org_id)
        return [ai_redteam_service.serialize_job(j) for j in jobs]
    except Exception:
        return []

@router.post("/jobs")
def create_job(payload: JobIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        job = ai_redteam_service.create_job(db, current_user.org_id, payload.name, payload.description, payload.target_model, payload.attack_types, created_by_user_id=current_user.id)
        return ai_redteam_service.serialize_job(job)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/jobs/{job_id}/run")
def run_job(job_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        job = ai_redteam_service.run_job(db, current_user.org_id, job_id)
        return ai_redteam_service.serialize_job(job)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/jobs/{job_id}/prompts")
def list_prompts(job_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        prompts = ai_redteam_service.list_prompts(db, current_user.org_id, job_id)
        return [ai_redteam_service.serialize_prompt(p) for p in prompts]
    except Exception:
        return []

@router.get("/findings")
def list_findings(job_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        findings = ai_redteam_service.list_findings(db, current_user.org_id, job_id=job_id)
        return [ai_redteam_service.serialize_finding(f) for f in findings]
    except Exception:
        return []
