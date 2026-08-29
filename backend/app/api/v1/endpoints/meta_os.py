"""Phase 120: Meta OS endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import meta_os_service

router = APIRouter(prefix="/meta-os", tags=["Meta OS P120"])

class EvoIn(BaseModel):
    module_name: str
    change_description: str = "Optimize detection algorithm with genetic programming"

@router.get("/config")
def get_config(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cfg = meta_os_service.get_or_create_meta_os(db, current_user.org_id)
        return meta_os_service.serialize_config(cfg)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/evolve")
def propose(payload: EvoIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        evo = meta_os_service.propose_evolution(db, current_user.org_id, payload.module_name, payload.change_description)
        return meta_os_service.serialize_evolution(evo)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/evolutions/{evo_id}/deploy")
def deploy(evo_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        evo = meta_os_service.deploy_evolution(db, current_user.org_id, evo_id)
        return meta_os_service.serialize_evolution(evo)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.get("/evolutions")
def list_evos(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        evos = meta_os_service.list_evolutions(db, current_user.org_id)
        return [meta_os_service.serialize_evolution(e) for e in evos]
    except Exception:
        return []

@router.get("/metrics")
def metrics(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        return meta_os_service.get_metrics(db, current_user.org_id)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
