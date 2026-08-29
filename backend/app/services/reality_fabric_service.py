"""Phase 142: Reality Fabric service."""
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.reality_fabric import RealityFabric, RealityAnomaly, FabricPatch

def _now():
    return datetime.now(timezone.utc)

def create_fabric(db: Session, org_id: int, name: str) -> RealityFabric:
    fab = RealityFabric(org_id=org_id, name=name, dimension_count=11, constants_json={"c": 299792458, "G": 6.67430e-11, "hbar": 1.0545718e-34, "alpha": 0.0072973525693, "vacuum_energy": 1e-9}, integrity_score=100.0, vacuum_stability=99.99, status="stable")
    db.add(fab)
    db.commit()
    db.refresh(fab)
    return fab

def list_fabrics(db: Session, org_id: int) -> List[RealityFabric]:
    return db.query(RealityFabric).filter(RealityFabric.org_id == org_id).all()

def detect_anomaly(db: Session, org_id: int, fabric_id: int, anomaly_type: str = "constant_drift") -> RealityAnomaly:
    fab = db.query(RealityFabric).filter(RealityFabric.id == fabric_id, RealityFabric.org_id == org_id).first()
    if not fab:
        raise ValueError("Fabric not found")
    an = RealityAnomaly(fabric_id=fabric_id, org_id=org_id, anomaly_type=anomaly_type, description=f"{anomaly_type} detected - attacker attempting to alter physics constants", severity="CRITICAL", affected_constants=["alpha","c"] if anomaly_type=="constant_drift" else ["vacuum"], status="detected")
    db.add(an)
    fab.integrity_score = max(0, fab.integrity_score - 1)
    db.commit()
    db.refresh(an)
    patch = FabricPatch(anomaly_id=an.id, fabric_id=fabric_id, org_id=org_id, patch_type="constant_lock", patch_json={"lock_alpha": True, "stabilize_vacuum": True}, effectiveness=99.9, status="applied")
    db.add(patch)
    db.commit()
    return an

def serialize_fabric(f: RealityFabric) -> Dict[str, Any]:
    return {"id": f.id, "name": f.name, "dimension_count": f.dimension_count, "constants_json": f.constants_json, "integrity_score": f.integrity_score, "vacuum_stability": f.vacuum_stability, "status": f.status}
def serialize_anomaly(a: RealityAnomaly) -> Dict[str, Any]:
    return {"id": a.id, "fabric_id": a.fabric_id, "anomaly_type": a.anomaly_type, "description": a.description, "severity": a.severity, "affected_constants": a.affected_constants, "status": a.status}
