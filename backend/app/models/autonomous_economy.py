"""Phase 133: Autonomous Economy - tokenomics, resource allocation."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class CyberEconomy(Base):
    __tablename__ = "cyber_economies"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    token_name = Column(String(50), default="NOCTRA")
    total_supply = Column(Float, default=1000000.0)
    circulating_supply = Column(Float, default=500000.0)
    treasury_balance = Column(Float, default=100000.0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class ResourceMarket(Base):
    __tablename__ = "resource_markets"
    id = Column(Integer, primary_key=True, index=True)
    economy_id = Column(Integer, ForeignKey("cyber_economies.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    resource_type = Column(String(50), default="compute")  # compute, intel, defense, healing
    supply = Column(Float, default=1000.0)
    demand = Column(Float, default=800.0)
    price = Column(Float, default=1.5)
    created_at = Column(DateTime(timezone=True), default=_now)

class EconomyTransaction(Base):
    __tablename__ = "economy_transactions"
    id = Column(Integer, primary_key=True, index=True)
    economy_id = Column(Integer, ForeignKey("cyber_economies.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    from_agent = Column(String(200), nullable=False)
    to_agent = Column(String(200), nullable=False)
    amount = Column(Float, default=0.0)
    resource_type = Column(String(50), default="compute")
    purpose = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
