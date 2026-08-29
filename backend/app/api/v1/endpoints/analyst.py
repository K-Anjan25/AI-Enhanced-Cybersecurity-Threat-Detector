"""Autonomous-analyst API (Phases 18-19).

The product surface: simulate incidents, read the calm brief + decision feed,
open a case, make human decisions (approve / decline / revert), ask NOCTRA
questions, and monitor connected security integrations.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import analyst_service, connector_service, scenario
from app.services.case_service import serialize_case

router = APIRouter(prefix="/analyst", tags=["Analyst"])


class ChatRequest(BaseModel):
    message: str


@router.post("/simulate", status_code=201)
def simulate_incident(
    scenario_type: str = Query("credential_leak", description="Scenario: credential_leak, phishing_outbreak, data_exfiltration, compromised_api_key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Inject a simulated incident scenario and open a pending analyst case."""
    case = scenario.run_scenario(
        db,
        scenario_type=scenario_type,
        org_id=current_user.org_id,
        actor=current_user.username,
        created_by_id=current_user.id,
    )
    return serialize_case(case)


@router.get("/brief")
def get_brief(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calm summary for the analyst home screen."""
    return analyst_service.get_brief(db, org_id=current_user.org_id)


@router.get("/feed")
def get_feed(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated feed of analyst decisions, newest first."""
    items, total = analyst_service.list_feed(db, org_id=current_user.org_id, page=page, limit=limit)
    return {
        "data": [serialize_case(c) for c in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/connectors")
def get_connectors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Status of integrated security tools, derived from real configuration and
    real sync state — a connector reads "connected" only if its last sync
    actually succeeded, and counts come from ingested rows."""
    return connector_service.list_connectors(db, org_id=current_user.org_id)


@router.post("/connectors/{connector_id}/sync")
def sync_connector(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Run a sync for a security connector.

    Returns `synced` when a poll really fetched events, `recorded` when there
    was nothing to fetch (no config / disabled / push mode), and `error` with
    the reason when a poll was attempted and failed.
    """
    try:
        return connector_service.sync(
            db, connector_id=connector_id, org_id=current_user.org_id, actor=current_user.username
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/cases/{case_id}")
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full analyst case: analysis, blast radius, proposed action, decision, report."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return serialize_case(case)


@router.post("/cases/{case_id}/chat")
def chat_about_case(
    case_id: int,
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Interactive NOCTRA Q&A regarding case context, MITRE mapping, or remediation."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    return analyst_service.chat_about_case(
        db, case=case, question=body.message.strip(), actor=current_user.username
    )


@router.post("/cases/{case_id}/approve")
def approve_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Authorize the drafted action: execute via SOAR, record, generate report."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        case = analyst_service.approve_case(db, case, actor=current_user.username, actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return serialize_case(case)


@router.post("/cases/{case_id}/decline")
def decline_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Dismiss the case with no system change."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        case = analyst_service.decline_case(db, case, actor=current_user.username, actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return serialize_case(case)


@router.post("/cases/{case_id}/revert")
def revert_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Roll back a previously approved action via a recorded compensating entry."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        case = analyst_service.revert_case(db, case, actor=current_user.username, actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return serialize_case(case)


@router.get("/cases/{case_id}/report")
def get_report(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the stored markdown report for a case (empty until decided)."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"case_id": case.id, "report": case.report or ""}


@router.get("/cases/{case_id}/timeline")
def get_timeline(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Server-side case record: entries composed from real rows only
    (source alert, case fields, recorded SOAR action, audit trail)."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"case_id": case.id, "entries": analyst_service.case_timeline(db, case)}


@router.get("/notifications")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Derived notification feed: pending decisions + outcomes from the last
    24 h. No unread-state table — clients track the last-seen timestamp."""
    return {"items": analyst_service.list_notifications(db, org_id=current_user.org_id)}
