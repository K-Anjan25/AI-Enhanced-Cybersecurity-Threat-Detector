"""Autonomous-analyst orchestration (Phases 18-19).

Thin service layer on top of the existing engine that drives the product loop:
a calm **brief**, a **feed** of decisions, human **approve / decline / revert**
transitions, interactive **case chat**, and security **connectors** sync.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_

from app.core.config import settings
from app.models import AuditLog, Case, SecurityAlert, Entity, SoarAction, User
from app.services import case_context, case_service, report as report_service
from app.services import soar
from app.utils.helpers import paginate, create_audit_log
from app.utils.rate_limit import RateLimiter

# Chat rate limiting: per (org, user, case) to prevent abuse of LLM costs
_chat_limiter = RateLimiter(limit=settings.ANALYST_CHAT_RATE_LIMIT, window_seconds=60)


class ChatRateLimited(Exception):
    def __init__(self, retry_after: int = 60):
        super().__init__("Too many chat questions for this case")
        self.retry_after = retry_after


def _check_chat_rate(org_id: int | None, user_id: int | None, case_id: int) -> None:
    key = f"{org_id}:{user_id}:{case_id}"
    if not _chat_limiter.check(key):
        raise ChatRateLimited()


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

    # Top pending cases carry their org context so the inbox can lead with
    # business impact ("2 hops from the DC") instead of only the headline.
    top = pending.order_by(Case.created_at.desc()).limit(5).all()
    top_serialized = []
    for c in top:
        row = case_service.serialize_case(c)
        try:
            ctx = case_context.build(db, c)
            row["context"] = ctx
            row["context_summary"] = case_context.summarize(ctx)
        except Exception:  # pragma: no cover - enrichment is best-effort
            row["context"] = {}
            row["context_summary"] = []
        top_serialized.append(row)

    return {
        "pending_count": pending_count,
        "handled_today": handled_today,
        "watching": watching,
        "alerts_today": alerts_today,
        "auto_recorded_today": auto_recorded_today,
        "top_cases": top_serialized,
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
def chat_about_case(db, case: Case, question: str, actor: str, actor_id: int | None = None) -> dict:
    """Answer analyst questions about a specific case using LLM when available,
    falling back to deterministic keyword logic.

    The LLM path is attempted first when LLM_ENABLED and ANTHROPIC_API_KEY are
    set; any failure (network, parse, empty) falls back to the keyword logic so
    the endpoint never fails for lack of a key — same resilience contract as
    analyze_incident.
    """
    analysis = case.analysis or {}
    proposed = case.proposed_action or {}
    blast = case.blast_radius or {}
    nodes = blast.get("nodes", [])

    mitre_technique_id = None
    mitre_technique = None
    if case.source_alert_id is not None:
        alert_row = (
            db.query(SecurityAlert).filter(SecurityAlert.id == case.source_alert_id).first()
        )
        mitre_technique_id = getattr(alert_row, "mitre_technique_id", None)
        mitre_technique = getattr(alert_row, "mitre_technique", None)

    # Rate limit (Phase 37) — prevents LLM cost abuse
    try:
        _check_chat_rate(case.org_id, actor_id, case.id)
    except ChatRateLimited as exc:
        raise exc

    # Phase 44: grounding on recent connector alerts (OCSF)
    connector_context = ""
    try:
        from app.services import ocsf_service

        recent_alerts = (
            db.query(SecurityAlert)
            .filter(SecurityAlert.org_id == case.org_id)
            .order_by(SecurityAlert.created_at.desc())
            .limit(10)
            .all()
        )
        if recent_alerts:
            ocsf_batch = ocsf_service.alerts_to_ocsf_batch(recent_alerts)
            connector_context = ocsf_service.ocsf_to_brief_summary(ocsf_batch["findings"])
    except Exception:
        connector_context = ""

    # Business context from the risk-reduction modules (attack paths, posture,
    # DRP). Best-effort: an empty list simply grounds the answer on less.
    try:
        org_context_lines = case_context.summarize(case_context.build(db, case))
    except Exception:  # pragma: no cover - enrichment is best-effort
        org_context_lines = []

    # Try LLM first (Phase 36)
    answer: str | None = None
    llm_used = False
    try:
        from app.services import llm_client as _llm

        context = {
            "id": case.id,
            "title": case.title,
            "what_happened": analysis.get("what_happened") or case.description or "",
            "why_it_matters": analysis.get("why_it_matters") or "",
            "blast_radius_summary": analysis.get("blast_radius_summary") or "",
            "action_type": proposed.get("action_type") or "",
            "target": proposed.get("target") or "",
            "rationale": proposed.get("rationale") or "",
            "undo": proposed.get("undo") or "",
            "mitre_id": mitre_technique_id or "",
            "mitre_name": mitre_technique or "",
            "confidence": analysis.get("confidence", 0.0),
            "model": analysis.get("model", ""),
            "fallback": analysis.get("fallback", False),
            "entities": [f"{n.get('entity_type')}:{n.get('value')}" for n in nodes[:10]],
            "connector_context": connector_context,
            # Business context for this org: reach to crown jewels, posture at
            # risk, already-leaked credentials. Empty when no module has data.
            "org_context": " ".join(org_context_lines),
        }
        llm_answer = _llm.answer_case_question(context, question)
        if llm_answer:
            answer = llm_answer
            llm_used = True
    except Exception:
        answer = None

    if not answer:
        q_lower = question.lower()

        if (
            "impact" in q_lower
            or "posture" in q_lower
            or "crown" in q_lower
            or "leak" in q_lower
            or "business" in q_lower
        ) and org_context_lines:
            answer = " ".join(org_context_lines)
        elif "blast radius" in q_lower or "entity" in q_lower or "affected" in q_lower:
            node_names = ", ".join([f"{n.get('entity_type')}:{n.get('value')}" for n in nodes[:5]])
            answer = (
                f"The blast radius contains {len(nodes)} identified entities: {node_names}. "
                f"The root entity is connected to key assets and accounts."
            )
            if org_context_lines:
                answer += " " + " ".join(org_context_lines)
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
        details=f"q:'{question[:60]}' a:'{answer[:60]}' llm:{llm_used}",
    )

    return {
        "case_id": case.id,
        "question": question,
        "answer": answer,
        "confidence": float(analysis.get("confidence", 0.92)),
        "llm_used": llm_used,
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


def bulk_decide(
    db,
    org_id: int | None,
    case_ids: list[int],
    decision: str,
    actor: str,
    actor_id: int | None,
) -> dict:
    """Bulk approve/decline for multiple pending cases.

    Returns {decided: [ids], failed: [{id, reason}]}. Only pending cases are
    acted upon; already-decided cases are reported as failed. This is honest:
    it never silently skips.
    """
    if decision not in ("approved", "declined"):
        raise ValueError("bulk decision must be 'approved' or 'declined'")

    decided = []
    failed = []
    for cid in case_ids:
        case = get_case(db, cid, org_id=org_id)
        if not case:
            failed.append({"id": cid, "reason": "not found"})
            continue
        if case.decision != "pending":
            failed.append({"id": cid, "reason": f"already {case.decision}"})
            continue
        try:
            if decision == "approved":
                approve_case(db, case, actor=actor, actor_id=actor_id)
            else:
                decline_case(db, case, actor=actor, actor_id=actor_id)
            decided.append(cid)
        except Exception as exc:
            failed.append({"id": cid, "reason": str(exc)})

    return {"decided": decided, "failed": failed, "decision": decision}


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
