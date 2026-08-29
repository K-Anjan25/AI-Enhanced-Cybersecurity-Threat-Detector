"""Phase 51: Case collaboration — comments, mentions, activity feed."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.services import case_collaboration_service, case_service

router = APIRouter(prefix="/cases", tags=["Collaboration (Phase 51)"])


class CommentRequest(BaseModel):
    content: str


@router.get("/{case_id}/comments")
def list_comments(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    rows = case_collaboration_service.list_comments(db, org_id=current_user.org_id, case_id=case_id)
    return [case_collaboration_service.serialize_comment(c) for c in rows]


@router.post("/{case_id}/comments", status_code=201)
def create_comment(
    case_id: int,
    payload: CommentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not payload.content or not payload.content.strip():
        raise HTTPException(status_code=422, detail="Content required")
    comment = case_collaboration_service.create_comment(
        db, org_id=current_user.org_id, case_id=case_id, user_id=current_user.id, content=payload.content.strip()
    )
    return case_collaboration_service.serialize_comment(comment)


@router.put("/{case_id}/comments/{comment_id}")
def update_comment(
    case_id: int,
    comment_id: int,
    payload: CommentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        comment = case_collaboration_service.update_comment(
            db, org_id=current_user.org_id, comment_id=comment_id, user_id=current_user.id, content=payload.content.strip()
        )
        return case_collaboration_service.serialize_comment(comment)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{case_id}/comments/{comment_id}")
def delete_comment(
    case_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ok = case_collaboration_service.delete_comment(db, org_id=current_user.org_id, comment_id=comment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"status": "deleted"}


@router.get("/{case_id}/activities")
def list_activities(
    case_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    rows = case_collaboration_service.list_activities(db, org_id=current_user.org_id, case_id=case_id, limit=limit)
    return [case_collaboration_service.serialize_activity(a) for a in rows]
