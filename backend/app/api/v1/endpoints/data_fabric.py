"""Phase 95: Data Fabric endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import data_fabric_service

router = APIRouter(prefix="/data-fabric", tags=["Data Fabric (Phase 95)"])

class QueryIn(BaseModel):
    query: str
    sources: Optional[List[int]] = None

@router.get("/sources")
def list_sources(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        data_fabric_service.seed_sources(db, current_user.org_id)
        srcs = data_fabric_service.list_sources(db, current_user.org_id)
        return [data_fabric_service.serialize_source(s) for s in srcs]
    except Exception:
        return []

@router.post("/query")
def query(payload: QueryIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        q = data_fabric_service.query_fabric(db, current_user.org_id, payload.query, payload.sources, created_by_user_id=current_user.id)
        return data_fabric_service.serialize_query(q)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
