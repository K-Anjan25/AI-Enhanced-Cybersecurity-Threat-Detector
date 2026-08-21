"""Autonomous-analyst API (Phase 18).

The product surface: simulate an incident, read the calm brief + decision feed,
open a case, and make the human decision (approve / decline / revert). Mirrors
the ``cases.py`` conventions -- ``{data,total,page,limit}`` envelope, org scoping
via ``current_user.org_id``, reads gated by ``get_current_user`` and writes by
the existing ``alerts:write`` permission (no new permissions introduced).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import analyst_service, scenario
from app.services.case_service import serialize_case

router = APIRouter(prefix="/analyst", tags=["Analyst"])


@router.post("/simulate", status_code=201)
def simulate_incident(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Inject the credential-leak scenario and open a pending analyst case."""
    case = scenario.run_credential_leak(
        db, org_id=current_user.org_id, actor=current_user.username, created_by_id=current_user.id
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
