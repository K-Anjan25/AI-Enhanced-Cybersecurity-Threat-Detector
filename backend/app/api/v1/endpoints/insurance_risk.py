"""Phase 112: Insurance Risk endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import insurance_risk_service

router = APIRouter(prefix="/insurance-risk", tags=["Insurance Risk P112"])

class PolicyIn(BaseModel):
    policy_name: str

@router.get("/policies")
def list_pols(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        pols = insurance_risk_service.list_policies(db, current_user.org_id)
        return [insurance_risk_service.serialize_policy(p) for p in pols]
    except Exception:
        return []

@router.post("/policies")
def create_pol(payload: PolicyIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        p = insurance_risk_service.create_policy(db, current_user.org_id, payload.policy_name)
        return insurance_risk_service.serialize_policy(p)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/quantify")
def quantify(asset_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        rq = insurance_risk_service.quantify_risk(db, current_user.org_id, asset_id)
        return insurance_risk_service.serialize_rq(rq)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/quantifications")
def list_rq(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        rqs = insurance_risk_service.list_quantifications(db, current_user.org_id)
        return [insurance_risk_service.serialize_rq(r) for r in rqs]
    except Exception:
        return []
