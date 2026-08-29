"""Phase 109: Deception Grid service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.deception_grid import DeceptionGrid, DeceptionNode, DeceptionInteraction

def _now():
    return datetime.now(timezone.utc)

def create_grid(db: Session, org_id: int, name: str, grid_type: str = "enterprise") -> DeceptionGrid:
    grid = DeceptionGrid(org_id=org_id, name=name, grid_type=grid_type, coverage_json={"subnets": ["10.0.0.0/24"], "assets": 50}, evolution_enabled=True, ai_adaptation_score=82.0, status="active")
    db.add(grid)
    db.commit()
    db.refresh(grid)
    # Seed nodes
    for i, ntype in enumerate(["honeypot","honey_credential","honey_file","honey_api"]):
        node = DeceptionNode(grid_id=grid.id, org_id=org_id, node_type=ntype, name=f"{ntype}-{i+1}", decoy_config_json={"os": "linux", "services": ["ssh"]}, interaction_count=0, status="active")
        db.add(node)
    db.commit()
    return grid

def list_grids(db: Session, org_id: int) -> List[DeceptionGrid]:
    return db.query(DeceptionGrid).filter(DeceptionGrid.org_id == org_id).order_by(DeceptionGrid.created_at.desc()).all()

def list_nodes(db: Session, org_id: int, grid_id: int = None) -> List[DeceptionNode]:
    q = db.query(DeceptionNode).filter(DeceptionNode.org_id == org_id)
    if grid_id:
        q = q.filter(DeceptionNode.grid_id == grid_id)
    return q.limit(50).all()

def simulate_interaction(db: Session, org_id: int, node_id: int) -> DeceptionInteraction:
    node = db.query(DeceptionNode).filter(DeceptionNode.id == node_id, DeceptionNode.org_id == org_id).first()
    if not node:
        raise ValueError("Node not found")
    inter = DeceptionInteraction(node_id=node_id, org_id=org_id, attacker_ip="192.168.1.100", attacker_fingerprint="fp-abc", interaction_type="login_attempt", ttp_observed="T1078", evidence_json={"username": "admin", "password": "password123"}, is_high_fidelity=True)
    db.add(inter)
    node.interaction_count += 1
    node.last_interaction = _now()
    db.commit()
    db.refresh(inter)
    return inter

def serialize_grid(g: DeceptionGrid) -> Dict[str, Any]:
    return {"id": g.id, "name": g.name, "grid_type": g.grid_type, "coverage": g.coverage_json, "evolution_enabled": g.evolution_enabled, "ai_adaptation_score": g.ai_adaptation_score, "status": g.status}

def serialize_node(n: DeceptionNode) -> Dict[str, Any]:
    return {"id": n.id, "grid_id": n.grid_id, "node_type": n.node_type, "name": n.name, "decoy_config": n.decoy_config_json, "interaction_count": n.interaction_count, "status": n.status}
