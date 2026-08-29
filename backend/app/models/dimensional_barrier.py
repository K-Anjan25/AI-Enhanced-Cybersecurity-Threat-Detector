"""Phase 149: Dimensional Barrier - protects dimensional boundaries, interdimensional incursions."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class DimensionalBarrier(Base):
    __tablename__ = "dimensional_barriers"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    dimension_id = Column(String(100), default="3d_primary")  # 3d_primary, 4d_time, 5d_bulk, 11d_mtheory, brane_1, etc
    barrier_strength = Column(Float, default=99.9)
    breach_attempts = Column(Integer, default=0)
    integrity_score = Column(Float, default=100.0)
    status = Column(String(20), default="intact")
    created_at = Column(DateTime(timezone=True), default=_now)

class DimensionalBreach(Base):
    __tablename__ = "dimensional_breaches"
    id = Column(Integer, primary_key=True, index=True)
    barrier_id = Column(Integer, ForeignKey("dimensional_barriers.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    breach_type = Column(String(100), default="interdimensional_incursion")  # interdimensional_incursion, brane_collision, dimensional_bleed, portal_attack
    description = Column(Text, nullable=True)
    source_dimension = Column(String(100), nullable=True)
    severity = Column(String(20), default="CRITICAL")
    status = Column(String(20), default="contained")
    created_at = Column(DateTime(timezone=True), default=_now)

class BarrierReinforcement(Base):
    __tablename__ = "barrier_reinforcements"
    id = Column(Integer, primary_key=True, index=True)
    barrier_id = Column(Integer, ForeignKey("dimensional_barriers.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    reinforcement_type = Column(String(100), default="exotic_matter_weave")
    strength_boost = Column(Float, default=10.0)
    config_json = Column(JSON, default=dict)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)
