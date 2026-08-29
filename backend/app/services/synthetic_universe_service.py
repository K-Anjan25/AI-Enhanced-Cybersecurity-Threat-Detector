"""Phase 124: Synthetic Universe service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.synthetic_universe import SyntheticUniverse, SyntheticDataset, SyntheticScenario

def _now():
    return datetime.now(timezone.utc)

def create_universe(db: Session, org_id: int, name: str, universe_type: str = "soc", scale: str = "large") -> SyntheticUniverse:
    uni = SyntheticUniverse(org_id=org_id, name=name, universe_type=universe_type, scale=scale, realism_score=92.5, privacy_preserved=True, status="active")
    db.add(uni)
    db.commit()
    db.refresh(uni)
    return uni

def list_universes(db: Session, org_id: int) -> List[SyntheticUniverse]:
    return db.query(SyntheticUniverse).filter(SyntheticUniverse.org_id == org_id).all()

def generate_dataset(db: Session, org_id: int, universe_id: int, data_type: str = "alerts", count: int = 10000) -> SyntheticDataset:
    uni = db.query(SyntheticUniverse).filter(SyntheticUniverse.id == universe_id, SyntheticUniverse.org_id == org_id).first()
    if not uni:
        raise ValueError("Universe not found")
    ds = SyntheticDataset(universe_id=universe_id, org_id=org_id, dataset_name=f"{data_type}-{count}-{datetime.now(timezone.utc).isoformat()}", record_count=count, data_type=data_type, schema_json={"fields": ["timestamp","severity","src_ip","dst_ip"]}, generation_model="gan+llm", quality_metrics_json={"fidelity": 0.92, "privacy": 0.99, "utility": 0.88})
    db.add(ds)
    db.commit()
    db.refresh(ds)
    # Scenario
    scen = SyntheticScenario(dataset_id=ds.id, org_id=org_id, scenario_name="APT29 lateral movement", attack_chain=[{"ttp": "T1078"}, {"ttp": "T1021"}], difficulty="hard")
    db.add(scen)
    db.commit()
    return ds

def serialize_universe(u: SyntheticUniverse) -> Dict[str, Any]:
    return {"id": u.id, "name": u.name, "universe_type": u.universe_type, "scale": u.scale, "realism_score": u.realism_score, "privacy_preserved": u.privacy_preserved, "status": u.status}

def serialize_dataset(d: SyntheticDataset) -> Dict[str, Any]:
    return {"id": d.id, "universe_id": d.universe_id, "dataset_name": d.dataset_name, "record_count": d.record_count, "data_type": d.data_type, "generation_model": d.generation_model, "quality_metrics": d.quality_metrics_json}
