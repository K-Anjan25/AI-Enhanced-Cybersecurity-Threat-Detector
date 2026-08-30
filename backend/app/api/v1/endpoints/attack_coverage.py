"""Phase 82: ATT&CK Coverage endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import attack_coverage_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attack-coverage", tags=["ATT&CK Coverage (Phase 82)"])

@router.get("/")
def list_coverage(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        covs = attack_coverage_service.list_coverage(db, current_user.org_id)
        if not covs:
            covs = attack_coverage_service.evaluate_coverage(db, current_user.org_id)
        return [attack_coverage_service.serialize_coverage(c) for c in covs]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/evaluate")
def evaluate(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        covs = attack_coverage_service.evaluate_coverage(db, current_user.org_id)
        return [attack_coverage_service.serialize_coverage(c) for c in covs]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/report")
def get_report(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        report = attack_coverage_service.generate_report(db, current_user.org_id)
        return attack_coverage_service.serialize_report(report)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/report")
def create_report(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        report = attack_coverage_service.generate_report(db, current_user.org_id)
        return attack_coverage_service.serialize_report(report)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e