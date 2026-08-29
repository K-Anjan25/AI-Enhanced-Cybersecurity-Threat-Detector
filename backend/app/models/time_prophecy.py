"""Phase 129: Time-Series Anomaly Prophecy - temporal causal inference."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class TemporalModel(Base):
    __tablename__ = "temporal_models"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    model_type = Column(String(50), default="prophet")  # prophet, lstm, transformer, causal
    time_granularity = Column(String(20), default="hourly")  # minutely, hourly, daily
    lookback_days = Column(Integer, default=90)
    forecast_horizon_days = Column(Integer, default=30)
    accuracy = Column(Float, default=0.0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class AnomalyProphecy(Base):
    __tablename__ = "anomaly_prophecies"
    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("temporal_models.id"), nullable=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    prophecy_type = Column(String(50), default="anomaly")  # anomaly, breach, outage
    predicted_at = Column(DateTime(timezone=True), nullable=False)
    probability = Column(Float, default=0.0)
    causal_factors = Column(JSON, default=list)  # causal inference
    explanation = Column(Text, nullable=True)
    status = Column(String(20), default="predicted")
    created_at = Column(DateTime(timezone=True), default=_now)

class CausalGraph(Base):
    __tablename__ = "causal_graphs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    nodes_json = Column(JSON, default=list)  # events
    edges_json = Column(JSON, default=list)  # causal edges with strength
    root_cause = Column(String(500), nullable=True)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
