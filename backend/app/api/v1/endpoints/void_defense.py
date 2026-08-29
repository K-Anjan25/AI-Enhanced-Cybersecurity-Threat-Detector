"""Phase 145: Void Defense endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import void_defense_service

router = APIRouter(prefix="/void-defense", tags=["Void Defense P145"])

class In(BaseModel):
    name: str

class EntityIn(BaseModel):
    sector_id: int
    entity_type: str = "void_predator"

@router.get("/sectors")
def list_sec(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        secs = void_defense_service.list_sectors(db, current_user.org_id)
        return [void_defense_service.serialize_sector(s) for s in secs]
    except Exception:
        return []

@router.post("/sectors")
def create_sec(payload: In, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        s = void_defense_service.create_sector(db, current_user.org_id, payload.name)
        return void_defense_service.serialize_sector(s)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/entities")
def spawn(payload: EntityIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        en = void_defense_service.spawn_entity(db, current_user.org_id, payload.sector_id, payload.entity_type)
        return {"id": en.id, "sector_id": en.sector_id, "entity_type": en.entity_type, "power_level": en.power_level, "status": en.status}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
