from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import DetectionRule, SecurityAlert, SoarPlaybook, User
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
    playbooks = db.query(SoarPlaybook).filter(SoarPlaybook.is_active.is_(True)).all()
    matched = soar.evaluate_alert(payload, rules, playbooks=playbooks)
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
    playbooks = db.query(SoarPlaybook).filter(SoarPlaybook.is_active.is_(True)).all()
    alert_dict = {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "source_ip": alert.source_ip,
        "severity": alert.severity,
        "message": alert.message,
        "mitre_technique_id": alert.mitre_technique_id,
        "org_id": alert.org_id,
    }
    results = soar.respond_to_alert(db, alert_dict, rules, playbooks=playbooks)
    db.commit()
    return {"executed": results, "count": len(results)}


@router.get("/playbooks")
def list_playbooks(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:read")),
):
    """List explicit rule->action playbook overrides (org-scoped)."""
    items, total = soar.list_playbooks(db, org_id=current_user.org_id, page=page, limit=limit)
    return {
        "data": [soar.serialize_playbook(pb) for pb in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/playbooks")
def create_playbook(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:write")),
):
    """Pin a rule to a specific SOAR action (overrides the default heuristic)."""
    rule_id = payload.get("rule_id")
    name = payload.get("name")
    action_type = payload.get("action_type")
    if not all([rule_id, name, action_type]):
        raise HTTPException(status_code=400, detail="rule_id, name and action_type are required")
    rule = db.query(DetectionRule).filter(DetectionRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    try:
        playbook = soar.create_playbook(
            db, org_id=current_user.org_id, rule_id=rule_id, name=name, action_type=action_type
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return soar.serialize_playbook(playbook)


@router.patch("/playbooks/{playbook_id}")
def update_playbook(
    playbook_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:write")),
):
    """Update a playbook's action mapping, name, or active state."""
    try:
        playbook = soar.update_playbook(
            db,
            org_id=current_user.org_id,
            playbook_id=playbook_id,
            name=payload.get("name"),
            action_type=payload.get("action_type"),
            is_active=payload.get("is_active"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if playbook is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return soar.serialize_playbook(playbook)


@router.delete("/playbooks/{playbook_id}")
def delete_playbook(
    playbook_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:write")),
):
    """Remove a playbook override (the rule reverts to heuristic action)."""
    deleted = soar.delete_playbook(db, org_id=current_user.org_id, playbook_id=playbook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return {"deleted": True}
