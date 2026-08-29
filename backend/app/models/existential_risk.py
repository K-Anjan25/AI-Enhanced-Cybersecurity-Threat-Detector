"""Phase 139: Existential Risk Monitor - Bostrom-style x-risk."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class ExistentialRisk(Base):
    __tablename__ = "existential_risks"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    risk_name = Column(String(500), nullable=False)
    risk_category = Column(String(50), default="ai")  # ai, bio, nano, cyber, climate, asteroid, unknown
    probability = Column(Float, default=0.001)  # annual probability
    impact = Column(String(20), default="extinction")  # extinction, collapse, stagnation
    timeline_years = Column(Integer, default=50)  # years until potential
    mitigation_readiness = Column(Float, default=50.0)
    status = Column(String(20), default="monitoring")
    created_at = Column(DateTime(timezone=True), default=_now)

class XRiskMitigation(Base):
    __tablename__ = "x_risk_mitigations"
    id = Column(Integer, primary_key=True, index=True)
    risk_id = Column(Integer, ForeignKey("existential_risks.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    mitigation_name = Column(String(500), nullable=False)
    mitigation_type = Column(String(50), default="technical")  # technical, governance, coordination
    effectiveness = Column(Float, default=0.0)
    cost = Column(Float, default=0.0)
    status = Column(String(20), default="proposed")
    created_at = Column(DateTime(timezone=True), default=_now)

class XRiskScenario(Base):
    __tablename__ = "x_risk_scenarios"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    scenario_name = Column(String(500), nullable=False)
    risks_json = Column(JSON, default=list)  # multiple x-risks interacting
    cascade_probability = Column(Float, default=0.0)
    simulation_result = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
