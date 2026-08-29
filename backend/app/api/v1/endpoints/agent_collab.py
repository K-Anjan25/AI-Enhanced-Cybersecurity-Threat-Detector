"""Phase 83: Agent-to-Agent collaboration endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import agent_collab_service

router = APIRouter(prefix="/agent-collab", tags=["Agent Collab (Phase 83)"])

class CollabIn(BaseModel):
    case_id: int
    name: str
    agents: Optional[List[str]] = None

class MessageIn(BaseModel):
    from_agent: str
    content: str
    to_agent: Optional[str] = None
    message_type: str = "proposal"

@router.get("/")
def list_collabs(case_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        collabs = agent_collab_service.list_collaborations(db, current_user.org_id, case_id=case_id)
        return [agent_collab_service.serialize_collab(c) for c in collabs]
    except Exception:
        return []

@router.post("/")
def create_collab(payload: CollabIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        collab = agent_collab_service.create_collaboration(db, current_user.org_id, payload.case_id, payload.name, payload.agents, created_by_user_id=current_user.id)
        return agent_collab_service.serialize_collab(collab)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/{collab_id}/run")
def run_collab(collab_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        collab = agent_collab_service.run_collaboration_round(db, current_user.org_id, collab_id)
        return agent_collab_service.serialize_collab(collab)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/{collab_id}/messages")
def get_messages(collab_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        msgs = agent_collab_service.get_messages(db, current_user.org_id, collab_id)
        return [agent_collab_service.serialize_message(m) for m in msgs]
    except Exception:
        return []

@router.post("/{collab_id}/messages")
def add_message(collab_id: int, payload: MessageIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        msg = agent_collab_service.add_message(db, current_user.org_id, collab_id, payload.from_agent, payload.content, payload.to_agent, payload.message_type)
        return agent_collab_service.serialize_message(msg)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
