"""Phase 122: AGI Council endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import agi_council_service

router = APIRouter(prefix="/agi-council", tags=["AGI Council P122"])

class CouncilIn(BaseModel):
    name: str

class ConveneIn(BaseModel):
    council_id: int
    topic: str

@router.get("/councils")
def list_councils(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        councils = agi_council_service.list_councils(db, current_user.org_id)
        return [agi_council_service.serialize_council(c) for c in councils]
    except Exception:
        return []

@router.post("/councils")
def create_council(payload: CouncilIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        c = agi_council_service.create_council(db, current_user.org_id, payload.name)
        return agi_council_service.serialize_council(c)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/convene")
def convene(payload: ConveneIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        d = agi_council_service.convene_council(db, current_user.org_id, payload.council_id, payload.topic)
        return agi_council_service.serialize_decision(d)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
