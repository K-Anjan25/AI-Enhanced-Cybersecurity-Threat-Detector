"""Phase 103: Hunt Swarm endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import hunt_swarm_service

router = APIRouter(prefix="/hunt-swarm", tags=["Hunt Swarm P103"])

class SwarmIn(BaseModel):
    name: str
    objective: str
    swarm_size: int = 5

@router.get("/swarms")
def list_swarms(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        swarms = hunt_swarm_service.list_swarms(db, current_user.org_id)
        return [hunt_swarm_service.serialize_swarm(s) for s in swarms]
    except Exception:
        return []

@router.post("/swarms")
def create_swarm(payload: SwarmIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        s = hunt_swarm_service.create_swarm(db, current_user.org_id, payload.name, payload.objective, payload.swarm_size)
        return hunt_swarm_service.serialize_swarm(s)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/swarms/{swarm_id}/launch")
def launch_swarm(swarm_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        s = hunt_swarm_service.launch_swarm(db, current_user.org_id, swarm_id)
        return hunt_swarm_service.serialize_swarm(s)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/findings")
def list_findings(swarm_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        findings = hunt_swarm_service.list_findings(db, current_user.org_id, swarm_id)
        return [hunt_swarm_service.serialize_finding(f) for f in findings]
    except Exception:
        return []
