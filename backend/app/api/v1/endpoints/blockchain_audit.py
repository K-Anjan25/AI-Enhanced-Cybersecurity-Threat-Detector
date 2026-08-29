"""Phase 119: Blockchain Audit endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import blockchain_audit_service

router = APIRouter(prefix="/blockchain-audit", tags=["Blockchain Audit P119"])

class LedgerIn(BaseModel):
    name: str

class BlockIn(BaseModel):
    ledger_id: int
    payload: Dict[str, Any]

@router.get("/ledgers")
def list_ledgers(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ledgers = blockchain_audit_service.list_ledgers(db, current_user.org_id)
        return [blockchain_audit_service.serialize_ledger(l) for l in ledgers]
    except Exception:
        return []

@router.post("/ledgers")
def create_ledger(payload: LedgerIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        l = blockchain_audit_service.create_ledger(db, current_user.org_id, payload.name)
        return blockchain_audit_service.serialize_ledger(l)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/blocks")
def add_block(payload: BlockIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        b = blockchain_audit_service.add_block(db, current_user.org_id, payload.ledger_id, payload.payload)
        return blockchain_audit_service.serialize_block(b)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.post("/ledgers/{ledger_id}/verify")
def verify(ledger_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        v = blockchain_audit_service.verify_chain(db, current_user.org_id, ledger_id)
        return {"verified_blocks": v.verified_blocks, "is_valid": v.is_valid, "invalid_blocks": v.invalid_blocks, "verification_time_ms": v.verification_time_ms}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
