"""Phase 143: Chrono-Loop endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import chrono_loop_service

router = APIRouter(prefix="/chrono-loop", tags=["Chrono-Loop P143"])

class In(BaseModel):
    name: str
    loop_type: str = "closed_timelike"

@router.get("/loops")
def list_loops(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        loops = chrono_loop_service.list_loops(db, current_user.org_id)
        return [chrono_loop_service.serialize_loop(l) for l in loops]
    except Exception:
        return []

@router.post("/loops")
def create_loop(payload: In, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        l = chrono_loop_service.create_loop(db, current_user.org_id, payload.name, payload.loop_type)
        return chrono_loop_service.serialize_loop(l)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/loops/{loop_id}/iterate")
def iterate(loop_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        it = chrono_loop_service.iterate_loop(db, current_user.org_id, loop_id)
        return {"id": it.id, "iteration_number": it.iteration_number, "timeline_delta": it.timeline_delta, "paradox_detected": it.paradox_detected}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
