from fastapi import APIRouter, Depends, HTTPException
from app.api.v1.endpoints.auth import require_role
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import User
from app.services import item_service

router = APIRouter()


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
