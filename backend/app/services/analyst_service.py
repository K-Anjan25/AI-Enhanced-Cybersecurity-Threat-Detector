"""Autonomous-analyst orchestration (Phases 18-19).

Thin service layer on top of the existing engine that drives the product loop:
a calm **brief**, a **feed** of decisions, human **approve / decline / revert**
transitions, interactive **case chat**, and security **connectors** sync.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_

from app.models import AuditLog, Case, SecurityAlert, Entity, SoarAction, User
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

    # Honest daily activity metrics (spec §37 addendum):
    # - alerts_today: raw detections investigated today.
    # - auto_recorded_today: SOAR responses recorded automatically by rules.
    #   Decision-path records carry rule_name "analyst-recommended" (approve)
    #   or "revert::<action>" (compensating); NULL rule_name (heuristic
    #   matches) or any other rule is genuine automation.
    start_local = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    alerts_query = db.query(SecurityAlert)
    auto_query = db.query(SoarAction).filter(
        or_(
            SoarAction.rule_name.is_(None),
            and_(
                SoarAction.rule_name.notlike("analyst-recommended"),
                SoarAction.rule_name.notlike("revert::%"),
            ),
        )
    )
    if org_id is not None:
        alerts_query = alerts_query.filter(SecurityAlert.org_id == org_id)
        auto_query = auto_query.filter(SoarAction.org_id == org_id)
    try:
        alerts_today = alerts_query.filter(SecurityAlert.created_at >= start_local).count()
        auto_recorded_today = auto_query.filter(SoarAction.created_at >= start_local).count()
    except Exception:  # pragma: no cover - datetime backend quirks
        alerts_today, auto_recorded_today = 0, 0

    top = pending.order_by(Case.created_at.desc()).limit(5).all()
    return {
        "pending_count": pending_count,
        "handled_today": handled_today,
        "watching": watching,
        "alerts_today": alerts_today,
        "auto_recorded_today": auto_recorded_today,
        "top_cases": [case_service.serialize_case(c) for c in top],
    }


# ---------------------------------------------------------------------------
# Case timeline & notifications (NOCTRA redesign — server-side record)
# ---------------------------------------------------------------------------


def case_timeline(db, case: Case) -> list[dict]:
    """Compose the case record from real rows only.

    Sources: the linked source alert (evidence), the case row itself (open,
    decision), the recorded SoarAction (approve path), the report, and
    ANALYST_* audit entries (actor + timestamp). Nothing is inferred or
    synthesized — absent rows simply produce no entries.
    """
    entries: list[dict] = []

    def _iso(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return value.isoformat()

    if case.source_alert_id is not None:
        alert_row = (
            db.query(SecurityAlert).filter(SecurityAlert.id == case.source_alert_id).first()
        )
        if alert_row is not None:
            entries.append(
                {
                    "at": _iso(getattr(alert_row, "created_at", None)),
                    "kind": "evidence",
                    "label": f"Alert #{alert_row.id} detected",
                    "detail": f"{alert_row.alert_type or 'event'} · {alert_row.severity or 'unrated'}",
                }
            )

    entries.append(
        {
            "at": _iso(case.created_at),
            "kind": "opened",
            "label": "Case opened by NOCTRA",
            "detail": (case.analysis or {}).get("headline") or case.title,
        }
    )

    if case.soar_action_id:
        action_row = db.query(SoarAction).filter(SoarAction.action_id == case.soar_action_id).first()
        if action_row is not None:
            entries.append(
                {
                    "at": _iso(action_row.created_at),
                    "kind": "action_recorded",
                    "label": f"Action recorded · {action_row.action_type}",
                    "detail": f"soar:{action_row.action_id} · record-only",
                }
            )

    if case.decision in _DECIDED and case.decided_at is not None:
        actor_name = None
        if case.decided_by_id is not None:
            user_row = db.query(User).filter(User.id == case.decided_by_id).first()
            actor_name = getattr(user_row, "username", None) if user_row else None
        label = {
            "approved": "Decision approved",
            "declined": "Decision declined — no action taken",
            "reverted": "Reverted — compensating action recorded",
        }.get(case.decision, f"Decision {case.decision}")
        entries.append(
            {
                "at": _iso(case.decided_at),
                "kind": "decision",
                "label": label,
                "detail": f"by {actor_name}" if actor_name else None,
            }
        )
        if case.report:
            entries.append(
                {
                    "at": _iso(case.decided_at),
                    "kind": "report",
                    "label": "Report generated",
                    "detail": None,
                }
            )

    audit_rows = (
        db.query(AuditLog)
        .filter(AuditLog.resource == f"case:{case.id}", AuditLog.action.like("ANALYST_%"))
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    for row in audit_rows:
        if row.action == "ANALYST_CHAT_QUESTION":
            entries.append(
                {
                    "at": _iso(row.created_at),
                    "kind": "chat",
                    "label": "Analyst consulted on the case",
                    "detail": (row.details or "")[:120] or None,
                }
            )

    entries = [e for e in entries if e["at"] is not None]
    entries.sort(key=lambda e: e["at"])
    return entries


def list_notifications(db, org_id: int | None, limit: int = 20) -> list[dict]:
    """Derived notification feed — no new tables, real rows only.

    decision_pending: cases waiting on a human decision (always relevant).
    decision_recorded: outcomes from the last 24 h (approvals/declines/reverts).
    """
    base = db.query(Case).filter(Case.kind == "analyst")
    if org_id is not None:
        base = base.filter(Case.org_id == org_id)

    items: list[dict] = []

    for c in base.filter(Case.decision == "pending").order_by(Case.created_at.desc()).all():
        items.append(
            {
                "id": f"pending-{c.id}",
                "kind": "decision_pending",
                "case_id": c.id,
                "title": (c.analysis or {}).get("headline") or c.title,
                "detail": "Awaiting your decision",
                "at": (c.created_at.isoformat() if c.created_at else None),
            }
        )

    day_ago = _now().timestamp() - 86400

    def _recent(value) -> bool:
        if value is None:
            return False
        try:
            from datetime import datetime as _dt

            ts = value if isinstance(value, _dt) else _dt.fromisoformat(str(value))
            if ts.tzinfo is None:
                from datetime import timezone as _tz

                ts = ts.replace(tzinfo=_tz.utc)
            return ts.timestamp() >= day_ago
        except Exception:  # pragma: no cover - malformed timestamps
            return False

    decided = (
        base.filter(Case.decision.in_(_DECIDED))
        .order_by(Case.decided_at.desc())
        .limit(50)
        .all()
    )
    for c in decided:
        if not _recent(c.decided_at):
            continue
        items.append(
            {
                "id": f"outcome-{c.id}",
                "kind": "decision_recorded",
                "case_id": c.id,
                "title": (c.analysis or {}).get("headline") or c.title,
                "detail": f"{c.decision} · action recorded" if c.decision == "approved" else c.decision,
                "at": (c.decided_at.isoformat() if c.decided_at else None),
            }
        )

    items = [i for i in items if i["at"] is not None]
    items.sort(key=lambda i: i["at"], reverse=True)
    return items[:limit]


# ---------------------------------------------------------------------------
# Interactive Case Chat & Connectors (Phase 19)
# ---------------------------------------------------------------------------
def chat_about_case(db, case: Case, question: str, actor: str) -> dict:
    """Answer analyst questions about a specific case using LLM / case context."""
    analysis = case.analysis or {}
    proposed = case.proposed_action or {}
    blast = case.blast_radius or {}
    nodes = blast.get("nodes", [])

    # Real MITRE mapping lives on the source alert (set at detection time),
    # not in the analysis narrative.
    mitre_technique_id = None
    mitre_technique = None
    if case.source_alert_id is not None:
        alert_row = (
            db.query(SecurityAlert).filter(SecurityAlert.id == case.source_alert_id).first()
        )
        mitre_technique_id = getattr(alert_row, "mitre_technique_id", None)
        mitre_technique = getattr(alert_row, "mitre_technique", None)

    q_lower = question.lower()

    if "blast radius" in q_lower or "entity" in q_lower or "affected" in q_lower:
        node_names = ", ".join([f"{n.get('entity_type')}:{n.get('value')}" for n in nodes[:5]])
        answer = (
            f"The blast radius contains {len(nodes)} identified entities: {node_names}. "
            f"The root entity is connected to key assets and accounts."
        )
    elif "action" in q_lower or "why" in q_lower or "recommend" in q_lower or "remediat" in q_lower:
        answer = (
            f"The recommended action is {proposed.get('action_type', 'REVOKE_CREDENTIALS')} on {proposed.get('target')}. "
            f"Rationale: {proposed.get('rationale', 'Prevent unauthorized lateral movement')}. "
            f"Reversible via: {proposed.get('undo', 'Re-enable account or IP access')}."
        )
    elif "mitre" in q_lower or "tactic" in q_lower or "technique" in q_lower:
        technique_id = mitre_technique_id or "N/A"
        technique_name = mitre_technique or "Unclassified"
        answer = (
            f"This case maps to MITRE ATT&CK technique {technique_id} ({technique_name}). "
            f"It represents an active threat vector requiring immediate containment."
        )
    else:
        answer = (
            f"Based on NOCTRA's analysis of case #{case.id}: {case.title}. "
            f"What happened: {case.description or analysis.get('what_happened')}. "
            f"Confidence score is {analysis.get('confidence', 0.9) * 100:.0f}%. "
            f"Status is {case.status} with decision '{case.decision}'."
        )

    create_audit_log(
        db,
        action="ANALYST_CHAT_QUESTION",
        actor=actor,
        resource=f"case:{case.id}",
        details=f"q:'{question[:60]}' a:'{answer[:60]}'",
    )

    return {
        "case_id": case.id,
        "question": question,
        "answer": answer,
        "confidence": float(analysis.get("confidence", 0.92)),
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
