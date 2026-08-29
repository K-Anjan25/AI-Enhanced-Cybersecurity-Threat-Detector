"""Phase 101: Global SOC Federation endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import global_federation_service

router = APIRouter(prefix="/global-federation", tags=["Global Federation P101"])

class FedIn(BaseModel):
    name: str
    regions: Optional[List[str]] = None

class ShareIn(BaseModel):
    federation_id: int
    case_id: int
    shared_with_orgs: List[int]

@router.get("/federations")
def list_feds(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        feds = global_federation_service.list_federations(db, current_user.org_id)
        return [global_federation_service.serialize_fed(f) for f in feds]
    except Exception:
        return []

@router.post("/federations")
def create_fed(payload: FedIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        fed = global_federation_service.create_federation(db, current_user.org_id, payload.name, payload.regions)
        return global_federation_service.serialize_fed(fed)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/tenants")
def list_tenants(federation_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        tenants = global_federation_service.list_tenants(db, current_user.org_id, federation_id)
        return [global_federation_service.serialize_tenant(t) for t in tenants]
    except Exception:
        return []

@router.post("/share-case")
def share_case(payload: ShareIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        share = global_federation_service.share_case_cross_border(db, current_user.org_id, payload.federation_id, payload.case_id, payload.shared_with_orgs)
        return {"id": share.id, "status": share.status}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
