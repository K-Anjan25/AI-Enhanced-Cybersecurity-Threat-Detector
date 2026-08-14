from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, SecurityAlert
from app.services.alert_service import get_alert_stats, get_top_threats

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview")
def analytics_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregated metrics used by the AI analytics dashboard."""
    return get_alert_stats(db)


@router.get("/top-threats")
def top_threats(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Most common detected threat messages."""
    return get_top_threats(db, limit=limit)


@router.get("/trends")
def alert_trends(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Daily alert counts over the last N days for time-series charts."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    alerts = (
        db.query(SecurityAlert)
        .filter(SecurityAlert.created_at >= since)
        .order_by(SecurityAlert.created_at.asc())
        .all()
    )

    buckets: dict[str, dict] = {}
    for i in range(days):
        day = (since + timedelta(days=i)).date().isoformat()
        buckets[day] = {"date": day, "total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}

    for alert in alerts:
        if not alert.created_at:
            continue
        day = alert.created_at.date().isoformat()
        if day not in buckets:
            continue
        sev = (alert.severity or "LOW").upper()
        buckets[day]["total"] += 1
        if sev in buckets[day]:
            buckets[day][sev.lower()] += 1

    return {"days": days, "trend": list(buckets.values())}
