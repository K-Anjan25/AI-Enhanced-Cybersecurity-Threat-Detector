"""Phase 57 + 81: Data retention, archival, legal hold, GDPR + automation."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import data_lifecycle_service
from app.core.partitioning import ensure_partitions

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data-lifecycle", tags=["Data Lifecycle (Phase 57+81)"])

class PolicyUpdate(BaseModel):
    data_type: str
    retention_days: int
    archive_after_days: Optional[int] = None
    delete_after_days: Optional[int] = None

class LegalHoldIn(BaseModel):
    name: str
    description: Optional[str] = None
    case_ids: Optional[List[int]] = None

class GDPRIn(BaseModel):
    target_email: str
    reason: Optional[str] = None
    target_user_id: Optional[int] = None

@router.get("/policies")
def list_policies(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    rows = data_lifecycle_service.list_policies(db, org_id=current_user.org_id)
    return [{"id": r.id, "data_type": r.data_type, "retention_days": r.retention_days, "archive_after_days": r.archive_after_days, "delete_after_days": r.delete_after_days, "is_active": r.is_active} for r in rows]

@router.post("/policies")
def update_policy(payload: PolicyUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        pol = data_lifecycle_service.update_policy(db, current_user.org_id, payload.data_type, payload.retention_days, payload.archive_after_days, payload.delete_after_days)
        return {"id": pol.id, "data_type": pol.data_type, "retention_days": pol.retention_days}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/archive/{data_type}")
def archive_data(data_type: str, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        result = data_lifecycle_service.archive_old_data(db, current_user.org_id, data_type=data_type)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/automation/run")
def run_automation(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    """Phase 81: Run full retention automation - archive old data respecting legal holds."""
    try:
        results = []
        for dtype in ["alerts", "cases", "audit_logs"]:
            res = data_lifecycle_service.archive_old_data(db, current_user.org_id, data_type=dtype)
            results.append(res)
        # Also ensure partitions
        try:
            from app.core.database import engine
            ensure_partitions(engine)
        except Exception:
            pass
        archived = sum(r.get("archived_count", 0) for r in results)
        eligible = sum(r.get("eligible_count", 0) for r in results)
        return {
            "status": "completed" if archived else "not_configured",
            "results": results,
            "archived_total": archived,
            "eligible_total": eligible,
            "note": (
                "Cases under an active legal hold are excluded. No archive "
                "destination is configured, so this run reported what is "
                "eligible without moving or deleting anything."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/legal-holds")
def list_holds(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    rows = data_lifecycle_service.list_legal_holds(db, org_id=current_user.org_id)
    return [{"id": h.id, "name": h.name, "description": h.description, "case_ids": h.case_ids, "is_active": h.is_active, "created_at": h.created_at.isoformat() if h.created_at else None} for h in rows]

@router.post("/legal-holds")
def create_hold(payload: LegalHoldIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        hold = data_lifecycle_service.create_legal_hold(db, current_user.org_id, payload.name, payload.description, payload.case_ids, user_id=current_user.id)
        return {"id": hold.id, "name": hold.name, "case_ids": hold.case_ids, "is_active": hold.is_active}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/legal-holds/{hold_id}")
def release_hold(hold_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    hold = data_lifecycle_service.release_legal_hold(db, current_user.org_id, hold_id)
    if not hold:
        raise HTTPException(status_code=404, detail="Hold not found")
    return {"status": "released", "id": hold.id}

@router.get("/gdpr")
def list_gdpr(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    # Simplified
    from app.models.data_lifecycle import GDPRDeletionRequest
    rows = db.query(GDPRDeletionRequest).filter(GDPRDeletionRequest.org_id == current_user.org_id).order_by(GDPRDeletionRequest.created_at.desc()).limit(50).all()
    return [{"id": r.id, "target_email": r.target_email, "reason": r.reason, "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None, "completed_at": r.completed_at.isoformat() if r.completed_at else None} for r in rows]

@router.post("/gdpr")
def create_gdpr(payload: GDPRIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        req = data_lifecycle_service.create_gdpr_request(db, current_user.org_id, payload.target_email, payload.reason, requested_by_user_id=current_user.id, target_user_id=payload.target_user_id)
        return {"id": req.id, "target_email": req.target_email, "status": req.status}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/gdpr/{req_id}/{action}")
def process_gdpr(req_id: int, action: str, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        req = data_lifecycle_service.process_gdpr_request(db, current_user.org_id, req_id, action=action)
        return {"id": req.id, "status": req.status}
    except ValueError as e:
        # "not found" is a 404; a bad action or an already-decided request is a
        # client error the operator can act on, not a missing resource.
        detail = str(e)
        raise HTTPException(
            status_code=404 if "not found" in detail.lower() else 400, detail=detail
        )
