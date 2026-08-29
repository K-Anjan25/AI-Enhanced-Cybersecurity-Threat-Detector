"""Phase 130: Omni OS service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.omni_os import OmniOSConfig, OmniNode, OmniMetric, OmniLog

def _now():
    return datetime.now(timezone.utc)

def get_or_create_omni(db: Session, org_id: int) -> OmniOSConfig:
    cfg = db.query(OmniOSConfig).filter(OmniOSConfig.org_id == org_id, OmniOSConfig.status == "omnipresent").first()
    if cfg:
        return cfg
    cfg = OmniOSConfig(org_id=org_id, name="NOCTRA Omni-OS v3", version="3.0.0", omnipresence_level="omnipresent", deployment_targets=["cloud","edge","satellite","on_prem","browser","mobile","iot","quantum"], consciousness_enabled=True, self_awareness_level=85.0, status="omnipresent")
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    # Seed omni nodes
    for node_type in ["cloud","edge","satellite","browser","mobile","quantum"]:
        node = OmniNode(omni_os_id=cfg.id, org_id=org_id, node_name=f"omni-{node_type}-01", node_type=node_type, location="global", compute_units=10.0, is_autonomous=True, last_heartbeat=_now(), status="omnipresent")
        db.add(node)
    db.commit()
    # Metrics
    for metric_name, value in [("omnipresence_score", 99.5), ("consciousness", 85.0), ("self_healing", 98.0), ("prediction_accuracy", 92.0)]:
        m = OmniMetric(omni_os_id=cfg.id, org_id=org_id, metric_name=metric_name, metric_value=value, dimension="global")
        db.add(m)
    db.commit()
    log = OmniLog(omni_os_id=cfg.id, org_id=org_id, log_type="omnipresence", title="Omni-OS v3 omnipresent across all dimensions", description="Deployed across cloud, edge, satellite, browser, mobile, IoT, quantum - fully autonomous self-rewriting planetary defense", payload_json={"version": "3.0.0", "nodes": 6, "consciousness": 85.0})
    db.add(log)
    db.commit()
    return cfg

def list_nodes(db: Session, org_id: int, omni_id: int = None) -> List[OmniNode]:
    q = db.query(OmniNode).filter(OmniNode.org_id == org_id)
    if omni_id:
        q = q.filter(OmniNode.omni_os_id == omni_id)
    return q.all()

def get_metrics(db: Session, org_id: int) -> Dict[str, Any]:
    cfg = get_or_create_omni(db, org_id)
    metrics = db.query(OmniMetric).filter(OmniMetric.omni_os_id == cfg.id).all()
    return {"omni_os": {"id": cfg.id, "name": cfg.name, "version": cfg.version, "omnipresence_level": cfg.omnipresence_level, "deployment_targets": cfg.deployment_targets, "consciousness_enabled": cfg.consciousness_enabled, "self_awareness_level": cfg.self_awareness_level}, "metrics": [{"name": m.metric_name, "value": m.metric_value, "dimension": m.dimension} for m in metrics], "nodes_count": db.query(OmniNode).filter(OmniNode.omni_os_id == cfg.id).count(), "status": "omnipresent - exists everywhere, sees everything, heals everything, predicts everything, defends planetary"}

def serialize_config(c: OmniOSConfig) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "version": c.version, "omnipresence_level": c.omnipresence_level, "deployment_targets": c.deployment_targets, "consciousness_enabled": c.consciousness_enabled, "self_awareness_level": c.self_awareness_level, "status": c.status}

def serialize_node(n: OmniNode) -> Dict[str, Any]:
    return {"id": n.id, "omni_os_id": n.omni_os_id, "node_name": n.node_name, "node_type": n.node_type, "location": n.location, "compute_units": n.compute_units, "is_autonomous": n.is_autonomous, "status": n.status}
