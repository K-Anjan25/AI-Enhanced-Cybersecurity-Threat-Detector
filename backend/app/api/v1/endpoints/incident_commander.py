"""Phase 111: Incident Commander endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import incident_commander_service

router = APIRouter(prefix="/incident-commander", tags=["Incident Commander P111"])

class CmdIn(BaseModel):
    name: str
    incident_id: Optional[int] = None

class DecisionIn(BaseModel):
    commander_id: int
    decision_type: str = "contain"
    title: str = "Isolate affected hosts"

@router.get("/commanders")
def list_cmd(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cmds = incident_commander_service.list_commanders(db, current_user.org_id)
        return [incident_commander_service.serialize_commander(c) for c in cmds]
    except Exception:
        return []

@router.post("/commanders")
def create_cmd(payload: CmdIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        c = incident_commander_service.create_commander(db, current_user.org_id, payload.name, payload.incident_id)
        return incident_commander_service.serialize_commander(c)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/decide")
def decide(payload: DecisionIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        d = incident_commander_service.make_decision(db, current_user.org_id, payload.commander_id, payload.decision_type, payload.title)
        return incident_commander_service.serialize_decision(d)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.get("/decisions")
def list_decisions(commander_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        decs = incident_commander_service.list_decisions(db, current_user.org_id, commander_id)
        return [incident_commander_service.serialize_decision(d) for d in decs]
    except Exception:
        return []
