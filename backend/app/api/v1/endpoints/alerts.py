from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import csv
import io
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import SecurityAlert, User
from app.services.alert_service import process_log
from app.core.abac import require_permission, require_any_permission
from app.api.v1.endpoints.auth import get_current_user
from app.utils.helpers import serialize_alert

router = APIRouter()


@router.post("/analyze")
def analyze(log: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Analyze a single log entry and return the anomaly result."""
    alert = process_log(log, produce_kafka=False, org_id=current_user.org_id)
    return alert


@router.get("/alerts")
def get_alerts(
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return security alerts ordered by most recent first, paginated.

    Response shape: ``{"items": [...], "total": N, "page": P, "limit": L}``
    """
    page = max(1, page)
    limit = min(max(1, limit), 100)

    query = db.query(SecurityAlert).order_by(SecurityAlert.created_at.desc())
    total = query.count()
    alerts = query.offset((page - 1) * limit).limit(limit).all()

    return {
        "items": [serialize_alert(a) for a in alerts],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.delete("/alerts/clear")
def clear_alerts(db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:delete"))):
    """Clear all security alerts. Requires the alerts:delete permission."""
    db.query(SecurityAlert).delete()
    db.commit()
    return {"message": "All alerts cleared"}


@router.get("/alerts/export")
def export_alerts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Stream all security alerts as a downloadable CSV file."""
    alerts = db.query(SecurityAlert).order_by(SecurityAlert.created_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "alert_type", "source_ip", "source", "severity", "score", "message", "created_at"])
    for a in alerts:
        writer.writerow([
            a.id,
            a.alert_type,
            a.source_ip,
            a.source,
            a.severity,
            a.score,
            a.message,
            a.created_at.isoformat() if a.created_at else "",
        ])

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=security_alerts.csv"},
    )