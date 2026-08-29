"""Phase 102: Predictive SOC - breach prediction, MTTD forecast."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class PredictionModel(Base):
    __tablename__ = "prediction_models"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    model_type = Column(String(50), default="breach_likelihood")  # breach_likelihood, mttd_forecast, actor_next_move
    features_json = Column(JSON, default=list)
    accuracy = Column(Float, default=0.0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class ThreatForecast(Base):
    __tablename__ = "threat_forecasts"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    model_id = Column(Integer, ForeignKey("prediction_models.id"), nullable=True)
    forecast_type = Column(String(50), default="breach")  # breach, ransomware, data_exfil
    predicted_probability = Column(Float, default=0.0)
    predicted_timeframe = Column(String(50), default="7d")  # 24h, 7d, 30d
    contributing_factors = Column(JSON, default=list)
    confidence = Column(Float, default=0.0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class RiskPrediction(Base):
    __tablename__ = "risk_predictions"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    predicted_risk_score = Column(Float, default=0.0)
    current_risk_score = Column(Float, default=0.0)
    trend = Column(String(20), default="increasing")  # increasing, stable, decreasing
    explanation_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
