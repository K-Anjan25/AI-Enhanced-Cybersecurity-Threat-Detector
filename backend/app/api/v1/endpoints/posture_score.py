"""Phase 99: Posture Score v2 endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import posture_score_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/posture-score", tags=["Posture Score v2 (Phase 99)"])

@router.get("/latest")
def get_latest(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        score = posture_score_service.calculate_posture(db, current_user.org_id)
        return posture_score_service.serialize_score(score)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/history")
def get_history(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        scores = posture_score_service.list_scores(db, current_user.org_id)
        return [posture_score_service.serialize_score(s) for s in scores]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/findings")
def list_findings(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        findings = posture_score_service.list_findings(db, current_user.org_id)
        return [posture_score_service.serialize_finding(f) for f in findings]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/recommendations")
def list_recommendations(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        recs = posture_score_service.list_recommendations(db, current_user.org_id)
        return [posture_score_service.serialize_recommendation(r) for r in recs]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e