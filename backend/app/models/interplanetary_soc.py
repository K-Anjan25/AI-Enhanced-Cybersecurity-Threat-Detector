"""Phase 121: Interplanetary SOC - space SOC, latency-tolerant."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class InterplanetaryNode(Base):
    __tablename__ = "interplanetary_nodes"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    node_name = Column(String(300), nullable=False)
    node_type = Column(String(50), default="satellite")  # satellite, ground_station, mars_rover, iss, lunar_gateway
    location = Column(String(100), default="LEO")  # LEO, GEO, Lunar, Mars
    latency_ms = Column(Float, default=120.0)  # light delay
    bandwidth_mbps = Column(Float, default=10.0)
    status = Column(String(20), default="online")
    created_at = Column(DateTime(timezone=True), default=_now)

class SpaceTelemetry(Base):
    __tablename__ = "space_telemetries"
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, ForeignKey("interplanetary_nodes.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    telemetry_type = Column(String(50), default="security")  # security, health, comms
    data_json = Column(JSON, default=dict)
    signal_strength = Column(Float, default=85.0)
    is_anomaly = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)

class DelayTolerantBundle(Base):
    __tablename__ = "delay_tolerant_bundles"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    source_node_id = Column(Integer, ForeignKey("interplanetary_nodes.id"), nullable=True)
    dest_node_id = Column(Integer, ForeignKey("interplanetary_nodes.id"), nullable=True)
    bundle_type = Column(String(50), default="alert")  # alert, intel, model_update
    payload_hash = Column(String(500), nullable=True)
    custody_transfer = Column(Boolean, default=True)
    status = Column(String(20), default="delivered")
    created_at = Column(DateTime(timezone=True), default=_now)
