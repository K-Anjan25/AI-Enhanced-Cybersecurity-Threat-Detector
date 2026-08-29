"""Phase 146: Genesis Protocol endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import genesis_protocol_service

router = APIRouter(prefix="/genesis-protocol", tags=["Genesis Protocol P146"])

class In(BaseModel):
    name: str

@router.get("/universes")
def list_uni(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        unis = genesis_protocol_service.list_genesis(db, current_user.org_id)
        return [genesis_protocol_service.serialize_genesis(u) for u in unis]
    except Exception:
        return []

@router.post("/universes")
def create_uni(payload: In, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        u = genesis_protocol_service.create_genesis(db, current_user.org_id, payload.name)
        return genesis_protocol_service.serialize_genesis(u)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
