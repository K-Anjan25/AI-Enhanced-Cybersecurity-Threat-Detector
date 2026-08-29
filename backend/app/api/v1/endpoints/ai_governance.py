"""Phase 106: AI Governance endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import ai_governance_service

router = APIRouter(prefix="/ai-governance", tags=["AI Governance P106"])

class CardIn(BaseModel):
    model_name: str
    purpose: str = "Threat detection"

@router.get("/model-cards")
def list_cards(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cards = ai_governance_service.list_model_cards(db, current_user.org_id)
        return [ai_governance_service.serialize_card(c) for c in cards]
    except Exception:
        return []

@router.post("/model-cards")
def create_card(payload: CardIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        card = ai_governance_service.create_model_card(db, current_user.org_id, payload.model_name, payload.purpose)
        return ai_governance_service.serialize_card(card)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/model-cards/{card_id}/audit")
def audit_card(card_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        audit = ai_governance_service.run_bias_audit(db, current_user.org_id, card_id)
        return ai_governance_service.serialize_audit(audit)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
