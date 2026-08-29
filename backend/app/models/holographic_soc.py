"""Phase 125: Holographic SOC - volumetric holographic display."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class HolographicDisplay(Base):
    __tablename__ = "holographic_displays"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    display_name = Column(String(300), nullable=False)
    display_type = Column(String(50), default="volumetric")  # volumetric, light_field, plasma
    resolution = Column(String(50), default="8K volumetric")
    size_inches = Column(Float, default=65.0)
    location = Column(String(200), default="SOC War Room")
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class Hologram(Base):
    __tablename__ = "holograms"
    id = Column(Integer, primary_key=True, index=True)
    display_id = Column(Integer, ForeignKey("holographic_displays.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    hologram_type = Column(String(50), default="threat_globe")  # threat_globe, network_graph, attack_path, actor
    content_json = Column(JSON, default=dict)  # 3D content
    position_json = Column(JSON, default=dict)  # x,y,z, rotation, scale
    is_interactive = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class HoloInteraction(Base):
    __tablename__ = "holo_interactions"
    id = Column(Integer, primary_key=True, index=True)
    hologram_id = Column(Integer, ForeignKey("holograms.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    interaction_type = Column(String(50), default="gesture")  # gesture, voice, gaze, touch
    action = Column(String(200), nullable=True)
    result_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
