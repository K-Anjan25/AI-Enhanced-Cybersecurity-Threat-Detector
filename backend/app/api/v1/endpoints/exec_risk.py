"""Phase 72: Exec risk endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import exec_risk_service, response_metrics

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exec-risk", tags=["exec-risk"])

@router.get("/response-times")
def get_response_times(
    window_days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    """Measured time-to-triage, time-to-decision and time-to-contain.

    Computed from recorded timestamps, with each metric carrying its sample
    size and a `reliable` flag. Metrics this system genuinely cannot produce —
    true MTTD, cost avoidance, analyst hours saved — are listed under
    `not_measured` with the reason, rather than omitted.
    """
    window = max(1, min(window_days, 365))
    return response_metrics.compute(db, current_user.org_id, window_days=window)


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        metrics = exec_risk_service.calculate_risk_metrics(db, current_user.org_id)
        return [exec_risk_service.serialize_metric(m) for m in metrics]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/board-pack")
def generate_board_pack(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        report = exec_risk_service.generate_board_pack(db, current_user.org_id, generated_by_user_id=current_user.id)
        return exec_risk_service.serialize_report(report)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/reports")
def list_reports(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        reports = exec_risk_service.list_reports(db, current_user.org_id)
        return [exec_risk_service.serialize_report(r) for r in reports]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/roi")
def get_roi(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        return exec_risk_service.calculate_roi(db, current_user.org_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e