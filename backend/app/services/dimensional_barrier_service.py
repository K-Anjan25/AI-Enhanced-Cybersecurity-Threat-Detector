"""Phase 149: Dimensional Barrier service."""
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.dimensional_barrier import DimensionalBarrier, DimensionalBreach, BarrierReinforcement

def _now():
    return datetime.now(timezone.utc)

def create_barrier(db: Session, org_id: int, name: str, dimension_id: str = "3d_primary") -> DimensionalBarrier:
    barrier = DimensionalBarrier(org_id=org_id, name=name, dimension_id=dimension_id, barrier_strength=99.9, breach_attempts=0, integrity_score=100.0, status="intact")
    db.add(barrier)
    db.commit()
    db.refresh(barrier)
    return barrier

def list_barriers(db: Session, org_id: int) -> List[DimensionalBarrier]:
    return db.query(DimensionalBarrier).filter(DimensionalBarrier.org_id == org_id).all()

def breach(db: Session, org_id: int, barrier_id: int, breach_type: str = "interdimensional_incursion") -> DimensionalBreach:
    barrier = db.query(DimensionalBarrier).filter(DimensionalBarrier.id == barrier_id, DimensionalBarrier.org_id == org_id).first()
    if not barrier:
        raise ValueError("Barrier not found")
    b = DimensionalBreach(barrier_id=barrier_id, org_id=org_id, breach_type=breach_type, description=f"{breach_type} from {barrier.dimension_id} - interdimensional attacker", source_dimension="brane_7", severity="CRITICAL", status="contained")
    db.add(b)
    barrier.breach_attempts += 1
    barrier.integrity_score = max(0, barrier.integrity_score - 2)
    db.commit()
    db.refresh(b)
    reinf = BarrierReinforcement(barrier_id=barrier_id, org_id=org_id, reinforcement_type="exotic_matter_weave", strength_boost=10.0, config_json={"exotic_matter_density": "high"}, status="active")
    db.add(reinf)
    db.commit()
    return b

def serialize_barrier(b: DimensionalBarrier) -> Dict[str, Any]:
    return {"id": b.id, "name": b.name, "dimension_id": b.dimension_id, "barrier_strength": b.barrier_strength, "breach_attempts": b.breach_attempts, "integrity_score": b.integrity_score, "status": b.status}
def serialize_breach(br: DimensionalBreach) -> Dict[str, Any]:
    return {"id": br.id, "barrier_id": br.barrier_id, "breach_type": br.breach_type, "description": br.description, "source_dimension": br.source_dimension, "severity": br.severity, "status": br.status}
