from fastapi import APIRouter, Depends
from sqlalchemy import func
from app.core.security import require_role
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import User, Org

router = APIRouter()


@router.get("/orgs")
def list_orgs(db: Session = Depends(get_db), current_user: User = Depends(require_role("ADMIN"))):
    """Cross-tenant org listing for SOC administrators (FR-TENANT-06).

    Returns every tenant workspace with its member count, letting admins see
    across org boundaries that regular users never see.
    """
    rows = (
        db.query(Org, func.count(User.id))
        .outerjoin(User, User.org_id == Org.id)
        .group_by(Org.id)
        .order_by(Org.name.asc())
        .all()
    )
    data = [
        {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "description": org.description,
            "user_count": count,
            "created_at": org.created_at.isoformat() if org.created_at else None,
        }
        for org, count in rows
    ]
    return {"data": data, "total": len(data)}


@router.get("/roles")
def list_roles(current_user: User = Depends(require_role("ADMIN"))):
    """ABAC role -> permission matrix for the admin UI (FR-UI-06)."""
    from app.core.abac import ROLE_PERMISSIONS, DEFAULT_CLEARANCE_BY_ROLE, CLEARANCE_REQUIREMENTS

    data = [
        {
            "role": role,
            "clearance": DEFAULT_CLEARANCE_BY_ROLE.get(role, 1),
            "permissions": sorted(perms),
        }
        for role, perms in ROLE_PERMISSIONS.items()
    ]
    return {"data": data, "clearance_requirements": CLEARANCE_REQUIREMENTS}
