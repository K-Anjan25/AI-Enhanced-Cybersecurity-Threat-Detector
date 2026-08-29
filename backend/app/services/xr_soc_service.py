"""Phase 108: XR SOC service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.xr_soc import XRSOCSession, SpatialEntity, XRAlert
from app.models import SecurityAlert

def _now():
    return datetime.now(timezone.utc)

def create_session(db: Session, org_id: int, user_id: int, name: str, xr_type: str = "vr") -> XRSOCSession:
    sess = XRSOCSession(org_id=org_id, user_id=user_id, session_name=name, xr_type=xr_type, device="meta_quest_3", environment_json={"scene": "soc_war_room", "assets": 100}, status="active")
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess

def list_sessions(db: Session, org_id: int) -> List[XRSOCSession]:
    return db.query(XRSOCSession).filter(XRSOCSession.org_id == org_id).order_by(XRSOCSession.created_at.desc()).all()

def spawn_spatial_entities(db: Session, org_id: int, session_id: int) -> List[SpatialEntity]:
    alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).limit(10).all()
    entities = []
    for idx, alert in enumerate(alerts):
        ent = SpatialEntity(session_id=session_id, org_id=org_id, entity_type="alert", position_json={"x": idx*2, "y": 1.5, "z": -idx}, metadata_json={"alert_id": alert.id, "severity": getattr(alert, 'severity', 'HIGH')})
        db.add(ent)
        entities.append(ent)
    db.commit()
    for e in entities:
        db.refresh(e)
    return entities

def serialize_session(s: XRSOCSession) -> Dict[str, Any]:
    return {"id": s.id, "session_name": s.session_name, "xr_type": s.xr_type, "device": s.device, "environment": s.environment_json, "status": s.status, "created_at": s.created_at.isoformat() if s.created_at else None}
