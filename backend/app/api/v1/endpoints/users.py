import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import User
from app.services.user_service import get_profile_data, update_user_profile_data, update_user_password
from app.core.security import get_current_user
from app.core.abac import subject_permissions, effective_clearance, effective_department

router = APIRouter()

# Uploaded profile images live under backend/uploads/avatars and are served
# from the /uploads static mount (registered in app/main.py).
UPLOAD_ROOT = Path(__file__).resolve().parents[4] / "uploads"
AVATAR_DIR = UPLOAD_ROOT / "avatars"

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
IMAGE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB


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


@router.post("/profile/image")
async def upload_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload and set the current user's profile image.

    Validates type/size, stores the file under backend/uploads/avatars (served
    at /uploads/avatars/... via the static mount), and updates the user's
    profile_image. The previous avatar file is removed best-effort.
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image type — use PNG, JPEG, WEBP or GIF",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Image must be 5 MB or smaller")

    filename = f"user_{current_user.id}_{uuid.uuid4().hex[:12]}{IMAGE_EXT[file.content_type]}"
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    (AVATAR_DIR / filename).write_bytes(data)

    # Best-effort cleanup of the previous avatar file (only inside AVATAR_DIR).
    old_rel = getattr(current_user, "profile_image", None) or ""
    if old_rel.startswith("/uploads/avatars/"):
        old_file = UPLOAD_ROOT / old_rel[len("/uploads/"):]
        try:
            if old_file.is_file() and old_file.parent == AVATAR_DIR:
                old_file.unlink()
        except OSError:
            pass

    current_user.profile_image = f"/uploads/avatars/{filename}"
    db.commit()
    db.refresh(current_user)
    return {"message": "Profile image updated", "profileImageURL": current_user.profile_image}


@router.put("/updatePassword")
def update_password(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    payload["user_id"] = current_user.id
    return update_user_password(db, payload)