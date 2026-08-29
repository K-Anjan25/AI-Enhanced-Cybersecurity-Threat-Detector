"""Phase 97: DRP endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import drp_service

router = APIRouter(prefix="/drp", tags=["DRP (Phase 97)"])

class MonitorIn(BaseModel):
    name: str
    monitor_type: str = "domain"
    keyword: str

@router.get("/monitors")
def list_monitors(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        drp_service.seed_monitors(db, current_user.org_id)
        mons = drp_service.list_monitors(db, current_user.org_id)
        return [drp_service.serialize_monitor(m) for m in mons]
    except Exception:
        return []

@router.post("/monitors")
def create_monitor(payload: MonitorIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        m = drp_service.create_monitor(db, current_user.org_id, payload.name, payload.monitor_type, payload.keyword)
        return drp_service.serialize_monitor(m)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/scan")
def scan(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        findings = drp_service.scan_drp(db, current_user.org_id)
        return [drp_service.serialize_finding(f) for f in findings]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/findings")
def list_findings(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        findings = drp_service.list_findings(db, current_user.org_id)
        return [drp_service.serialize_finding(f) for f in findings]
    except Exception:
        return []
