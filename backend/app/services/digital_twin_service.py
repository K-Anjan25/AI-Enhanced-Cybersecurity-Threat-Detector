"""Phase 104: Digital Twin service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.digital_twin import DigitalTwin, TwinSimulation, ResilienceScore

def _now():
    return datetime.now(timezone.utc)

def create_twin(db: Session, org_id: int, name: str, twin_type: str = "infrastructure") -> DigitalTwin:
    twin = DigitalTwin(org_id=org_id, name=name, twin_type=twin_type, source_config_json={"source": "cspm+assets", "sync_interval": "1h"}, fidelity_score=88.5, status="active")
    db.add(twin)
    db.commit()
    db.refresh(twin)
    return twin

def list_twins(db: Session, org_id: int) -> List[DigitalTwin]:
    return db.query(DigitalTwin).filter(DigitalTwin.org_id == org_id).order_by(DigitalTwin.created_at.desc()).all()

def run_simulation(db: Session, org_id: int, twin_id: int, scenario: str = "ransomware") -> TwinSimulation:
    twin = db.query(DigitalTwin).filter(DigitalTwin.id == twin_id, DigitalTwin.org_id == org_id).first()
    if not twin:
        raise ValueError("Twin not found")
    result = {"blast_radius": 12, "time_to_recover_hours": 4.5, "affected_assets": ["web01","db01"], "mitigation_effectiveness": 0.85}
    sim = TwinSimulation(twin_id=twin_id, org_id=org_id, name=f"{scenario} simulation {datetime.now(timezone.utc).isoformat()}", scenario=scenario, simulation_config={"scenario": scenario}, result_json=result, resilience_impact=15.0, status="completed")
    db.add(sim)
    db.commit()
    db.refresh(sim)
    # Create resilience score
    score = ResilienceScore(org_id=org_id, twin_id=twin_id, overall_score=72.5, breakdown_json={"recoverability": 80, "redundancy": 65, "segmentation": 70}, recommendations=["Improve segmentation","Add backup redundancy"])
    db.add(score)
    db.commit()
    return sim

def get_resilience(db: Session, org_id: int) -> List[ResilienceScore]:
    return db.query(ResilienceScore).filter(ResilienceScore.org_id == org_id).order_by(ResilienceScore.created_at.desc()).limit(10).all()

def serialize_twin(t: DigitalTwin) -> Dict[str, Any]:
    return {"id": t.id, "name": t.name, "twin_type": t.twin_type, "fidelity_score": t.fidelity_score, "status": t.status, "source_config": t.source_config_json}

def serialize_sim(s: TwinSimulation) -> Dict[str, Any]:
    return {"id": s.id, "twin_id": s.twin_id, "name": s.name, "scenario": s.scenario, "result": s.result_json, "resilience_impact": s.resilience_impact, "status": s.status}
