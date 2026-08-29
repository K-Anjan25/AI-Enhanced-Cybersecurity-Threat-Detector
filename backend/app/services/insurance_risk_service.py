"""Phase 112: Insurance Risk service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.insurance_risk import InsurancePolicy, RiskQuantification, BreachCostModel

def _now():
    return datetime.now(timezone.utc)

def create_policy(db: Session, org_id: int, name: str) -> InsurancePolicy:
    pol = InsurancePolicy(org_id=org_id, policy_name=name, provider="Chubb", coverage_amount=5000000.0, premium=75000.0, coverage_json={"ransomware": 2000000, "data_breach": 5000000, "business_interruption": 1000000}, status="active")
    db.add(pol)
    db.commit()
    db.refresh(pol)
    return pol

def list_policies(db: Session, org_id: int) -> List[InsurancePolicy]:
    return db.query(InsurancePolicy).filter(InsurancePolicy.org_id == org_id).all()

def quantify_risk(db: Session, org_id: int, asset_id: int = None) -> RiskQuantification:
    # ALE = SLE * ARO
    sle = 500000.0
    aro = 0.3
    ale = sle * aro
    rq = RiskQuantification(org_id=org_id, asset_id=asset_id, annualized_loss_expectancy=ale, single_loss_expectancy=sle, annual_rate_occurrence=aro, risk_factors_json={"threat_likelihood": "medium", "vulnerability": "high"})
    db.add(rq)
    db.commit()
    db.refresh(rq)
    # Breach cost model
    bc = BreachCostModel(org_id=org_id, scenario="ransomware", estimated_cost=ale*1.5, breakdown_json={"forensics": 75000, "legal": 150000, "notification": 50000, "ransom": 200000, "recovery": 100000}, confidence=0.78)
    db.add(bc)
    db.commit()
    return rq

def list_quantifications(db: Session, org_id: int) -> List[RiskQuantification]:
    return db.query(RiskQuantification).filter(RiskQuantification.org_id == org_id).order_by(RiskQuantification.created_at.desc()).limit(20).all()

def serialize_policy(p: InsurancePolicy) -> Dict[str, Any]:
    return {"id": p.id, "policy_name": p.policy_name, "provider": p.provider, "coverage_amount": p.coverage_amount, "premium": p.premium, "coverage": p.coverage_json, "status": p.status}

def serialize_rq(r: RiskQuantification) -> Dict[str, Any]:
    return {"id": r.id, "asset_id": r.asset_id, "ale": r.annualized_loss_expectancy, "sle": r.single_loss_expectancy, "aro": r.annual_rate_occurrence, "risk_factors": r.risk_factors_json}
