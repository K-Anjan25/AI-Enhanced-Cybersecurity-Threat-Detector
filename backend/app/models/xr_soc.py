"""Phase 108: XR SOC - VR/AR SOC visualization."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class XRSOCSession(Base):
    __tablename__ = "xr_soc_sessions"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_name = Column(String(300), nullable=False)
    xr_type = Column(String(20), default="vr")  # vr, ar, mr
    device = Column(String(100), default="meta_quest_3")
    environment_json = Column(JSON, default=dict)  # scene config
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class SpatialEntity(Base):
    __tablename__ = "spatial_entities"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("xr_soc_sessions.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    entity_type = Column(String(50), default="alert")  # alert, asset, threat_actor, network
    position_json = Column(JSON, default=dict)  # x,y,z
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)

class XRAlert(Base):
    __tablename__ = "xr_alerts"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("xr_soc_sessions.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    alert_id = Column(Integer, ForeignKey("security_alerts.id"), nullable=True)
    spatial_position = Column(JSON, default=dict)
    visual_intensity = Column(Float, default=1.0)
    is_acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
