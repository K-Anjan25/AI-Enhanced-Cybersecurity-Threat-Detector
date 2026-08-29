"""Phase 57: Data retention, archival, legal hold, GDPR."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import data_lifecycle_service

router = APIRouter(prefix="/data-lifecycle", tags=["Data Lifecycle (Phase 57)"])


class LegalHoldCreate(BaseModel):
    case_id: Optional[int] = None
    reason: str
    scope: str = "case"


class GDPRRequestCreate(BaseModel):
    user_identifier: str
    reason: Optional[str] = None


@router.get("/policies")
def list_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    rows = data_lifecycle_service.list_policies(db, org_id=current_user.org_id)
    return [data_lifecycle_service.serialize_policy(p) for p in rows]


@router.post("/policies/ensure-defaults")
def ensure_defaults(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    rows = data_lifecycle_service.ensure_default_policies(db, org_id=current_user.org_id)
    return [data_lifecycle_service.serialize_policy(p) for p in rows]


@router.post("/archive/run")
def run_archive(
    dry_run: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    result = data_lifecycle_service.archive_old_data(db, org_id=current_user.org_id, dry_run=dry_run)
    return result


@router.get("/legal-holds")
def list_legal_holds(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    rows = data_lifecycle_service.list_legal_holds(db, org_id=current_user.org_id)
    return [data_lifecycle_service.serialize_legal_hold(h) for h in rows]


@router.post("/legal-holds", status_code=201)
def create_legal_hold(
    payload: LegalHoldCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    hold = data_lifecycle_service.create_legal_hold(
        db,
        org_id=current_user.org_id,
        case_id=payload.case_id,
        reason=payload.reason,
        created_by_user_id=current_user.id,
        scope=payload.scope,
    )
    return data_lifecycle_service.serialize_legal_hold(hold)


@router.delete("/legal-holds/{hold_id}")
def release_hold(
    hold_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    ok = data_lifecycle_service.release_legal_hold(db, org_id=current_user.org_id, hold_id=hold_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Hold not found")
    return {"status": "released"}


@router.get("/gdpr/requests")
def list_gdpr_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    rows = data_lifecycle_service.list_gdpr_requests(db, org_id=current_user.org_id)
    return [data_lifecycle_service.serialize_gdpr_request(r) for r in rows]


@router.post("/gdpr/requests", status_code=201)
def create_gdpr_request(
    payload: GDPRRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    req = data_lifecycle_service.create_gdpr_request(
        db,
        org_id=current_user.org_id,
        user_identifier=payload.user_identifier,
        reason=payload.reason,
        requested_by_user_id=current_user.id,
    )
    return data_lifecycle_service.serialize_gdpr_request(req)


@router.post("/gdpr/requests/{req_id}/approve")
def approve_gdpr(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    try:
        req = data_lifecycle_service.approve_gdpr_request(db, org_id=current_user.org_id, request_id=req_id, approved_by_user_id=current_user.id)
        return data_lifecycle_service.serialize_gdpr_request(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/gdpr/requests/{req_id}/complete")
def complete_gdpr(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    try:
        req = data_lifecycle_service.complete_gdpr_request(db, org_id=current_user.org_id, request_id=req_id)
        return data_lifecycle_service.serialize_gdpr_request(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
