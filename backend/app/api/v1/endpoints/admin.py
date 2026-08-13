from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from app.api.v1.endpoints.auth import require_role
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import User, Org
from app.services import item_service

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


@router.patch("/users/{user_id}")
def update_user_role(user_id: int, payload: dict, db: Session = Depends(get_db), current_user: User = Depends(require_role("ADMIN"))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if "role" in payload:
        user.role = payload.get("role")
    if "is_active" in payload:
        user.is_active = bool(payload.get("is_active"))

    db.commit()
    db.refresh(user)

    item_service.audit(
        db,
        action="USER_UPDATED",
        actor=current_user.username,
        resource=f"user:{user.id}",
        details=str(payload),
    )
    return {"id": user.id, "role": user.role, "is_active": user.is_active}


@router.patch("/users/{user_id}/block")
def block_user(user_id: int, payload: dict, db: Session = Depends(get_db), current_user: User = Depends(require_role("ADMIN"))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_blocked = bool(payload.get("is_blocked", True))
    db.commit()
    item_service.audit(
        db,
        action="USER_BLOCKED" if user.is_blocked else "USER_UNBLOCKED",
        actor=current_user.username,
        resource=f"user:{user.id}",
    )
    return {"id": user.id, "is_blocked": user.is_blocked}


@router.delete("/users/{user_id}")
def delete_user_admin(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role("ADMIN"))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    item_service.audit(db, action="USER_DELETED", actor=current_user.username, resource=f"user:{user_id}")
    return {"success": True}
