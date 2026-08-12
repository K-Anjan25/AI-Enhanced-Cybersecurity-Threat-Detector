from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import case_service

router = APIRouter(prefix="/cases", tags=["Incident Management"])


@router.get("")
def list_cases(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List cases (optionally filtered by status), paginated."""
    items, total = case_service.list_cases(
        db, page=page, limit=limit, status=status, org_id=current_user.org_id
    )
    return {
        "data": [case_service.serialize_case(c) for c in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("", status_code=201)
def create_case(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Open a new incident/case, optionally linked to a source alert."""
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="'title' is required")
    payload = dict(payload)
    payload["created_by_id"] = current_user.id
    try:
        case = case_service.create_case(db, payload, actor=current_user.username, org_id=current_user.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return case_service.serialize_case(case)


@router.get("/{case_id}")
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case_service.serialize_case(case)


@router.patch("/{case_id}")
def update_case(
    case_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Update case status/priority/assignee/title/description."""
    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        case = case_service.update_case(db, case, payload, actor=current_user.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return case_service.serialize_case(case)
