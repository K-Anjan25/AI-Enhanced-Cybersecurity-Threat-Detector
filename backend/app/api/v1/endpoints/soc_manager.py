"""Phase 96: SOC Manager endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import soc_manager_service

router = APIRouter(prefix="/soc-manager", tags=["SOC Manager (Phase 96)"])

class OrchestrateIn(BaseModel):
    case_id: int

@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        dash = soc_manager_service.get_or_create_dashboard(db, current_user.org_id)
        return soc_manager_service.serialize_dashboard(dash)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/orchestrate")
def orchestrate(payload: OrchestrateIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        orch = soc_manager_service.orchestrate_case(db, current_user.org_id, payload.case_id)
        return soc_manager_service.serialize_orchestration(orch)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/orchestrations")
def list_orchestrations(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        orchs = soc_manager_service.list_orchestrations(db, current_user.org_id)
        return [soc_manager_service.serialize_orchestration(o) for o in orchs]
    except Exception:
        return []
