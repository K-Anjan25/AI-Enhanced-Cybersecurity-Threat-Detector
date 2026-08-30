"""Phase 65: CSPM endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import cspm_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cspm", tags=["cspm"])

class AccountIn(BaseModel):
    provider: str
    account_id: str
    name: Optional[str] = None

class IaCScanIn(BaseModel):
    scanner: str = "checkov"
    target: str
    iac_content: Dict[str, Any]

@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        accs = cspm_service.list_accounts(db, current_user.org_id)
        return [{"id": a.id, "provider": a.provider, "account_id": a.account_id, "name": a.name, "status": a.status} for a in accs]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/accounts")
def create_account(payload: AccountIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        acc = cspm_service.create_account(db, current_user.org_id, payload.provider, payload.account_id, payload.name)
        return {"id": acc.id, "provider": acc.provider, "account_id": acc.account_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/violations")
def list_violations(severity: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        vs = cspm_service.list_violations(db, current_user.org_id, severity=severity)
        return [cspm_service.serialize_violation(v) for v in vs]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/evaluate")
def evaluate_cis(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        vs = cspm_service.evaluate_cis(db, current_user.org_id)
        return [cspm_service.serialize_violation(v) for v in vs]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/iac-scan")
def scan_iac(payload: IaCScanIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        scan = cspm_service.scan_iac(db, current_user.org_id, payload.scanner, payload.target, payload.iac_content)
        return {"id": scan.id, "scanner": scan.scanner, "violation_count": scan.violation_count, "results": scan.results_json}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e