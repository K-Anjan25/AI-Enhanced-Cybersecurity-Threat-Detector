"""Phase 136: Temporal Defense service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.temporal_defense import Timeline, TemporalAnomaly, TimelineProtection

def _now():
    return datetime.now(timezone.utc)

def create_timeline(db: Session, org_id: int, name: str, timeline_type: str = "primary") -> Timeline:
    tl = Timeline(org_id=org_id, name=name, timeline_type=timeline_type, start_time=_now(), integrity_score=100.0, paradox_count=0, status="protected")
    db.add(tl)
    db.commit()
    db.refresh(tl)
    # Protection
    prot = TimelineProtection(timeline_id=tl.id, org_id=org_id, protection_type="causality_lock", config_json={"lock_strength": "max", "paradox_buffer": True}, effectiveness=98.5, status="active")
    db.add(prot)
    db.commit()
    return tl

def list_timelines(db: Session, org_id: int) -> List[Timeline]:
    return db.query(Timeline).filter(Timeline.org_id == org_id).all()

def detect_anomaly(db: Session, org_id: int, timeline_id: int, anomaly_type: str = "retrocausal_attack") -> TemporalAnomaly:
    tl = db.query(Timeline).filter(Timeline.id == timeline_id, Timeline.org_id == org_id).first()
    if not tl:
        raise ValueError("Timeline not found")
    anomaly = TemporalAnomaly(timeline_id=timeline_id, org_id=org_id, anomaly_type=anomaly_type, description=f"{anomaly_type} detected - attacker attempting to alter past logs", temporal_coordinates={"t": _now().isoformat(), "causality_violation": True, "affected_events": ["log_deletion"]}, severity="CRITICAL", status="detected")
    db.add(anomaly)
    tl.paradox_count += 1
    tl.integrity_score = max(0, tl.integrity_score - 5)
    db.commit()
    db.refresh(anomaly)
    return anomaly

def serialize_timeline(t: Timeline) -> Dict[str, Any]:
    return {"id": t.id, "name": t.name, "timeline_type": t.timeline_type, "integrity_score": t.integrity_score, "paradox_count": t.paradox_count, "status": t.status}

def serialize_anomaly(a: TemporalAnomaly) -> Dict[str, Any]:
    return {"id": a.id, "timeline_id": a.timeline_id, "anomaly_type": a.anomaly_type, "description": a.description, "temporal_coordinates": a.temporal_coordinates, "severity": a.severity, "status": a.status}
