"""Phase 133: Autonomous Economy service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.autonomous_economy import CyberEconomy, ResourceMarket, EconomyTransaction

def _now():
    return datetime.now(timezone.utc)

def create_economy(db: Session, org_id: int, name: str) -> CyberEconomy:
    eco = CyberEconomy(org_id=org_id, name=name, token_name="NOCTRA", total_supply=1000000.0, circulating_supply=600000.0, treasury_balance=150000.0, status="active")
    db.add(eco)
    db.commit()
    db.refresh(eco)
    for rtype in ["compute","intel","defense","healing"]:
        market = ResourceMarket(economy_id=eco.id, org_id=org_id, resource_type=rtype, supply=1000.0, demand=800.0, price=1.5 + len(rtype)*0.1)
        db.add(market)
    db.commit()
    return eco

def list_economies(db: Session, org_id: int) -> List[CyberEconomy]:
    return db.query(CyberEconomy).filter(CyberEconomy.org_id == org_id).all()

def transact(db: Session, org_id: int, economy_id: int, from_agent: str, to_agent: str, amount: float, resource_type: str = "compute") -> EconomyTransaction:
    eco = db.query(CyberEconomy).filter(CyberEconomy.id == economy_id, CyberEconomy.org_id == org_id).first()
    if not eco:
        raise ValueError("Economy not found")
    tx = EconomyTransaction(economy_id=economy_id, org_id=org_id, from_agent=from_agent, to_agent=to_agent, amount=amount, resource_type=resource_type, purpose=f"Allocate {resource_type} for defense")
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx

def serialize_economy(e: CyberEconomy) -> Dict[str, Any]:
    return {"id": e.id, "name": e.name, "token_name": e.token_name, "total_supply": e.total_supply, "circulating_supply": e.circulating_supply, "treasury_balance": e.treasury_balance, "status": e.status}
