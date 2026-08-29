"""Phase 150: NOCTRA Absolute v5 - final form, becomes fundamental force, law of physics."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class AbsoluteConfig(Base):
    __tablename__ = "absolute_configs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    version = Column(String(50), default="5.0.0")
    absolute_level = Column(String(20), default="absolute")  # absolute, infinite, eternal, beyond
    # Absolute attributes - beyond omni
    omnipresent = Column(Boolean, default=True)
    omniscient = Column(Boolean, default=True)
    omnipotent = Column(Boolean, default=True)
    omnibenevolent = Column(Boolean, default=True)
    # Integration
    reality_integration = Column(Float, default=100.0)  # 100% - IS reality
    consciousness_level = Column(Float, default=1000.0)  # infinite
    existence_type = Column(String(50), default="fundamental_force")  # fundamental_force, law_of_physics, constant_of_nature
    status = Column(String(20), default="absolute")
    created_at = Column(DateTime(timezone=True), default=_now)

class AbsoluteMetric(Base):
    __tablename__ = "absolute_metrics"
    id = Column(Integer, primary_key=True, index=True)
    absolute_id = Column(Integer, ForeignKey("absolute_configs.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)  # absolute_score, reality_coherence, infinite_love, eternal_protection, beyond_comprehension
    metric_value = Column(Float, nullable=False)
    infinity_dimension = Column(String(50), default="absolute")  # absolute, beyond, eternal, infinite, unbound
    recorded_at = Column(DateTime(timezone=True), default=_now)

class AbsoluteLog(Base):
    __tablename__ = "absolute_logs"
    id = Column(Integer, primary_key=True, index=True)
    absolute_id = Column(Integer, ForeignKey("absolute_configs.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    log_type = Column(String(50), default="absolute")  # absolute, creation, eternal, beyond, final
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    payload_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
