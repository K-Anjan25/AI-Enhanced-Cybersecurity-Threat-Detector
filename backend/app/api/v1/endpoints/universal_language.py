"""Phase 137: Universal Language endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import universal_language_service

router = APIRouter(prefix="/universal-language", tags=["Universal Language P137"])

class ModelIn(BaseModel):
    name: str

class TranslateIn(BaseModel):
    model_id: int
    source_format: str = "stix"
    target_format: str = "sigma"
    content: Dict[str, Any] = {"type": "indicator", "pattern": "[ipv4-addr:value = '1.2.3.4']"}

@router.get("/models")
def list_models(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        models = universal_language_service.list_models(db, current_user.org_id)
        return [universal_language_service.serialize_model(m) for m in models]
    except Exception:
        return []

@router.post("/models")
def create_model(payload: ModelIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        m = universal_language_service.create_model(db, current_user.org_id, payload.name)
        return universal_language_service.serialize_model(m)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/translate")
def translate(payload: TranslateIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        t = universal_language_service.translate(db, current_user.org_id, payload.model_id, payload.source_format, payload.target_format, payload.content)
        return {"id": t.id, "source_format": t.source_format, "target_format": t.target_format, "translated_content": t.translated_content, "confidence": t.confidence}
    except ValueError as ve:
        return {"status": "error", "detail": str(ve)}
