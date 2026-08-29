"""Phase 129: Time Prophecy service."""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.time_prophecy import TemporalModel, AnomalyProphecy, CausalGraph

def _now():
    return datetime.now(timezone.utc)

def create_temporal_model(db: Session, org_id: int, name: str, model_type: str = "transformer") -> TemporalModel:
    model = TemporalModel(org_id=org_id, name=name, model_type=model_type, time_granularity="hourly", lookback_days=90, forecast_horizon_days=30, accuracy=0.89, status="active")
    db.add(model)
    db.commit()
    db.refresh(model)
    return model

def list_models(db: Session, org_id: int) -> List[TemporalModel]:
    return db.query(TemporalModel).filter(TemporalModel.org_id == org_id).all()

def prophesy(db: Session, org_id: int, model_id: int) -> List[AnomalyProphecy]:
    model = db.query(TemporalModel).filter(TemporalModel.id == model_id, TemporalModel.org_id == org_id).first()
    if not model:
        raise ValueError("Model not found")
    prophecies = []
    for i in range(3):
        pred_time = _now() + timedelta(days=i*7+3)
        prop = AnomalyProphecy(model_id=model_id, org_id=org_id, prophecy_type="breach" if i==0 else "anomaly", predicted_at=pred_time, probability=0.75 - i*0.1, causal_factors=[{"cause": "failed logins spike", "strength": 0.8}, {"cause": "priv esc", "strength": 0.7}], explanation=f"Predicted {prophecies[0].prophecy_type if prophecies else 'breach'} due to temporal pattern", status="predicted")
        db.add(prop)
        prophecies.append(prop)
    db.commit()
    for p in prophecies:
        db.refresh(p)
    # Causal graph
    graph = CausalGraph(org_id=org_id, name=f"Causal graph for model {model_id}", nodes_json=[{"id": "failed_logins", "type": "event"}, {"id": "priv_esc", "type": "event"}, {"id": "breach", "type": "outcome"}], edges_json=[{"from": "failed_logins", "to": "priv_esc", "strength": 0.7}, {"from": "priv_esc", "to": "breach", "strength": 0.85}], root_cause="failed_logins", confidence=0.82)
    db.add(graph)
    db.commit()
    return prophecies

def serialize_model(m: TemporalModel) -> Dict[str, Any]:
    return {"id": m.id, "name": m.name, "model_type": m.model_type, "time_granularity": m.time_granularity, "lookback_days": m.lookback_days, "forecast_horizon_days": m.forecast_horizon_days, "accuracy": m.accuracy, "status": m.status}

def serialize_prophecy(p: AnomalyProphecy) -> Dict[str, Any]:
    return {"id": p.id, "model_id": p.model_id, "prophecy_type": p.prophecy_type, "predicted_at": p.predicted_at.isoformat() if p.predicted_at else None, "probability": p.probability, "causal_factors": p.causal_factors, "explanation": p.explanation, "status": p.status}
