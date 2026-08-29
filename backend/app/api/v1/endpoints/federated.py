"""Phase 89: Federated Learning endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import federated_service

router = APIRouter(prefix="/federated", tags=["Federated Learning (Phase 89)"])

class JobIn(BaseModel):
    name: str
    description: Optional[str] = None
    model_type: str = "threat_detection"
    base_model: str = "noctra-ml-v1"
    config: Optional[Dict[str, Any]] = None
    total_rounds: int = 5

class UpdateIn(BaseModel):
    round_id: int
    org_id: int
    update: Dict[str, Any]
    metrics: Dict[str, Any]

@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        jobs = federated_service.list_jobs(db)
        return [federated_service.serialize_job(j) for j in jobs]
    except Exception:
        return []

@router.post("/jobs")
def create_job(payload: JobIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        job = federated_service.create_job(db, payload.name, payload.description, payload.model_type, payload.base_model, payload.config, payload.total_rounds, created_by_user_id=current_user.id)
        return federated_service.serialize_job(job)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/jobs/{job_id}/start-round")
def start_round(job_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        rnd = federated_service.start_round(db, job_id)
        return federated_service.serialize_round(rnd)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/jobs/{job_id}/submit-update")
def submit_update(job_id: int, payload: UpdateIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        upd = federated_service.submit_update(db, job_id, payload.round_id, payload.org_id, payload.update, payload.metrics)
        return {"id": upd.id, "status": upd.status, "org_id": upd.org_id, "round_id": upd.round_id}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/rounds/{round_id}/aggregate")
def aggregate_round(round_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        rnd = federated_service.aggregate_round(db, round_id)
        return federated_service.serialize_round(rnd)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/jobs/{job_id}/status")
def job_status(job_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        return federated_service.get_job_status(db, job_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
