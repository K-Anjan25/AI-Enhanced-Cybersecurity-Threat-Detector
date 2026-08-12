from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import User
from app.services.user_service import get_profile_data, update_user_profile_data, update_user_password
from app.api.v1.endpoints.auth import get_current_user
from app.core.abac import subject_permissions, effective_clearance, effective_department

router = APIRouter()


@router.get("/me")
async def get_current_user_me(current_user: User = Depends(get_current_user)):
    """Returns basic info about the currently authenticated user."""
    return {
        "status": "success",
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role,
            "clearance_level": effective_clearance(current_user),
            "department": effective_department(current_user),
        },
        "roles": [current_user.role] if current_user.role else [],
        "permissions": sorted(subject_permissions(current_user)),
    }


@router.get("/profile")
def get_user_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_profile_data(db, user_id=current_user.id)


@router.put("/profile")
def update_user_profile(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return update_user_profile_data(db, user_id=current_user.id, payload=payload)


@router.put("/updatePassword")
def update_password(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    payload["user_id"] = current_user.id
    return update_user_password(db, payload)