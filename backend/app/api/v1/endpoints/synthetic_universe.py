"""Phase 124: Synthetic Universe endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import synthetic_universe_service

router = APIRouter(prefix="/synthetic-universe", tags=["Synthetic Universe P124"])

class UniIn(BaseModel):
    name: str
    universe_type: str = "soc"
    scale: str = "large"

class DatasetIn(BaseModel):
    universe_id: int
    data_type: str = "alerts"
    record_count: int = 10000

@router.get("/universes")
def list_unis(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        unis = synthetic_universe_service.list_universes(db, current_user.org_id)
        return [synthetic_universe_service.serialize_universe(u) for u in unis]
    except Exception:
        return []

@router.post("/universes")
def create_uni(payload: UniIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        u = synthetic_universe_service.create_universe(db, current_user.org_id, payload.name, payload.universe_type, payload.scale)
        return synthetic_universe_service.serialize_universe(u)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/datasets")
def gen_dataset(payload: DatasetIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ds = synthetic_universe_service.generate_dataset(db, current_user.org_id, payload.universe_id, payload.data_type, payload.record_count)
        return synthetic_universe_service.serialize_dataset(ds)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
