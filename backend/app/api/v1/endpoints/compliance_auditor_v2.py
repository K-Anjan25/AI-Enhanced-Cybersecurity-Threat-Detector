"""Phase 115: Compliance Auditor v2 endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import compliance_auditor_v2_service

router = APIRouter(prefix="/compliance-auditor-v2", tags=["Compliance Auditor v2 P115"])

class AuditIn(BaseModel):
    name: str
    framework: str = "SOC2"

@router.get("/audits")
def list_audits(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        audits = compliance_auditor_v2_service.list_audits(db, current_user.org_id)
        return [compliance_auditor_v2_service.serialize_audit(a) for a in audits]
    except Exception:
        return []

@router.post("/audits")
def create_audit(payload: AuditIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        a = compliance_auditor_v2_service.create_audit(db, current_user.org_id, payload.name, payload.framework)
        return compliance_auditor_v2_service.serialize_audit(a)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/audits/{audit_id}/run")
def run_audit(audit_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        a = compliance_auditor_v2_service.run_audit(db, current_user.org_id, audit_id)
        return compliance_auditor_v2_service.serialize_audit(a)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.get("/findings")
def list_findings(audit_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        findings = compliance_auditor_v2_service.list_findings(db, current_user.org_id, audit_id)
        return [compliance_auditor_v2_service.serialize_finding(f) for f in findings]
    except Exception:
        return []
