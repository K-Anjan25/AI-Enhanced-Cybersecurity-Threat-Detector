"""Phase 51: Case collaboration — comments, mentions, activity feed."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from app.models import User
from app.models.case_comment import CaseComment, CaseActivity

MENTION_RE = re.compile(r"@(\w+)")


def extract_mentions(content: str) -> List[str]:
    return list(set(MENTION_RE.findall(content)))


def create_comment(
    db: Session,
    org_id: int,
    case_id: int,
    user_id: int,
    content: str,
) -> CaseComment:
    mentions = extract_mentions(content)
    comment = CaseComment(
        case_id=case_id,
        org_id=org_id,
        user_id=user_id,
        content=content,
        mentions=mentions,
    )
    db.add(comment)
    db.flush()

    # Activity
    activity = CaseActivity(
        case_id=case_id,
        org_id=org_id,
        user_id=user_id,
        action="comment",
        details={"comment_id": comment.id, "mentions": mentions, "preview": content[:100]},
    )
    db.add(activity)
    db.commit()
    db.refresh(comment)

    # Publish to EventBus for real-time
    try:
        from app.core.events import bus

        bus.publish(
            {
                "type": "case_comment",
                "case_id": case_id,
                "org_id": org_id,
                "comment_id": comment.id,
                "user_id": user_id,
                "mentions": mentions,
            }
        )
    except Exception:
        pass

    return comment


def list_comments(db: Session, org_id: int, case_id: int) -> List[CaseComment]:
    return (
        db.query(CaseComment)
        .filter(CaseComment.org_id == org_id, CaseComment.case_id == case_id)
        .order_by(CaseComment.created_at.asc())
        .all()
    )


def update_comment(db: Session, org_id: int, comment_id: int, user_id: int, content: str) -> CaseComment:
    comment = (
        db.query(CaseComment)
        .filter(CaseComment.id == comment_id, CaseComment.org_id == org_id)
        .first()
    )
    if not comment:
        raise ValueError("Comment not found")
    if comment.user_id != user_id:
        # Allow admin to edit? For simplicity, only author can edit, but check in endpoint via permission
        pass
    comment.content = content
    comment.mentions = extract_mentions(content)
    comment.is_edited = True
    comment.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(comment)
    return comment


def delete_comment(db: Session, org_id: int, comment_id: int) -> bool:
    comment = (
        db.query(CaseComment)
        .filter(CaseComment.id == comment_id, CaseComment.org_id == org_id)
        .first()
    )
    if not comment:
        return False
    db.delete(comment)
    db.commit()
    return True


def list_activities(db: Session, org_id: int, case_id: int, limit: int = 50) -> List[CaseActivity]:
    return (
        db.query(CaseActivity)
        .filter(CaseActivity.org_id == org_id, CaseActivity.case_id == case_id)
        .order_by(CaseActivity.created_at.desc())
        .limit(limit)
        .all()
    )


def log_activity(db: Session, org_id: int, case_id: int, user_id: Optional[int], action: str, details: Dict[str, Any] = None):
    act = CaseActivity(
        case_id=case_id,
        org_id=org_id,
        user_id=user_id,
        action=action,
        details=details or {},
    )
    db.add(act)
    db.commit()
    return act


def serialize_comment(c: CaseComment) -> Dict[str, Any]:
    return {
        "id": c.id,
        "case_id": c.case_id,
        "org_id": c.org_id,
        "user_id": c.user_id,
        "username": c.user.username if c.user else None,
        "content": c.content,
        "mentions": c.mentions or [],
        "is_edited": c.is_edited,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def serialize_activity(a: CaseActivity) -> Dict[str, Any]:
    return {
        "id": a.id,
        "case_id": a.case_id,
        "org_id": a.org_id,
        "user_id": a.user_id,
        "action": a.action,
        "details": a.details,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
