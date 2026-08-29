"""Phase 148: Cosmic Threat service."""
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.cosmic_threat import CosmicThreat, CosmicMitigation, CosmicSimulation

def _now():
    return datetime.now(timezone.utc)

def create_threat(db: Session, org_id: int, name: str, threat_type: str = "vacuum_decay", prob: float = 0.0001) -> CosmicThreat:
    threat = CosmicThreat(org_id=org_id, name=name, threat_type=threat_type, probability=prob, impact="omniversal_extinction" if threat_type in ["vacuum_decay","false_vacuum","big_rip"] else "universal", timeline_years=1000000, distance_light_years=1000.0, mitigation_readiness=10.0, status="monitoring")
    db.add(threat)
    db.commit()
    db.refresh(threat)
    mit = CosmicMitigation(threat_id=threat.id, org_id=org_id, mitigation_name=f"Mitigate {threat_type} via {threat_type}_stabilizer", mitigation_type=f"{threat_type}_stabilizer", effectiveness=50.0, cost_energy=1e30, status="theoretical")
    db.add(mit)
    db.commit()
    return threat

def list_threats(db: Session, org_id: int) -> List[CosmicThreat]:
    return db.query(CosmicThreat).filter(CosmicThreat.org_id == org_id).order_by(CosmicThreat.probability.desc()).all()

def create_simulation(db: Session, org_id: int, name: str, threat_ids: List[int]) -> CosmicSimulation:
    sim = CosmicSimulation(org_id=org_id, simulation_name=name, threats_json=threat_ids, simulation_result={"survival_probability": 0.999, "mitigated": True, "timeline_preserved": True}, survival_probability=0.999)
    db.add(sim)
    db.commit()
    db.refresh(sim)
    return sim

def serialize_threat(t: CosmicThreat) -> Dict[str, Any]:
    return {"id": t.id, "name": t.name, "threat_type": t.threat_type, "probability": t.probability, "impact": t.impact, "timeline_years": t.timeline_years, "distance_light_years": t.distance_light_years, "mitigation_readiness": t.mitigation_readiness, "status": t.status}
