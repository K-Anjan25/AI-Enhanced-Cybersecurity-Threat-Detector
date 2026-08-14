from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import DetectionRule, SecurityAlert, User
from app.services import soar
from app.services import alert_service

router = APIRouter(prefix="/soar", tags=["SOAR"])


@router.get("/actions")
def list_actions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """List executed SOAR actions (org-scoped audit of automation)."""
    items, total = soar.list_actions(db, page=page, limit=limit, org_id=current_user.org_id)
    return {
        "data": [
            {
                "id": a.id,
                "action_id": a.action_id,
                "action_type": a.action_type,
                "severity": a.severity,
                "rule_name": a.rule_name,
                "alert_id": a.alert_id,
                "status": a.status,
                "payload": a.payload,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in items
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/evaluate")
def evaluate_alert_manually(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Dry-run: evaluate a synthetic alert dict against active rules and return
    the actions that would fire, WITHOUT executing them."""
    rules = db.query(DetectionRule).filter(DetectionRule.is_active.is_(True)).all()
    matched = soar.evaluate_alert(payload, rules)
    return {"actions": matched, "count": len(matched)}


@router.post("/trigger/{alert_id}")
def trigger_for_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Manually trigger SOAR response for an existing alert."""
    alert = db.query(SecurityAlert).filter(SecurityAlert.id == alert_id).first()
    if not alert or (alert.org_id and alert.org_id != current_user.org_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    rules = db.query(DetectionRule).filter(DetectionRule.is_active.is_(True)).all()
    alert_dict = {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "source_ip": alert.source_ip,
        "severity": alert.severity,
        "message": alert.message,
        "mitre_technique_id": alert.mitre_technique_id,
        "org_id": alert.org_id,
    }
    results = soar.respond_to_alert(db, alert_dict, rules)
    db.commit()
    return {"executed": results, "count": len(results)}
