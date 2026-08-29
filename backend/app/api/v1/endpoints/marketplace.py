"""Phase 75: Marketplace endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import marketplace_service

router = APIRouter(prefix="/marketplace", tags=["Marketplace (Phase 75)"])

class InstallIn(BaseModel):
    marketplace_id: int

@router.get("/")
def list_marketplace(category: Optional[str] = None, search: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        marketplace_service.seed_marketplace(db)
        pbs = marketplace_service.list_marketplace_db(db, category=category, search=search)
        return [marketplace_service.serialize_mp(pb) for pb in pbs]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/install")
def install(payload: InstallIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        inst = marketplace_service.install_playbook(db, current_user.org_id, payload.marketplace_id, installed_by_user_id=current_user.id)
        return marketplace_service.serialize_install(inst)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
