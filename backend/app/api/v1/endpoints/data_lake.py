"""Phase 73: Data Lake endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import data_lake_service

router = APIRouter(prefix="/data-lake", tags=["data-lake (Phase 73)"])

class ExportIn(BaseModel):
    year: Optional[int] = None
    month: Optional[int] = None

class QueryIn(BaseModel):
    athena_sql: str

@router.post("/export")
def export_alerts(payload: ExportIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        exp = data_lake_service.export_alerts_to_parquet(db, current_user.org_id, year=payload.year, month=payload.month, created_by_user_id=current_user.id)
        return data_lake_service.serialize_export(exp)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/exports")
def list_exports(limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        exps = data_lake_service.list_exports(db, current_user.org_id, limit=limit)
        return [data_lake_service.serialize_export(e) for e in exps]
    except Exception:
        return []

@router.post("/query")
def query_datalake(payload: QueryIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        q = data_lake_service.query_datalake(db, current_user.org_id, payload.athena_sql)
        return data_lake_service.serialize_query(q)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
