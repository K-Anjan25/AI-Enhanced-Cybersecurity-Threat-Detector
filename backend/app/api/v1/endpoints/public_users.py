from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import User, Org
from app.core.security import require_role
from app.core.security import get_password_hash
from app.services import item_service

router = APIRouter()


@router.get("")
def list_users(
    org_id: int | None = None,
    role: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """Admin-only, cross-tenant user roster with org/role/search filtering.

    FR-TENANT-06: SOC administrators can list and filter users across every
    tenant workspace, unlike regular users who never see outside their org.
    """
    query = db.query(User, Org).join(Org, User.org_id == Org.id)

    if org_id:
        query = query.filter(User.org_id == org_id)
    if role:
        query = query.filter(User.role == role.upper())
    if search:
        like = f"%{search}%"
        query = query.filter((User.username.ilike(like)) | (User.email.ilike(like)))

    rows = query.order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "is_blocked": u.is_blocked,
            "clearance_level": u.clearance_level,
            "department": u.department,
            "org_id": u.org_id,
            "org_name": org.name,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u, org in rows
    ]


@router.post("", status_code=201)
def create_user(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    username = payload.get("username")
    email = payload.get("email")
    password = payload.get("password")
    role = payload.get("role", "USER")

    if not username or not email or not password:
        raise HTTPException(status_code=400, detail="username, email and password are required")

    existing = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    # Default to the provisioning admin's org; admins may target another tenant.
    org_id = payload.get("org_id") or current_user.org_id
    org = db.query(Org).filter(Org.id == org_id).first()
    if not org:
        raise HTTPException(status_code=400, detail="Unknown org_id")

    user = User(
        username=username,
        email=email,
        password=get_password_hash(password),
        role=role,
        org_id=org.id,
        clearance_level=payload.get("clearance_level"),
        department=payload.get("department"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"id": user.id, "username": user.username, "email": user.email, "role": user.role, "org_id": user.org_id}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    item_service.audit(db, action="USER_DELETED", actor=current_user.username, resource=f"user:{user_id}")
    return {"success": True}


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
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


@router.patch("/{user_id}/block")
def block_user(
    user_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
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
