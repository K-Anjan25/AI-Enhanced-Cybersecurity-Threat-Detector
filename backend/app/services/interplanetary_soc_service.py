"""Phase 121: Interplanetary SOC service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.interplanetary_soc import InterplanetaryNode, SpaceTelemetry, DelayTolerantBundle
import hashlib

def _now():
    return datetime.now(timezone.utc)

def create_node(db: Session, org_id: int, name: str, node_type: str = "satellite", location: str = "LEO") -> InterplanetaryNode:
    latency_map = {"LEO": 20, "GEO": 120, "Lunar": 1300, "Mars": 720000}
    node = InterplanetaryNode(org_id=org_id, node_name=name, node_type=node_type, location=location, latency_ms=latency_map.get(location, 120), bandwidth_mbps=10.0, status="online")
    db.add(node)
    db.commit()
    db.refresh(node)
    return node

def list_nodes(db: Session, org_id: int) -> List[InterplanetaryNode]:
    return db.query(InterplanetaryNode).filter(InterplanetaryNode.org_id == org_id).all()

def ingest_telemetry(db: Session, org_id: int, node_id: int, data: Dict[str, Any]) -> SpaceTelemetry:
    node = db.query(InterplanetaryNode).filter(InterplanetaryNode.id == node_id, InterplanetaryNode.org_id == org_id).first()
    if not node:
        raise ValueError("Node not found")
    tele = SpaceTelemetry(node_id=node_id, org_id=org_id, telemetry_type="security", data_json=data, signal_strength=88.0, is_anomaly=data.get("is_anomaly", False))
    db.add(tele)
    db.commit()
    db.refresh(tele)
    # Create DTN bundle if anomaly
    if tele.is_anomaly:
        payload_hash = hashlib.sha256(str(data).encode()).hexdigest()
        bundle = DelayTolerantBundle(org_id=org_id, source_node_id=node_id, bundle_type="alert", payload_hash=payload_hash, custody_transfer=True, status="delivered")
        db.add(bundle)
        db.commit()
    return tele

def serialize_node(n: InterplanetaryNode) -> Dict[str, Any]:
    return {"id": n.id, "node_name": n.node_name, "node_type": n.node_type, "location": n.location, "latency_ms": n.latency_ms, "bandwidth_mbps": n.bandwidth_mbps, "status": n.status}
