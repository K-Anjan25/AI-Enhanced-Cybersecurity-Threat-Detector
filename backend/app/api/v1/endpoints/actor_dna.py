"""Phase 113: Actor DNA endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any, Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import actor_dna_service

router = APIRouter(prefix="/actor-dna", tags=["Actor DNA P113"])

class ActorIn(BaseModel):
    actor_name: str
    behavior_genome: Optional[Dict[str, Any]] = None

class AttrIn(BaseModel):
    case_id: int
    actor_dna_id: int

@router.get("/actors")
def list_actors(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        actors = actor_dna_service.list_actors(db, current_user.org_id)
        return [actor_dna_service.serialize_actor(a) for a in actors]
    except Exception:
        return []

@router.post("/actors")
def create_actor(payload: ActorIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        a = actor_dna_service.create_actor_dna(db, current_user.org_id, payload.actor_name, payload.behavior_genome)
        return actor_dna_service.serialize_actor(a)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/attribute")
def attribute(payload: AttrIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        attr = actor_dna_service.attribute_case(db, current_user.org_id, payload.case_id, payload.actor_dna_id)
        return {"id": attr.id, "confidence": attr.confidence, "status": attr.status}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
