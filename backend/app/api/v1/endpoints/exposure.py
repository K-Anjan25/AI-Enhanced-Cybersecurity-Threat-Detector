"""Phase 87: Exposure Management endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import exposure_service

router = APIRouter(prefix="/exposure", tags=["Exposure ASM (Phase 87)"])

class DomainIn(BaseModel):
    domain: str
    discovery_method: str = "manual"

class DiscoverIn(BaseModel):
    domain: Optional[str] = None

@router.get("/domains")
def list_domains(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        domains = exposure_service.list_domains(db, current_user.org_id)
        return [{"id": d.id, "domain": d.domain, "discovery_method": d.discovery_method, "is_verified": d.is_verified} for d in domains]
    except Exception:
        return []

@router.post("/domains")
def add_domain(payload: DomainIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        d = exposure_service.add_domain(db, current_user.org_id, payload.domain, payload.discovery_method)
        return {"id": d.id, "domain": d.domain}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/discover")
def discover(payload: DiscoverIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        exps = exposure_service.discover_exposures(db, current_user.org_id, domain=payload.domain)
        return [exposure_service.serialize_exposure(e) for e in exps]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/")
def list_exposures(severity: Optional[str] = None, status: str = "open", db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        exps = exposure_service.list_exposures(db, current_user.org_id, severity=severity, status=status)
        return [exposure_service.serialize_exposure(e) for e in exps]
    except Exception:
        return []

@router.get("/findings")
def list_findings(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        findings = exposure_service.list_findings(db, current_user.org_id)
        return [exposure_service.serialize_finding(f) for f in findings]
    except Exception:
        return []

@router.get("/summary")
def summary(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        return exposure_service.get_exposure_summary(db, current_user.org_id)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
