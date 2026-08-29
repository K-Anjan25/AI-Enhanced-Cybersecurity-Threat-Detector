"""Phase 91: Federated Intel Sharing endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import federated_intel_service

router = APIRouter(prefix="/federated-intel", tags=["Federated Intel (Phase 91)"])

class PackageIn(BaseModel):
    name: str
    stix_bundle: Dict[str, Any]
    tlp: str = "AMBER"
    is_anonymized: bool = True
    recipient_orgs: Optional[List[int]] = None

@router.get("/")
def list_packages(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        pkgs = federated_intel_service.list_packages(db, current_user.org_id)
        return [federated_intel_service.serialize_pkg(p) for p in pkgs]
    except Exception:
        return []

@router.post("/")
def create_package(payload: PackageIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        pkg = federated_intel_service.create_package(db, current_user.org_id, payload.name, payload.stix_bundle, payload.tlp, payload.is_anonymized, payload.recipient_orgs)
        return federated_intel_service.serialize_pkg(pkg)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
