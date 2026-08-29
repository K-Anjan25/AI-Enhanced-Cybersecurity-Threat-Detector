"""Phase 112: Cyber Insurance Risk Engine."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class InsurancePolicy(Base):
    __tablename__ = "insurance_policies"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    policy_name = Column(String(300), nullable=False)
    provider = Column(String(200), default="Chubb")
    coverage_amount = Column(Float, default=1000000.0)
    premium = Column(Float, default=50000.0)
    coverage_json = Column(JSON, default=dict)  # {ransomware: 500k, data_breach: 1M}
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class RiskQuantification(Base):
    __tablename__ = "risk_quantifications"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    annualized_loss_expectancy = Column(Float, default=0.0)  # ALE
    single_loss_expectancy = Column(Float, default=0.0)  # SLE
    annual_rate_occurrence = Column(Float, default=0.0)  # ARO
    risk_factors_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)

class BreachCostModel(Base):
    __tablename__ = "breach_cost_models"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    scenario = Column(String(100), default="ransomware")  # ransomware, data_breach, ddos
    estimated_cost = Column(Float, default=0.0)
    breakdown_json = Column(JSON, default=dict)  # {forensics: 50k, legal: 100k, notification: 20k}
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
