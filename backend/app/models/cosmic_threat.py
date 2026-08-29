"""Phase 148: Cosmic Threat Intel - vacuum decay, gamma bursts, heat death, big rip."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class CosmicThreat(Base):
    __tablename__ = "cosmic_threats"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    threat_type = Column(String(100), default="vacuum_decay")  # vacuum_decay, gamma_ray_burst, false_vacuum, heat_death, big_rip, big_crunch, big_freeze, grey_goo_cosmic, strangelet
    probability = Column(Float, default=0.0001)
    impact = Column(String(50), default="omniversal_extinction")  # planetary, stellar, galactic, universal, multiversal, omniversal_extinction
    timeline_years = Column(Integer, default=1000000)  # years until possible
    distance_light_years = Column(Float, default=1000.0)
    mitigation_readiness = Column(Float, default=10.0)
    status = Column(String(20), default="monitoring")
    created_at = Column(DateTime(timezone=True), default=_now)

class CosmicMitigation(Base):
    __tablename__ = "cosmic_mitigations"
    id = Column(Integer, primary_key=True, index=True)
    threat_id = Column(Integer, ForeignKey("cosmic_threats.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    mitigation_name = Column(String(300), nullable=False)
    mitigation_type = Column(String(100), default="vacuum_stabilizer")  # vacuum_stabilizer, dyson_swarm_shield, entropy_reversal, reality_anchor
    effectiveness = Column(Float, default=50.0)
    cost_energy = Column(Float, default=1e30)  # joules
    status = Column(String(20), default="theoretical")
    created_at = Column(DateTime(timezone=True), default=_now)

class CosmicSimulation(Base):
    __tablename__ = "cosmic_simulations"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    simulation_name = Column(String(300), nullable=False)
    threats_json = Column(JSON, default=list)  # list of threat ids
    simulation_result = Column(JSON, default=dict)  # outcome
    survival_probability = Column(Float, default=0.99)
    created_at = Column(DateTime(timezone=True), default=_now)
