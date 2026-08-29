"""Phase 130: NOCTRA Omni-OS - omnipresent OS that exists everywhere."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class OmniOSConfig(Base):
    __tablename__ = "omni_os_configs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    version = Column(String(50), default="3.0.0")
    omnipresence_level = Column(String(20), default="planetary")  # local, global, planetary, interplanetary, omnipresent
    deployment_targets = Column(JSON, default=list)  # ["cloud","edge","satellite","on_prem","browser","mobile"]
    consciousness_enabled = Column(Boolean, default=True)
    self_awareness_level = Column(Float, default=75.0)
    status = Column(String(20), default="omnipresent")
    created_at = Column(DateTime(timezone=True), default=_now)

class OmniNode(Base):
    __tablename__ = "omni_nodes"
    id = Column(Integer, primary_key=True, index=True)
    omni_os_id = Column(Integer, ForeignKey("omni_os_configs.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    node_name = Column(String(300), nullable=False)
    node_type = Column(String(50), default="edge")  # cloud, edge, satellite, browser, mobile, iot, quantum
    location = Column(String(200), nullable=True)
    compute_units = Column(Float, default=1.0)
    is_autonomous = Column(Boolean, default=True)
    last_heartbeat = Column(DateTime(timezone=True), default=_now)
    status = Column(String(20), default="omnipresent")
    created_at = Column(DateTime(timezone=True), default=_now)

class OmniMetric(Base):
    __tablename__ = "omni_metrics"
    id = Column(Integer, primary_key=True, index=True)
    omni_os_id = Column(Integer, ForeignKey("omni_os_configs.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)  # omnipresence_score, consciousness, self_healing, prediction_accuracy
    metric_value = Column(Float, nullable=False)
    dimension = Column(String(50), default="global")  # local, global, planetary, temporal
    recorded_at = Column(DateTime(timezone=True), default=_now)

class OmniLog(Base):
    __tablename__ = "omni_logs"
    id = Column(Integer, primary_key=True, index=True)
    omni_os_id = Column(Integer, ForeignKey("omni_os_configs.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    log_type = Column(String(50), default="omnipresence")  # omnipresence, evolution, prophecy, defense
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    payload_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
