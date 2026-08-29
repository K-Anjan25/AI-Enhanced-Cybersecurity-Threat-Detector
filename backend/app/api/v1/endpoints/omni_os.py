"""Phase 130: Omni OS endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import omni_os_service

router = APIRouter(prefix="/omni-os", tags=["Omni OS P130"])

@router.get("/config")
def get_config(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cfg = omni_os_service.get_or_create_omni(db, current_user.org_id)
        return omni_os_service.serialize_config(cfg)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/nodes")
def list_nodes(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        nodes = omni_os_service.list_nodes(db, current_user.org_id)
        return [omni_os_service.serialize_node(n) for n in nodes]
    except Exception:
        return []

@router.get("/metrics")
def metrics(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        return omni_os_service.get_metrics(db, current_user.org_id)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
