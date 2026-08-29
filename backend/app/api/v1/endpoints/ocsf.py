"""OCSF normalization endpoints — export alerts as OCSF (Phase 44)."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, SecurityAlert
from app.services import ocsf_service

router = APIRouter(prefix="/ocsf", tags=["OCSF"])


@router.get("/alerts")
def export_alerts_ocsf(
    limit: int = Query(100, ge=1, le=500),
    severity: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export recent alerts as OCSF Security Findings."""
    q = db.query(SecurityAlert).filter(SecurityAlert.org_id == current_user.org_id)
    if severity:
        q = q.filter(SecurityAlert.severity == severity.upper())
    if source:
        q = q.filter(SecurityAlert.source == source)
    q = q.order_by(SecurityAlert.created_at.desc()).limit(limit)
    alerts = q.all()

    return ocsf_service.alerts_to_ocsf_batch(alerts)


@router.get("/alerts/{alert_id}")
def export_single_alert_ocsf(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = (
        db.query(SecurityAlert)
        .filter(SecurityAlert.id == alert_id, SecurityAlert.org_id == current_user.org_id)
        .first()
    )
    if not alert:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Alert not found")

    return ocsf_service.alert_to_ocsf_finding(alert)


@router.get("/brief")
def get_ocsf_brief(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Brief summary of recent connector alerts in OCSF terms for analyst chat grounding."""
    q = (
        db.query(SecurityAlert)
        .filter(SecurityAlert.org_id == current_user.org_id)
        .order_by(SecurityAlert.created_at.desc())
        .limit(limit)
    )
    alerts = q.all()
    ocsf_batch = ocsf_service.alerts_to_ocsf_batch(alerts)
    summary = ocsf_service.ocsf_to_brief_summary(ocsf_batch["findings"])

    return {
        "summary": summary,
        "findings": ocsf_batch["findings"][:10],  # sample
        "total": len(alerts),
    }
