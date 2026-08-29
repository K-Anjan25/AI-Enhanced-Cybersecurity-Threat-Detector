"""Phase 135: Self-Replicating Defense - von Neumann probes."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class ReplicatorFleet(Base):
    __tablename__ = "replicator_fleets"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    fleet_name = Column(String(300), nullable=False)
    replicator_type = Column(String(50), default="defense_probe")  # defense_probe, hunter_probe, healer_probe
    replication_rate = Column(Float, default=1.5)  # exponential factor
    max_replicas = Column(Integer, default=1000)
    current_count = Column(Integer, default=1)
    status = Column(String(20), default="replicating")
    created_at = Column(DateTime(timezone=True), default=_now)

class ReplicatorNode(Base):
    __tablename__ = "replicator_nodes"
    id = Column(Integer, primary_key=True, index=True)
    fleet_id = Column(Integer, ForeignKey("replicator_fleets.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("replicator_nodes.id"), nullable=True)
    generation = Column(Integer, default=0)
    location = Column(String(200), nullable=True)
    capabilities_json = Column(JSON, default=list)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class ReplicationLog(Base):
    __tablename__ = "replication_logs"
    id = Column(Integer, primary_key=True, index=True)
    fleet_id = Column(Integer, ForeignKey("replicator_fleets.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    parent_node_id = Column(Integer, ForeignKey("replicator_nodes.id"), nullable=True)
    child_node_id = Column(Integer, ForeignKey("replicator_nodes.id"), nullable=True)
    replication_time_seconds = Column(Float, default=0.0)
    resource_cost = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
