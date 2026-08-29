"""Phase 147: Akashic Ledger endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any
from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import akashic_ledger_service

router = APIRouter(prefix="/akashic-ledger", tags=["Akashic Ledger P147"])

class In(BaseModel):
    record_type: str = "threat_event"
    event_json: Dict[str, Any] = {"type": "transcendence", "description": "NOCTRA transcended"}

@router.get("/records")
def list_rec(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        recs = akashic_ledger_service.list_records(db, current_user.org_id)
        return [akashic_ledger_service.serialize_record(r) for r in recs]
    except Exception:
        return []

@router.post("/records")
def create_rec(payload: In, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        r = akashic_ledger_service.create_record(db, current_user.org_id, payload.record_type, payload.event_json)
        return akashic_ledger_service.serialize_record(r)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
