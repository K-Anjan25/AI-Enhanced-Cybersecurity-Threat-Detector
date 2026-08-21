"""Autonomous-analyst orchestration (Phase 18).

Thin service layer on top of the existing engine that drives the product loop:
a calm **brief**, a **feed** of decisions, and the human **approve / decline /
revert** transitions. Approving runs the drafted action through the existing
record-only SOAR executor, generates a report, and audits every transition.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import Case, SecurityAlert, Entity
from app.services import case_service, report as report_service
from app.services import soar
from app.utils.helpers import paginate, create_audit_log

_DECIDED = ("approved", "declined", "reverted")

# Compensating action for a revert. SOAR is record-only, so a revert is a
# recorded ALERT_OPERATOR entry carrying the original "undo" instruction.
_REVERSE_ACTION = "ALERT_OPERATOR"


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_feed(db, org_id: int | None, page: int = 1, limit: int = 20) -> tuple[list, int]:
    """Analyst decisions (kind='analyst' cases), newest first."""
    query = db.query(Case).filter(Case.kind == "analyst")
    if org_id is not None:
        query = query.filter(Case.org_id == org_id)
    query = query.order_by(Case.created_at.desc())
    return paginate(db, query, page, limit)


def get_case(db, case_id: int, org_id: int | None = None) -> Case | None:
    """Fetch a single analyst case (org-scoped)."""
    query = db.query(Case).filter(Case.id == case_id, Case.kind == "analyst")
    if org_id is not None:
        query = query.filter(Case.org_id == org_id)
    return query.first()


def get_brief(db, org_id: int | None) -> dict:
    """Calm summary for the home screen: what's pending, what was handled, scope."""
    base = db.query(Case).filter(Case.kind == "analyst")
    if org_id is not None:
        base = base.filter(Case.org_id == org_id)

    pending = base.filter(Case.decision == "pending")
    pending_count = pending.count()

    try:
        start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        handled_today = base.filter(
            Case.decision.in_(_DECIDED), Case.decided_at.isnot(None), Case.decided_at >= start
        ).count()
    except Exception:  # pragma: no cover - datetime backend quirks
        handled_today = base.filter(Case.decision.in_(_DECIDED)).count()

    entity_query = db.query(Entity)
    if org_id is not None:
        entity_query = entity_query.filter(Entity.org_id == org_id)
    watching = entity_query.count()

    top = pending.order_by(Case.created_at.desc()).limit(5).all()
    return {
        "pending_count": pending_count,
        "handled_today": handled_today,
        "watching": watching,
        "top_cases": [case_service.serialize_case(c) for c in top],
    }


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

def _alert_and_matched(db, case: Case) -> tuple[dict, dict]:
    """Build the synthetic (alert, matched) dicts SOAR's execute_action expects."""
    action = case.proposed_action or {}
    alert_row = None
    if case.source_alert_id is not None:
        alert_row = db.query(SecurityAlert).filter(SecurityAlert.id == case.source_alert_id).first()

    alert = {
        "id": case.source_alert_id,
        "org_id": case.org_id,
        "source_ip": getattr(alert_row, "source_ip", None),
        "alert_type": getattr(alert_row, "alert_type", "analyst_case"),
        "mitre_technique_id": getattr(alert_row, "mitre_technique_id", None),
    }
    matched = {
        "action_type": action.get("action_type", "ALERT_OPERATOR"),
        "severity": action.get("severity", "HIGH"),
        "rule_name": "analyst-recommended",
        "rule_id": None,
    }
    return alert, matched


def approve_case(db, case: Case, actor: str, actor_id: int | None) -> Case:
    """Authorize the drafted action: execute via SOAR, record, generate report."""
    if case.decision != "pending":
        raise ValueError(f"Case already decided ({case.decision})")

    alert, matched = _alert_and_matched(db, case)
    result = soar.execute_action(db, alert, matched)  # records a SoarAction (flush, no commit)

    case.decision = "approved"
    case.status = "resolved"
    case.soar_action_id = result.get("action_id")
    case.decided_by_id = actor_id
    case.decided_at = _now()
    case.report = report_service.build_case_report(
        case, case.analysis, case.proposed_action, "approved", actor=actor
    )
    db.commit()
    db.refresh(case)

    create_audit_log(
        db,
        action="ANALYST_CASE_APPROVED",
        actor=actor,
        resource=f"case:{case.id}",
        details=f"action:{matched['action_type']} soar:{case.soar_action_id} status:{result.get('status')}",
    )
    return case


def decline_case(db, case: Case, actor: str, actor_id: int | None) -> Case:
    """Dismiss the case with no system change."""
    if case.decision != "pending":
        raise ValueError(f"Case already decided ({case.decision})")

    case.decision = "declined"
    case.status = "closed"
    case.decided_by_id = actor_id
    case.decided_at = _now()
    case.report = report_service.build_case_report(
        case, case.analysis, case.proposed_action, "declined", actor=actor
    )
    db.commit()
    db.refresh(case)

    create_audit_log(
        db,
        action="ANALYST_CASE_DECLINED",
        actor=actor,
        resource=f"case:{case.id}",
    )
    return case


def revert_case(db, case: Case, actor: str, actor_id: int | None) -> Case:
    """Roll back a previously approved action via a recorded compensating entry."""
    if case.decision != "approved":
        raise ValueError("Only an approved case can be reverted")

    action = case.proposed_action or {}
    alert, _ = _alert_and_matched(db, case)
    compensating = {
        "action_type": _REVERSE_ACTION,
        "severity": "MEDIUM",
        "rule_name": f"revert::{action.get('action_type', 'action')}",
        "rule_id": None,
    }
    soar.execute_action(db, alert, compensating)  # recorded compensating action

    case.decision = "reverted"
    case.status = "triaging"
    case.decided_by_id = actor_id
    case.decided_at = _now()
    case.report = report_service.build_case_report(
        case, case.analysis, case.proposed_action, "reverted", actor=actor
    )
    db.commit()
    db.refresh(case)

    create_audit_log(
        db,
        action="ANALYST_CASE_REVERTED",
        actor=actor,
        resource=f"case:{case.id}",
        details=action.get("undo", ""),
    )
    return case
