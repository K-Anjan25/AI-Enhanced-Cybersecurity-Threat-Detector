"""Phase 149: Dimensional Barrier endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import dimensional_barrier_service

router = APIRouter(prefix="/dimensional-barrier", tags=["Dimensional Barrier P149"])

class In(BaseModel):
    name: str
    dimension_id: str = "3d_primary"

class BreachIn(BaseModel):
    barrier_id: int
    breach_type: str = "interdimensional_incursion"

@router.get("/barriers")
def list_bar(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        bars = dimensional_barrier_service.list_barriers(db, current_user.org_id)
        return [dimensional_barrier_service.serialize_barrier(b) for b in bars]
    except Exception:
        return []

@router.post("/barriers")
def create_bar(payload: In, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        b = dimensional_barrier_service.create_barrier(db, current_user.org_id, payload.name, payload.dimension_id)
        return dimensional_barrier_service.serialize_barrier(b)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/breaches")
def breach(payload: BreachIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        br = dimensional_barrier_service.breach(db, current_user.org_id, payload.barrier_id, payload.breach_type)
        return dimensional_barrier_service.serialize_breach(br)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
