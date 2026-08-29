"""Phase 131: Multiverse SOC service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.multiverse_soc import Multiverse, UniverseBranch, CrossUniverseIntel

def _now():
    return datetime.now(timezone.utc)

def create_multiverse(db: Session, org_id: int, name: str, branching_factor: int = 10) -> Multiverse:
    mv = Multiverse(org_id=org_id, name=name, branching_factor=branching_factor, divergence_point="Initial breach attempt", coherence_score=92.0, status="active")
    db.add(mv)
    db.commit()
    db.refresh(mv)
    # Create branches
    outcomes = ["contained","breach","contained","contained","catastrophic"]
    for i in range(branching_factor):
        branch = UniverseBranch(multiverse_id=mv.id, org_id=org_id, branch_id=f"universe-{i}", timeline_json={"events": [f"event-{i}-{j}" for j in range(3)]}, threat_outcome=outcomes[i%len(outcomes)], probability=1.0/branching_factor)
        db.add(branch)
    db.commit()
    # Cross-universe intel
    intel = CrossUniverseIntel(multiverse_id=mv.id, org_id=org_id, intel_type="threat_pattern", shared_across_branches=["T1078 common in 80% branches"], consensus_probability=0.8)
    db.add(intel)
    db.commit()
    return mv

def list_multiverses(db: Session, org_id: int) -> List[Multiverse]:
    return db.query(Multiverse).filter(Multiverse.org_id == org_id).all()

def list_branches(db: Session, org_id: int, multiverse_id: int = None) -> List[UniverseBranch]:
    q = db.query(UniverseBranch).filter(UniverseBranch.org_id == org_id)
    if multiverse_id:
        q = q.filter(UniverseBranch.multiverse_id == multiverse_id)
    return q.limit(50).all()

def serialize_mv(m: Multiverse) -> Dict[str, Any]:
    return {"id": m.id, "name": m.name, "branching_factor": m.branching_factor, "divergence_point": m.divergence_point, "coherence_score": m.coherence_score, "status": m.status}

def serialize_branch(b: UniverseBranch) -> Dict[str, Any]:
    return {"id": b.id, "multiverse_id": b.multiverse_id, "branch_id": b.branch_id, "threat_outcome": b.threat_outcome, "probability": b.probability, "timeline": b.timeline_json}
