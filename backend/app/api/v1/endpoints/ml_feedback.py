"""Phase 55: ML feedback loop + drift detection."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import ml_feedback_service

router = APIRouter(prefix="/ml", tags=["ML Feedback (Phase 55)"])


class FeedbackCreate(BaseModel):
    alert_id: int
    feedback_type: str  # true_positive, false_positive, etc
    corrected_severity: Optional[str] = None
    comment: Optional[str] = None


@router.post("/feedback", status_code=201)
def submit_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    try:
        fb = ml_feedback_service.submit_feedback(
            db,
            org_id=current_user.org_id,
            alert_id=payload.alert_id,
            feedback_type=payload.feedback_type,
            corrected_severity=payload.corrected_severity,
            comment=payload.comment,
            user_id=current_user.id,
        )
        return ml_feedback_service.serialize_feedback(fb)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/feedback")
def list_feedback(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    rows = ml_feedback_service.list_feedback(db, org_id=current_user.org_id, limit=limit)
    return [ml_feedback_service.serialize_feedback(r) for r in rows]


@router.get("/feedback/stats")
def feedback_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    return ml_feedback_service.get_feedback_stats(db, org_id=current_user.org_id)


@router.get("/drift")
def drift_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    result = ml_feedback_service.check_drift(db, org_id=current_user.org_id)
    return result


@router.get("/models")
def list_models(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    rows = ml_feedback_service.list_model_versions(db, org_id=current_user.org_id)
    return [ml_feedback_service.serialize_model_version(m) for m in rows]
