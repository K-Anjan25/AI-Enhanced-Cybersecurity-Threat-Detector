"""Phase 67: Deception endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import deception_service

router = APIRouter(prefix="/deception", tags=["deception"])

class HoneypotIn(BaseModel):
    name: str
    honeypot_type: str
    port: Optional[int] = None
    banner: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class CanaryIn(BaseModel):
    name: str
    token_type: str

class TriggerIn(BaseModel):
    token_value: str
    triggered_by_ip: str
    user_agent: Optional[str] = None

class InteractionIn(BaseModel):
    honeypot_id: int
    attacker_ip: str
    payload: Optional[str] = None

@router.get("/honeypots")
def list_honeypots(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        hps = deception_service.list_honeypots(db, current_user.org_id)
        return [deception_service.serialize_hp(h) for h in hps]
    except Exception:
        return []

@router.post("/honeypots")
def create_honeypot(payload: HoneypotIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        hp = deception_service.create_honeypot(db, current_user.org_id, payload.name, payload.honeypot_type, payload.port, payload.banner, payload.config)
        return deception_service.serialize_hp(hp)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/canary")
def list_canary(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        tokens = deception_service.list_canary_tokens(db, current_user.org_id)
        return [deception_service.serialize_canary(c) for c in tokens]
    except Exception:
        return []

@router.post("/canary")
def create_canary(payload: CanaryIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ct = deception_service.create_canary_token(db, current_user.org_id, payload.name, payload.token_type, created_by_user_id=current_user.id)
        return deception_service.serialize_canary(ct)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/canary/trigger")
def trigger_canary(payload: TriggerIn, db: Session = Depends(get_db)):
    try:
        alert = deception_service.trigger_canary(db, payload.token_value, payload.triggered_by_ip, payload.user_agent)
        if alert:
            return deception_service.serialize_alert(alert)
        return {"status": "not_found"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/honeypots/interact")
def honeypot_interact(payload: InteractionIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        alert = deception_service.honeypot_interaction(db, current_user.org_id, payload.honeypot_id, payload.attacker_ip, payload.payload)
        return deception_service.serialize_alert(alert)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/alerts")
def list_alerts(limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        alerts = deception_service.list_alerts(db, current_user.org_id, limit=limit)
        return [deception_service.serialize_alert(a) for a in alerts]
    except Exception:
        return []
