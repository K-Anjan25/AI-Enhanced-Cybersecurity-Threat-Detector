"""Phase 145: Void Defense - dark universe, void entities, dark matter threats."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class VoidSector(Base):
    __tablename__ = "void_sectors"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    sector_coordinates = Column(JSON, default=dict)  # dark universe coords
    void_energy = Column(Float, default=75.0)  # vacuum energy density
    dark_matter_density = Column(Float, default=0.27)  # 27% universe
    threat_level = Column(String(20), default="HIGH")
    status = Column(String(20), default="monitored")
    created_at = Column(DateTime(timezone=True), default=_now)

class VoidEntity(Base):
    __tablename__ = "void_entities"
    id = Column(Integer, primary_key=True, index=True)
    sector_id = Column(Integer, ForeignKey("void_sectors.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    entity_type = Column(String(100), default="void_predator")  # void_predator, dark_tide, entropy_beast, null_wraith
    description = Column(Text, nullable=True)
    power_level = Column(Float, default=85.0)
    status = Column(String(20), default="contained")
    created_at = Column(DateTime(timezone=True), default=_now)

class VoidShield(Base):
    __tablename__ = "void_shields"
    id = Column(Integer, primary_key=True, index=True)
    sector_id = Column(Integer, ForeignKey("void_sectors.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    shield_type = Column(String(100), default="dark_energy_barrier")
    strength = Column(Float, default=99.0)
    config_json = Column(JSON, default=dict)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)
