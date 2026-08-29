"""Phase 143: Chrono-Loop service."""
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.chrono_loop import TimeLoop, LoopIteration, ChronoDefense

def _now():
    return datetime.now(timezone.utc)

def create_loop(db: Session, org_id: int, name: str, loop_type: str = "closed_timelike") -> TimeLoop:
    loop = TimeLoop(org_id=org_id, name=name, loop_type=loop_type, start_time=_now(), end_time=_now(), iterations=1, max_iterations=1000, paradox_risk=0.1, status="contained")
    db.add(loop)
    db.commit()
    db.refresh(loop)
    defense = ChronoDefense(loop_id=loop.id, org_id=org_id, defense_type="causality_anchor", config_json={"anchor_strength": "max", "paradox_buffer": True}, effectiveness=99.5, status="active")
    db.add(defense)
    db.commit()
    return loop

def list_loops(db: Session, org_id: int) -> List[TimeLoop]:
    return db.query(TimeLoop).filter(TimeLoop.org_id == org_id).all()

def iterate_loop(db: Session, org_id: int, loop_id: int) -> LoopIteration:
    loop = db.query(TimeLoop).filter(TimeLoop.id == loop_id, TimeLoop.org_id == org_id).first()
    if not loop:
        raise ValueError("Loop not found")
    loop.iterations += 1
    loop.paradox_risk = min(1.0, loop.paradox_risk + 0.05)
    it = LoopIteration(loop_id=loop_id, org_id=org_id, iteration_number=loop.iterations, timeline_delta={"changed": f"iteration {loop.iterations} attacker tries bootstrap paradox", "paradox_type": "bootstrap"}, paradox_detected=loop.paradox_risk > 0.5)
    db.add(it)
    db.commit()
    db.refresh(it)
    return it

def serialize_loop(l: TimeLoop) -> Dict[str, Any]:
    return {"id": l.id, "name": l.name, "loop_type": l.loop_type, "iterations": l.iterations, "max_iterations": l.max_iterations, "paradox_risk": l.paradox_risk, "status": l.status}
