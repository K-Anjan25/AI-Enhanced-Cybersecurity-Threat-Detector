from sqlalchemy.orm import Session

from app.models import Case, Org
from app.utils.helpers import paginate, create_audit_log


VALID_STATUSES = {"open", "triaging", "resolved", "closed"}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}


def get_case(db: Session, case_id: int, org_id: int | None = None) -> Case | None:
    query = db.query(Case).filter(Case.id == case_id)
    if org_id is not None:
        query = query.filter(Case.org_id == org_id)
    return query.first()


def list_cases(db: Session, page: int = 1, limit: int = 20, status: str | None = None, org_id: int | None = None) -> tuple[list, int]:
    query = db.query(Case)
    if org_id is not None:
        query = query.filter(Case.org_id == org_id)
    if status:
        query = query.filter(Case.status == status)
    query = query.order_by(Case.created_at.desc())
    return paginate(db, query, page, limit)


def create_case(db: Session, payload: dict, actor: str, org_id: int | None = None) -> Case:
    status = (payload.get("status") or "open").lower()
    priority = (payload.get("priority") or "medium").lower()
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority '{priority}'")

    case = Case(
        title=payload["title"],
        description=payload.get("description"),
        status=status,
        priority=priority,
        source_alert_id=payload.get("source_alert_id"),
        assignee_id=payload.get("assignee_id"),
        created_by_id=payload.get("created_by_id"),
        org_id=org_id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    create_audit_log(db, action="CASE_CREATED", actor=actor, resource=f"case:{case.id}")
    return case


def update_case(db: Session, case: Case, payload: dict, actor: str) -> Case:
    if "status" in payload:
        status = payload["status"].lower()
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'")
        case.status = status
    if "priority" in payload:
        priority = payload["priority"].lower()
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority '{priority}'")
        case.priority = priority
    if "assignee_id" in payload:
        case.assignee_id = payload["assignee_id"]
    if "title" in payload:
        case.title = payload["title"]
    if "description" in payload:
        case.description = payload["description"]

    db.commit()
    db.refresh(case)
    create_audit_log(db, action="CASE_UPDATED", actor=actor, resource=f"case:{case.id}", details=str(payload))
    return case


def serialize_case(case: Case) -> dict:
    return {
        "id": case.id,
        "title": case.title,
        "description": case.description,
        "status": case.status,
        "priority": case.priority,
        "source_alert_id": case.source_alert_id,
        "assignee_id": case.assignee_id,
        "created_by_id": case.created_by_id,
        "org_id": case.org_id,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        # Autonomous-analyst (Phase 18) fields. Nullable for legacy cases;
        # extra keys are safe for existing TS/UI consumers.
        "kind": getattr(case, "kind", None) or "manual",
        "analysis": getattr(case, "analysis", None),
        "blast_radius": getattr(case, "blast_radius", None),
        "proposed_action": getattr(case, "proposed_action", None),
        "decision": getattr(case, "decision", None) or "pending",
        "decided_by_id": getattr(case, "decided_by_id", None),
        "decided_at": case.decided_at.isoformat() if getattr(case, "decided_at", None) else None,
        "soar_action_id": getattr(case, "soar_action_id", None),
        "report": getattr(case, "report", None),
    }
