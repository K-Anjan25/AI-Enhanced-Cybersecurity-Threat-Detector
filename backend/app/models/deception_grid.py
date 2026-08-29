"""Phase 109: Deception Grid v2 - autonomous evolving deception."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class DeceptionGrid(Base):
    __tablename__ = "deception_grids"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    grid_type = Column(String(50), default="enterprise")  # enterprise, cloud, ot, identity
    coverage_json = Column(JSON, default=dict)  # subnets, assets covered
    evolution_enabled = Column(Boolean, default=True)
    ai_adaptation_score = Column(Float, default=75.0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class DeceptionNode(Base):
    __tablename__ = "deception_nodes"
    id = Column(Integer, primary_key=True, index=True)
    grid_id = Column(Integer, ForeignKey("deception_grids.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    node_type = Column(String(50), default="honeypot")  # honeypot, honey_credential, honey_file, honey_api
    name = Column(String(300), nullable=False)
    decoy_config_json = Column(JSON, default=dict)
    interaction_count = Column(Integer, default=0)
    last_interaction = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class DeceptionInteraction(Base):
    __tablename__ = "deception_interactions"
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, ForeignKey("deception_nodes.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    attacker_ip = Column(String(100), nullable=True)
    attacker_fingerprint = Column(String(500), nullable=True)
    interaction_type = Column(String(50), default="probe")  # probe, login_attempt, exfil, lateral
    ttp_observed = Column(String(50), nullable=True)
    evidence_json = Column(JSON, default=dict)
    is_high_fidelity = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
