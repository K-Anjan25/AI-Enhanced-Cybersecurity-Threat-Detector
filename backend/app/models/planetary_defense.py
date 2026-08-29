"""Phase 128: Planetary Defense Grid - critical infra integration."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class PlanetaryDefenseGrid(Base):
    __tablename__ = "planetary_defense_grids"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    grid_type = Column(String(50), default="global")  # global, continental, national, city
    coverage_json = Column(JSON, default=dict)  # {power_grid, water, telecom, finance}
    threat_level = Column(String(20), default="elevated")  # low, guarded, elevated, high, severe
    defense_readiness = Column(Float, default=85.0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class CriticalInfraNode(Base):
    __tablename__ = "critical_infra_nodes"
    id = Column(Integer, primary_key=True, index=True)
    grid_id = Column(Integer, ForeignKey("planetary_defense_grids.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    node_name = Column(String(300), nullable=False)
    infra_type = Column(String(50), default="power_grid")  # power_grid, water, telecom, transport, finance, healthcare
    location = Column(String(200), nullable=True)
    criticality = Column(String(20), default="critical")
    security_posture = Column(Float, default=75.0)
    status = Column(String(20), default="operational")
    created_at = Column(DateTime(timezone=True), default=_now)

class PlanetaryThreat(Base):
    __tablename__ = "planetary_threats"
    id = Column(Integer, primary_key=True, index=True)
    grid_id = Column(Integer, ForeignKey("planetary_defense_grids.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    threat_name = Column(String(500), nullable=False)
    threat_type = Column(String(50), default="nation_state")  # nation_state, ransomware, supply_chain, solar_flare
    affected_infra = Column(JSON, default=list)
    impact_score = Column(Float, default=0.0)
    mitigation_json = Column(JSON, default=dict)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)
