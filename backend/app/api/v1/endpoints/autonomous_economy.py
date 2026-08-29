"""Phase 133: Autonomous Economy endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import autonomous_economy_service

router = APIRouter(prefix="/autonomous-economy", tags=["Autonomous Economy P133"])

class EconIn(BaseModel):
    name: str = "NOCTRA Cyber Economy"

class TransactIn(BaseModel):
    economy_id: int
    market_type: str = "intel"
    amount: float = 100.0

@router.get("/economies")
def list_econ(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ecos = autonomous_economy_service.list_economies(db, current_user.org_id)
        return [autonomous_economy_service.serialize_economy(e) for e in ecos]
    except Exception:
        return []

@router.post("/economies")
def create_econ(payload: EconIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        e = autonomous_economy_service.create_economy(db, current_user.org_id, payload.name)
        return autonomous_economy_service.serialize_economy(e)
    except Exception as ex:
        return {"status": "error", "detail": str(ex)}

@router.get("/markets")
def list_markets(economy_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        markets = autonomous_economy_service.list_markets(db, current_user.org_id, economy_id)
        return [{"id": m.id, "market_type": m.market_type, "supply": m.supply, "demand": m.demand, "price": m.price, "volume": m.volume} for m in markets]
    except Exception:
        return []

@router.post("/transact")
def transact(payload: TransactIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        tx = autonomous_economy_service.transact(db, current_user.org_id, payload.economy_id, payload.market_type, payload.amount)
        return {"id": tx.id, "transaction_type": tx.transaction_type, "amount": tx.amount, "price": tx.price, "status": tx.status}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
