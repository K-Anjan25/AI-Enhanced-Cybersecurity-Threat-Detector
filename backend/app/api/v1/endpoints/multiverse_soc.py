"""Phase 131: Multiverse SOC endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import multiverse_soc_service

router = APIRouter(prefix="/multiverse-soc", tags=["Multiverse SOC P131"])

class MVIn(BaseModel):
    name: str
    branching_factor: int = 10

@router.get("/multiverses")
def list_mv(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        mvs = multiverse_soc_service.list_multiverses(db, current_user.org_id)
        return [multiverse_soc_service.serialize_mv(m) for m in mvs]
    except Exception:
        return []

@router.post("/multiverses")
def create_mv(payload: MVIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        mv = multiverse_soc_service.create_multiverse(db, current_user.org_id, payload.name, payload.branching_factor)
        return multiverse_soc_service.serialize_mv(mv)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/branches")
def list_branches(multiverse_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        branches = multiverse_soc_service.list_branches(db, current_user.org_id, multiverse_id)
        return [multiverse_soc_service.serialize_branch(b) for b in branches]
    except Exception:
        return []
