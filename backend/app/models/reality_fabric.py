"""Phase 142: Reality Fabric Security - protecting physics constants, vacuum stability."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class RealityFabric(Base):
    __tablename__ = "reality_fabrics"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    dimension_count = Column(Integer, default=11)  # 11 dimensions M-theory
    constants_json = Column(JSON, default=dict)  # {c: 299792458, G: 6.674e-11, hbar, alpha, etc}
    integrity_score = Column(Float, default=100.0)
    vacuum_stability = Column(Float, default=99.99)  # false vacuum risk
    status = Column(String(20), default="stable")
    created_at = Column(DateTime(timezone=True), default=_now)

class RealityAnomaly(Base):
    __tablename__ = "reality_anomalies"
    id = Column(Integer, primary_key=True, index=True)
    fabric_id = Column(Integer, ForeignKey("reality_fabrics.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    anomaly_type = Column(String(100), default="constant_drift")  # constant_drift, vacuum_bubble, dimensional_tear, physics_exploit
    description = Column(Text, nullable=True)
    severity = Column(String(20), default="CRITICAL")  # physics-level
    affected_constants = Column(JSON, default=list)
    status = Column(String(20), default="detected")
    created_at = Column(DateTime(timezone=True), default=_now)

class FabricPatch(Base):
    __tablename__ = "fabric_patches"
    id = Column(Integer, primary_key=True, index=True)
    anomaly_id = Column(Integer, ForeignKey("reality_anomalies.id"), nullable=False)
    fabric_id = Column(Integer, ForeignKey("reality_fabrics.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    patch_type = Column(String(100), default="constant_lock")
    patch_json = Column(JSON, default=dict)
    effectiveness = Column(Float, default=99.9)
    status = Column(String(20), default="applied")
    created_at = Column(DateTime(timezone=True), default=_now)
