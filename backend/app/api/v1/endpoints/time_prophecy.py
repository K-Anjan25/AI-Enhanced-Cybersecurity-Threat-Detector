"""Phase 129: Time Prophecy endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import time_prophecy_service

router = APIRouter(prefix="/time-prophecy", tags=["Time Prophecy P129"])

class ModelIn(BaseModel):
    name: str
    model_type: str = "transformer"

@router.get("/models")
def list_models(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        models = time_prophecy_service.list_models(db, current_user.org_id)
        return [time_prophecy_service.serialize_model(m) for m in models]
    except Exception:
        return []

@router.post("/models")
def create_model(payload: ModelIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        m = time_prophecy_service.create_temporal_model(db, current_user.org_id, payload.name, payload.model_type)
        return time_prophecy_service.serialize_model(m)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/models/{model_id}/prophesy")
def prophesy(model_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        props = time_prophecy_service.prophesy(db, current_user.org_id, model_id)
        return [time_prophecy_service.serialize_prophecy(p) for p in props]
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
