"""Phase 93: Attack Path endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import attack_path_service

router = APIRouter(prefix="/attack-path", tags=["Attack Path (Phase 93)"])

@router.get("/")
def list_paths(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        paths = attack_path_service.list_paths(db, current_user.org_id)
        if not paths:
            paths = attack_path_service.analyze_paths(db, current_user.org_id)
        return [attack_path_service.serialize_path(p) for p in paths]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/analyze")
def analyze(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        paths = attack_path_service.analyze_paths(db, current_user.org_id)
        return [attack_path_service.serialize_path(p) for p in paths]
    except Exception as e:
        return {"status": "error", "detail": str(e)}
