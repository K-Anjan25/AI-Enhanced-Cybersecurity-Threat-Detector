"""Phase 74: HA Redis Event Bus + multi-region."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class EventBusMessage(Base):
    __tablename__ = "event_bus_messages"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=True, index=True)
    channel = Column(String(100), nullable=False)  # alerts.raised, cases.created, soar.executed
    event_type = Column(String(100), nullable=False)
    payload_json = Column(JSON, default=dict)
    region = Column(String(50), default="us-east-1")
    is_persisted = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class HANode(Base):
    __tablename__ = "ha_nodes"
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String(100), nullable=False, unique=True)
    region = Column(String(50), default="us-east-1")
    role = Column(String(20), default="primary")  # primary, replica, standby
    status = Column(String(20), default="active")  # active, inactive, degraded
    last_heartbeat_at = Column(DateTime(timezone=True), default=_now)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
