"""Phase 117: Global Threat Intel Mesh - decentralized p2p."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class MeshNode(Base):
    __tablename__ = "mesh_nodes"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    node_id = Column(String(100), nullable=False)  # peer ID
    node_name = Column(String(300), nullable=False)
    region = Column(String(50), default="us-east-1")
    ip_address = Column(String(100), nullable=True)
    trust_score = Column(Float, default=80.0)
    reputation = Column(Float, default=85.0)
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime(timezone=True), default=_now)
    created_at = Column(DateTime(timezone=True), default=_now)

class MeshSync(Base):
    __tablename__ = "mesh_syncs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    node_id = Column(Integer, ForeignKey("mesh_nodes.id"), nullable=False)
    sync_type = Column(String(50), default="intel")  # intel, reputation, model
    records_synced = Column(Integer, default=0)
    sync_status = Column(String(20), default="completed")
    latency_ms = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)

class MeshIntel(Base):
    __tablename__ = "mesh_intels"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    mesh_node_id = Column(Integer, ForeignKey("mesh_nodes.id"), nullable=True)
    intel_type = Column(String(50), default="ioc")  # ioc, ttp, actor, vulnerability
    stix_bundle = Column(JSON, default=dict)
    confidence = Column(Float, default=0.0)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
