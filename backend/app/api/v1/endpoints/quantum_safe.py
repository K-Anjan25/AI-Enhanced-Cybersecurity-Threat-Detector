"""Phase 92: Quantum-Safe endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import quantum_safe_service

router = APIRouter(prefix="/quantum-safe", tags=["Quantum Safe (Phase 92)"])

class PlanIn(BaseModel):
    name: str
    inventory_ids: List[int]
    target_algorithm: str = "Kyber-768"

@router.get("/inventory")
def list_inventory(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        quantum_safe_service.scan_crypto(db, current_user.org_id)
        inv = quantum_safe_service.list_inventory(db, current_user.org_id)
        return [quantum_safe_service.serialize_inv(i) for i in inv]
    except Exception:
        return []

@router.post("/scan")
def scan_crypto(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        inv = quantum_safe_service.scan_crypto(db, current_user.org_id)
        return [quantum_safe_service.serialize_inv(i) for i in inv]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/migration-plan")
def create_plan(payload: PlanIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        plan = quantum_safe_service.create_migration_plan(db, current_user.org_id, payload.name, payload.inventory_ids, payload.target_algorithm)
        return quantum_safe_service.serialize_plan(plan)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
