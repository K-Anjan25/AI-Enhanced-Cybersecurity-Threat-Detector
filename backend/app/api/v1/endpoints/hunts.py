"""Phase 62: Threat hunting workbench."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import hunt_service

router = APIRouter(prefix="/hunts", tags=["Threat Hunting (Phase 62)"])


class HuntCreate(BaseModel):
    name: str
    query: str
    description: Optional[str] = None
    query_language: str = "kql"
    is_saved: bool = False


class ExecuteRequest(BaseModel):
    query: str
    limit: int = 100


@router.get("")
def list_hunts(saved_only: bool = False, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    rows = hunt_service.list_hunts(db, org_id=current_user.org_id, saved_only=saved_only)
    return [hunt_service.serialize_hunt(r) for r in rows]


@router.post("", status_code=201)
def create_hunt(payload: HuntCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:write"))):
    hunt = hunt_service.create_hunt(
        db,
        org_id=current_user.org_id,
        name=payload.name,
        query=payload.query,
        description=payload.description,
        query_language=payload.query_language,
        is_saved=payload.is_saved,
        created_by_user_id=current_user.id,
    )
    return hunt_service.serialize_hunt(hunt)


@router.post("/execute")
def execute_query(payload: ExecuteRequest, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    return hunt_service.execute_hunt_query(db, org_id=current_user.org_id, query=payload.query, limit=payload.limit)


@router.post("/{hunt_id}/execute", status_code=201)
def execute_saved(hunt_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    try:
        exec_log = hunt_service.execute_and_log_hunt(db, org_id=current_user.org_id, hunt_id=hunt_id, user_id=current_user.id)
        return hunt_service.serialize_execution(exec_log)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{hunt_id}/executions")
def list_executions(hunt_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    from app.models.hunt import HuntExecution

    rows = db.query(HuntExecution).filter(HuntExecution.org_id == current_user.org_id, HuntExecution.hunt_id == hunt_id).order_by(HuntExecution.executed_at.desc()).all()
    return [hunt_service.serialize_execution(r) for r in rows]
