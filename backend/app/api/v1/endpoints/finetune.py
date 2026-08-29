"""Phase 76: Fine-tune endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import finetune_service

router = APIRouter(prefix="/finetune", tags=["FineTune (Phase 76)"])

class DatasetIn(BaseModel):
    name: str
    source: str = "cases"

class JobIn(BaseModel):
    name: str
    base_model: str = "claude-sonnet-5"
    dataset_type: str = "cases"
    config: Optional[Dict[str, Any]] = None

@router.post("/datasets")
def create_dataset(payload: DatasetIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ds = finetune_service.create_dataset(db, current_user.org_id, payload.name, payload.source)
        return finetune_service.serialize_dataset(ds)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ds = finetune_service.list_datasets(db, current_user.org_id)
        return [finetune_service.serialize_dataset(d) for d in ds]
    except Exception:
        return []

@router.post("/jobs")
def create_job(payload: JobIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        job = finetune_service.create_finetune_job(db, current_user.org_id, payload.name, payload.base_model, payload.dataset_type, payload.config, created_by_user_id=current_user.id)
        return finetune_service.serialize_job(job)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        jobs = finetune_service.list_jobs(db, current_user.org_id)
        return [finetune_service.serialize_job(j) for j in jobs]
    except Exception:
        return []
