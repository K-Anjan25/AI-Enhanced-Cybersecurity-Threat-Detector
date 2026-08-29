"""Phase 71: Continuous compliance endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import compliance_continuous_service

router = APIRouter(prefix="/compliance-continuous", tags=["compliance-continuous"])

@router.get("/controls")
def list_controls(framework: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        compliance_continuous_service.ensure_default_controls(db, current_user.org_id)
        ctrls = compliance_continuous_service.list_controls(db, current_user.org_id, framework=framework)
        return [compliance_continuous_service.serialize_control(c) for c in ctrls]
    except Exception:
        return []

@router.post("/collect")
def collect_evidence(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        evs = compliance_continuous_service.collect_evidence(db, current_user.org_id)
        return [{"id": e.id, "control_id": e.control_id, "evidence_type": e.evidence_type, "collected_at": e.collected_at.isoformat() if e.collected_at else None} for e in evs]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/assess/{framework}")
def run_assessment(framework: str, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ass = compliance_continuous_service.run_assessment(db, current_user.org_id, framework=framework)
        return compliance_continuous_service.serialize_assessment(ass)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/assessments")
def list_assessments(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        asses = compliance_continuous_service.list_assessments(db, current_user.org_id)
        return [compliance_continuous_service.serialize_assessment(a) for a in asses]
    except Exception:
        return []
