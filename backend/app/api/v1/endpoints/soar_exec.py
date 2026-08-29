"""Phase 50: SOAR real execution engine endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import soar_executor, soar
from app.services.soar import SUPPORTED_ACTIONS

router = APIRouter(prefix="/soar-exec", tags=["SOAR Execution (Phase 50)"])


class DryRunRequest(BaseModel):
    alert: dict


class ApproveRequest(BaseModel):
    action_id: str


@router.post("/dry-run")
def dry_run(
    payload: DryRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    from app.models import DetectionRule, SoarPlaybook

    rules = db.query(DetectionRule).filter(DetectionRule.org_id == current_user.org_id).all()
    playbooks = db.query(SoarPlaybook).filter(SoarPlaybook.org_id == current_user.org_id).all()
    alert = {**payload.alert, "org_id": current_user.org_id}
    result = soar_executor.dry_run_evaluate(db, alert, rules, playbooks)
    return {"matched_actions": result, "dry_run": True}


@router.post("/execute/{action_id}/approve")
def approve_execute(
    action_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    try:
        return soar_executor.approve_and_execute(db, action_id=action_id, actor=current_user.username)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/pending")
def list_pending(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    from app.models import SoarAction

    rows = (
        db.query(SoarAction)
        .filter(SoarAction.org_id == current_user.org_id, SoarAction.status == "pending_approval")
        .order_by(SoarAction.created_at.desc())
        .all()
    )
    return [{"action_id": r.action_id, "action_type": r.action_type, "severity": r.severity, "rule_name": r.rule_name, "payload": r.payload, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.get("/targets")
def list_targets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Show configured external targets
    from app.core.config import settings

    return {
        "slack_configured": bool(getattr(settings, "SOAR_SLACK_WEBHOOK_URL", None)),
        "jira_configured": bool(getattr(settings, "SOAR_JIRA_URL", None) and getattr(settings, "SOAR_JIRA_TOKEN", None)),
        "pagerduty_configured": bool(getattr(settings, "SOAR_PAGERDUTY_KEY", None)),
        "webhook_enabled": getattr(settings, "SOAR_WEBHOOK_ENABLED", True),
        "supported_actions": list(SUPPORTED_ACTIONS),
    }
