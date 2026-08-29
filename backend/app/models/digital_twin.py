"""Phase 104: Cyber Digital Twin - resilience testing."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class DigitalTwin(Base):
    __tablename__ = "digital_twins"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    twin_type = Column(String(50), default="infrastructure")  # infrastructure, network, identity, application
    source_config_json = Column(JSON, default=dict)  # how twin is built from real infra
    fidelity_score = Column(Float, default=85.0)  # how accurate vs real
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class TwinSimulation(Base):
    __tablename__ = "twin_simulations"
    id = Column(Integer, primary_key=True, index=True)
    twin_id = Column(Integer, ForeignKey("digital_twins.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    scenario = Column(String(100), default="ransomware")  # ransomware, ddos, insider, supply_chain
    simulation_config = Column(JSON, default=dict)
    result_json = Column(JSON, default=dict)  # blast radius, time to recover, etc
    resilience_impact = Column(Float, default=0.0)
    status = Column(String(20), default="completed")
    created_at = Column(DateTime(timezone=True), default=_now)

class ResilienceScore(Base):
    __tablename__ = "resilience_scores"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    twin_id = Column(Integer, ForeignKey("digital_twins.id"), nullable=True)
    overall_score = Column(Float, default=0.0)
    breakdown_json = Column(JSON, default=dict)  # {recoverability, redundancy, segmentation}
    recommendations = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=_now)
