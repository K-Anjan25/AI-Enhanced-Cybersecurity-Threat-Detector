"""Phase 102: Predictive SOC service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.predictive_soc import PredictionModel, ThreatForecast, RiskPrediction
from app.models import SecurityAlert

def _now():
    return datetime.now(timezone.utc)

def create_model(db: Session, org_id: int, name: str, model_type: str = "breach_likelihood") -> PredictionModel:
    m = PredictionModel(org_id=org_id, name=name, model_type=model_type, features_json=["alert_volume","failed_logins","privilege_escalations"], accuracy=0.87, status="active")
    db.add(m)
    db.commit()
    db.refresh(m)
    return m

def list_models(db: Session, org_id: int) -> List[PredictionModel]:
    return db.query(PredictionModel).filter(PredictionModel.org_id == org_id).all()

def forecast_threats(db: Session, org_id: int) -> List[ThreatForecast]:
    models = list_models(db, org_id)
    if not models:
        models = [create_model(db, org_id, "Breach Likelihood v1")]
    forecasts = []
    for model in models:
        # Mock prediction based on alert volume
        alert_count = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).count()
        prob = min(0.95, alert_count * 0.02 + 0.3)
        f = ThreatForecast(org_id=org_id, model_id=model.id, forecast_type="breach", predicted_probability=prob, predicted_timeframe="7d", contributing_factors=["high alert volume","priv esc patterns"], confidence=0.78, status="active")
        db.add(f)
        forecasts.append(f)
    db.commit()
    for fc in forecasts:
        db.refresh(fc)
    return forecasts

def list_forecasts(db: Session, org_id: int) -> List[ThreatForecast]:
    return db.query(ThreatForecast).filter(ThreatForecast.org_id == org_id).order_by(ThreatForecast.created_at.desc()).limit(20).all()

def serialize_model(m: PredictionModel) -> Dict[str, Any]:
    return {"id": m.id, "name": m.name, "model_type": m.model_type, "features": m.features_json, "accuracy": m.accuracy, "status": m.status}

def serialize_forecast(f: ThreatForecast) -> Dict[str, Any]:
    return {"id": f.id, "model_id": f.model_id, "forecast_type": f.forecast_type, "predicted_probability": f.predicted_probability, "predicted_timeframe": f.predicted_timeframe, "contributing_factors": f.contributing_factors, "confidence": f.confidence, "created_at": f.created_at.isoformat() if f.created_at else None}
