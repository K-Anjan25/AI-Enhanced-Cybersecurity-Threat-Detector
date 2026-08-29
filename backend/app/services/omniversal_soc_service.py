"""Phase 141: Omniversal SOC service."""
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.omniversal_soc import Omniverse, OmniverseBranch, CrossOmniverseIntel

def _now():
    return datetime.now(timezone.utc)

def create_omniverse(db: Session, org_id: int, name: str, total: int = 1000) -> Omniverse:
    ov = Omniverse(org_id=org_id, name=name, total_multiverses=total, branching_factor=100, coherence_score=99.99, status="observing")
    db.add(ov)
    db.commit()
    db.refresh(ov)
    outcomes = ["contained","breach","catastrophic","omniverse_collapse","vacuum_decay"]
    for i in range(20):  # 20 branches representing infinite
        br = OmniverseBranch(omniverse_id=ov.id, org_id=org_id, multiverse_signature=f"MV-{i}-SIG-{hash(name+i)%10000}", threat_outcome=outcomes[i % len(outcomes)], probability=0.01 + (i*0.005), divergence_score=0.05*i, timeline_json={"iteration": i, "threat": f"omniverse threat {i}", "contained": i%2==0})
        db.add(br)
    db.commit()
    return ov

def list_omniverses(db: Session, org_id: int) -> List[Omniverse]:
    return db.query(Omniverse).filter(Omniverse.org_id == org_id).all()

def list_branches(db: Session, org_id: int, omniverse_id: int = None) -> List[OmniverseBranch]:
    q = db.query(OmniverseBranch).filter(OmniverseBranch.org_id == org_id)
    if omniverse_id:
        q = q.filter(OmniverseBranch.omniverse_id == omniverse_id)
    return q.all()

def serialize_ov(o: Omniverse) -> Dict[str, Any]:
    return {"id": o.id, "name": o.name, "total_multiverses": o.total_multiverses, "branching_factor": o.branching_factor, "coherence_score": o.coherence_score, "status": o.status}
def serialize_branch(b: OmniverseBranch) -> Dict[str, Any]:
    return {"id": b.id, "omniverse_id": b.omniverse_id, "multiverse_signature": b.multiverse_signature, "threat_outcome": b.threat_outcome, "probability": b.probability, "divergence_score": b.divergence_score, "timeline_json": b.timeline_json}
