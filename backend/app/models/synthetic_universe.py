"""Phase 124: Synthetic Data Universe - synthetic SOC data generation."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class SyntheticUniverse(Base):
    __tablename__ = "synthetic_universes"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    universe_type = Column(String(50), default="soc")  # soc, network, identity, cloud
    scale = Column(String(20), default="large")  # small 1k, medium 10k, large 100k, planetary 1M
    realism_score = Column(Float, default=92.0)
    privacy_preserved = Column(Boolean, default=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class SyntheticDataset(Base):
    __tablename__ = "synthetic_datasets"
    id = Column(Integer, primary_key=True, index=True)
    universe_id = Column(Integer, ForeignKey("synthetic_universes.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    dataset_name = Column(String(300), nullable=False)
    record_count = Column(Integer, default=10000)
    data_type = Column(String(50), default="alerts")  # alerts, logs, flows, incidents
    schema_json = Column(JSON, default=dict)
    generation_model = Column(String(100), default="gan+llm")
    quality_metrics_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)

class SyntheticScenario(Base):
    __tablename__ = "synthetic_scenarios"
    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("synthetic_datasets.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    scenario_name = Column(String(300), nullable=False)
    attack_chain = Column(JSON, default=list)
    difficulty = Column(String(20), default="hard")
    created_at = Column(DateTime(timezone=True), default=_now)
