"""Phase 139: Existential Risk service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.existential_risk import ExistentialRisk, XRiskMitigation, XRiskScenario

def _now():
    return datetime.now(timezone.utc)

def create_xrisk(db: Session, org_id: int, name: str, category: str = "ai", prob: float = 0.001) -> ExistentialRisk:
    risk = ExistentialRisk(org_id=org_id, risk_name=name, risk_category=category, probability=prob, impact="extinction" if category in ["ai","bio"] else "collapse", timeline_years=50, mitigation_readiness=60.0, status="monitoring")
    db.add(risk)
    db.commit()
    db.refresh(risk)
    # Mitigation
    mit = XRiskMitigation(risk_id=risk.id, org_id=org_id, mitigation_name=f"Mitigate {name} via alignment", mitigation_type="technical", effectiveness=75.0, cost=1000000.0, status="proposed")
    db.add(mit)
    db.commit()
    return risk

def list_xrisks(db: Session, org_id: int) -> List[ExistentialRisk]:
    return db.query(ExistentialRisk).filter(ExistentialRisk.org_id == org_id).order_by(ExistentialRisk.probability.desc()).all()

def create_scenario(db: Session, org_id: int, name: str, risks: List[int]) -> XRiskScenario:
    scen = XRiskScenario(org_id=org_id, scenario_name=name, risks_json=risks, cascade_probability=0.0005, simulation_result={"survival_probability": 0.999, "cascade_triggered": False})
    db.add(scen)
    db.commit()
    db.refresh(scen)
    return scen

def serialize_xrisk(r: ExistentialRisk) -> Dict[str, Any]:
    return {"id": r.id, "risk_name": r.risk_name, "risk_category": r.risk_category, "probability": r.probability, "impact": r.impact, "timeline_years": r.timeline_years, "mitigation_readiness": r.mitigation_readiness, "status": r.status}
