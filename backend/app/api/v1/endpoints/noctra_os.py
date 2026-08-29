"""Phase 100: NOCTRA OS endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import noctra_os_service

router = APIRouter(prefix="/noctra-os", tags=["NOCTRA OS (Phase 100)"])

class AutonomyIn(BaseModel):
    autonomy_level: str

@router.get("/config")
def get_config(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cfg = noctra_os_service.get_or_create_config(db, current_user.org_id)
        return noctra_os_service.serialize_config(cfg)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/autonomy")
def set_autonomy(payload: AutonomyIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cfg = noctra_os_service.update_autonomy(db, current_user.org_id, payload.autonomy_level)
        return noctra_os_service.serialize_config(cfg)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        return noctra_os_service.get_os_metrics(db, current_user.org_id)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/logs")
def list_logs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        logs = noctra_os_service.list_logs(db, current_user.org_id)
        return [noctra_os_service.serialize_log(l) for l in logs]
    except Exception:
        return []
