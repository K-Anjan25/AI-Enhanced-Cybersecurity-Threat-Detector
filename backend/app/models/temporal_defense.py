"""Phase 136: Temporal Defense - timeline protection, retrocausality."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class Timeline(Base):
    __tablename__ = "timelines"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    timeline_type = Column(String(50), default="primary")  # primary, alternate, protected
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    integrity_score = Column(Float, default=100.0)
    paradox_count = Column(Integer, default=0)
    status = Column(String(20), default="protected")
    created_at = Column(DateTime(timezone=True), default=_now)

class TemporalAnomaly(Base):
    __tablename__ = "temporal_anomalies"
    id = Column(Integer, primary_key=True, index=True)
    timeline_id = Column(Integer, ForeignKey("timelines.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    anomaly_type = Column(String(50), default="retrocausal_attack")  # retrocausal_attack, time_loop, timeline_branch, bootstrap_paradox
    description = Column(Text, nullable=True)
    temporal_coordinates = Column(JSON, default=dict)  # {t: timestamp, causality_violation: true}
    severity = Column(String(20), default="CRITICAL")
    status = Column(String(20), default="detected")
    created_at = Column(DateTime(timezone=True), default=_now)

class TimelineProtection(Base):
    __tablename__ = "timeline_protections"
    id = Column(Integer, primary_key=True, index=True)
    timeline_id = Column(Integer, ForeignKey("timelines.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    protection_type = Column(String(50), default="causality_lock")  # causality_lock, paradox_buffer, retro_shield
    config_json = Column(JSON, default=dict)
    effectiveness = Column(Float, default=95.0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)
