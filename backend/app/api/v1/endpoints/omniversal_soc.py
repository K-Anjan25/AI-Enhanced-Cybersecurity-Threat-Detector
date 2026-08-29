"""Phase 141: Omniversal SOC endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import omniversal_soc_service

router = APIRouter(prefix="/omniversal-soc", tags=["Omniversal SOC P141"])

class In(BaseModel):
    name: str
    total_multiverses: int = 1000

@router.get("/omniverses")
def list_ov(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ovs = omniversal_soc_service.list_omniverses(db, current_user.org_id)
        return [omniversal_soc_service.serialize_ov(o) for o in ovs]
    except Exception:
        return []

@router.post("/omniverses")
def create_ov(payload: In, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ov = omniversal_soc_service.create_omniverse(db, current_user.org_id, payload.name, payload.total_multiverses)
        return omniversal_soc_service.serialize_ov(ov)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/branches")
def list_branches(omniverse_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        branches = omniversal_soc_service.list_branches(db, current_user.org_id, omniverse_id)
        return [omniversal_soc_service.serialize_branch(b) for b in branches]
    except Exception:
        return []
