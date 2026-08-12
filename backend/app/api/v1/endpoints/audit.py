from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.abac import require_permission
from app.models import AuditLog, User
from app.schemas.item import AuditLogOut
from app.utils.helpers import paginate

router = APIRouter(tags=["Audit Logs"])


@router.get("/audit-logs")
def get_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    actor: str | None = None,
    action: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    """Return paginated audit trail entries. Requires the audit:read permission."""
    query = db.query(AuditLog)
    if actor:
        query = query.filter(AuditLog.actor.ilike(f"%{actor}%"))
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))

    query = query.order_by(AuditLog.created_at.desc())
    items, total = paginate(db, query, page, limit)

    return {
        "data": [AuditLogOut.model_validate(item).model_dump() for item in items],
        "total": total,
        "page": page,
        "limit": limit,
    }
