from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models import User
from app.core.security import verify_password, get_password_hash


def get_profile_data(db: Session, user_id: int):
    """
    Fetches the authenticated user profile from the database.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return {
        "id": user.id,
        "name": user.username,
        "username": user.username,
        "email": user.email,
        "role": user.role or "USER",
        # `profile_image` is the actual column name on the User model
        "profileImageURL": user.profile_image or "",
        "status": "Active"
    }


def update_user_password(db: Session, payload: dict):
    user_id = payload.get("user_id")
    current_password = payload.get("current_password")
    new_password = payload.get("new_password")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(current_password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect current password")

    user.password = get_password_hash(new_password)
    db.commit()

    return {"message": "Password updated successfully"}


def update_user_profile_data(db: Session, user_id: int, payload: dict):
    """
    Updates the user's profile details (username and profile image) in the database.
    """
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Accept username from multiple possible keys. `.get(key, next)` (not
    # `or`) so an explicit empty string is honoured when provided.
    new_name = payload.get("username", payload.get("Name", payload.get("name")))
    if new_name is not None:
        db_user.username = new_name

    # `profile_image` is the actual column name on the User model. Empty string
    # must clear the avatar — a falsy `or` chain would swallow it.
    profile_img = payload.get(
        "profileImageURL",
        payload.get("profile_image_url", payload.get("profile_image")),
    )
    if profile_img is not None:
        db_user.profile_image = profile_img

    db.commit()
    db.refresh(db_user)

    return {
        "message": "Profile updated successfully",
        "data": {
            "name": db_user.username,
            "username": db_user.username,
            "email": db_user.email,
            "profileImageURL": db_user.profile_image or ""
        }
    }