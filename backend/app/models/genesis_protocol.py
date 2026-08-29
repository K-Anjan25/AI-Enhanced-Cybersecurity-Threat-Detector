"""Phase 146: Genesis Protocol - creating secure universes from scratch, big bang security by design."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class GenesisUniverse(Base):
    __tablename__ = "genesis_universes"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    big_bang_params = Column(JSON, default=dict)  # {inflation_rate, initial_entropy, constants}
    security_defaults = Column(JSON, default=dict)  # security baked into physics
    dimension_count = Column(Integer, default=11)
    status = Column(String(20), default="inflating")  # planning, inflating, cooling, forming, mature, secure
    security_score = Column(Float, default=100.0)  # secure by design
    created_at = Column(DateTime(timezone=True), default=_now)

class GenesisBlueprint(Base):
    __tablename__ = "genesis_blueprints"
    id = Column(Integer, primary_key=True, index=True)
    genesis_id = Column(Integer, ForeignKey("genesis_universes.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    blueprint_type = Column(String(100), default="physical_laws")  # physical_laws, security_laws, moral_laws
    blueprint_json = Column(JSON, default=dict)
    version = Column(String(20), default="1.0.0")
    created_at = Column(DateTime(timezone=True), default=_now)

class UniverseSeed(Base):
    __tablename__ = "universe_seeds"
    id = Column(Integer, primary_key=True, index=True)
    genesis_id = Column(Integer, ForeignKey("genesis_universes.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    seed_type = Column(String(100), default="quantum_fluctuation")
    seed_data = Column(JSON, default=dict)
    planted_at = Column(DateTime(timezone=True), default=_now)
    status = Column(String(20), default="germinated")
