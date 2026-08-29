"""Phase 77: Risk-based alerting endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import risk_based_service

router = APIRouter(prefix="/risk-based", tags=["RiskBased (Phase 77)"])

class AssetIn(BaseModel):
    name: str
    asset_type: str = "host"
    ip_address: Optional[str] = None
    hostname: Optional[str] = None
    criticality: int = 3
    business_unit: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[List[str]] = None

class RuleIn(BaseModel):
    name: str
    conditions: Dict[str, Any]
    action: str = "escalate"
    risk_multiplier: float = 1.5

@router.get("/assets")
def list_assets(criticality: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        risk_based_service.seed_assets(db, current_user.org_id)
        assets = risk_based_service.list_assets(db, current_user.org_id, criticality=criticality)
        return [risk_based_service.serialize_asset(a) for a in assets]
    except Exception:
        return []

@router.post("/assets")
def create_asset(payload: AssetIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        asset = risk_based_service.create_asset(db, current_user.org_id, payload.name, payload.asset_type, payload.ip_address, payload.hostname, payload.criticality, payload.business_unit, payload.owner, payload.tags)
        return risk_based_service.serialize_asset(asset)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/rules")
def list_rules(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        rules = risk_based_service.list_risk_rules(db, current_user.org_id)
        return [risk_based_service.serialize_rule(r) for r in rules]
    except Exception:
        return []

@router.post("/rules")
def create_rule(payload: RuleIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        rule = risk_based_service.create_risk_rule(db, current_user.org_id, payload.name, payload.conditions, payload.action, payload.risk_multiplier)
        return risk_based_service.serialize_rule(rule)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/score/{alert_id}")
def calculate_score(alert_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        log = risk_based_service.calculate_risk_score(db, current_user.org_id, alert_id)
        return risk_based_service.serialize_score_log(log)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
