"""Phase 135: Self-Replicating Defense service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.self_replicating import ReplicatorFleet, ReplicatorNode, ReplicationLog

def _now():
    return datetime.now(timezone.utc)

def create_fleet(db: Session, org_id: int, name: str, replicator_type: str = "defense_probe") -> ReplicatorFleet:
    fleet = ReplicatorFleet(org_id=org_id, fleet_name=name, replicator_type=replicator_type, replication_rate=1.8, max_replicas=1000, current_count=1, status="replicating")
    db.add(fleet)
    db.commit()
    db.refresh(fleet)
    root = ReplicatorNode(fleet_id=fleet.id, org_id=org_id, parent_id=None, generation=0, location="us-east-1", capabilities_json=["defense","healing","hunting"], status="active")
    db.add(root)
    db.commit()
    db.refresh(root)
    return fleet

def list_fleets(db: Session, org_id: int) -> List[ReplicatorFleet]:
    return db.query(ReplicatorFleet).filter(ReplicatorFleet.org_id == org_id).all()

def replicate(db: Session, org_id: int, fleet_id: int) -> ReplicatorFleet:
    fleet = db.query(ReplicatorFleet).filter(ReplicatorFleet.id == fleet_id, ReplicatorFleet.org_id == org_id).first()
    if not fleet:
        raise ValueError("Fleet not found")
    # Exponential replication
    parent = db.query(ReplicatorNode).filter(ReplicatorNode.fleet_id == fleet_id).order_by(ReplicatorNode.generation.desc()).first()
    if not parent:
        raise ValueError("No parent node")
    if fleet.current_count >= fleet.max_replicas:
        fleet.status = "max_reached"
        db.commit()
        return fleet
    # Create 2 children (von Neumann)
    for i in range(2):
        child = ReplicatorNode(fleet_id=fleet_id, org_id=org_id, parent_id=parent.id, generation=parent.generation+1, location=f"region-{fleet.current_count+i}", capabilities_json=parent.capabilities_json, status="active")
        db.add(child)
        db.flush()
        log = ReplicationLog(fleet_id=fleet_id, org_id=org_id, parent_node_id=parent.id, child_node_id=child.id, replication_time_seconds=2.5, resource_cost=10.0)
        db.add(log)
    fleet.current_count += 2
    db.commit()
    db.refresh(fleet)
    return fleet

def serialize_fleet(f: ReplicatorFleet) -> Dict[str, Any]:
    return {"id": f.id, "fleet_name": f.fleet_name, "replicator_type": f.replicator_type, "replication_rate": f.replication_rate, "max_replicas": f.max_replicas, "current_count": f.current_count, "status": f.status}
