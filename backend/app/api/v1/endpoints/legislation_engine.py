"""Phase 123: Legislation Engine endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import legislation_engine_service

router = APIRouter(prefix="/legislation-engine", tags=["Legislation Engine P123"])

class RegIn(BaseModel):
    name: str
    framework: str = "GDPR"

@router.get("/regulations")
def list_regs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        regs = legislation_engine_service.list_regulations(db, current_user.org_id)
        return [legislation_engine_service.serialize_reg(r) for r in regs]
    except Exception:
        return []

@router.post("/regulations")
def create_reg(payload: RegIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        r = legislation_engine_service.create_regulation(db, current_user.org_id, payload.name, payload.framework)
        return legislation_engine_service.serialize_reg(r)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/regulations/{reg_id}/generate-policy")
def gen_policy(reg_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        p = legislation_engine_service.generate_policy(db, current_user.org_id, reg_id)
        return legislation_engine_service.serialize_policy(p)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
