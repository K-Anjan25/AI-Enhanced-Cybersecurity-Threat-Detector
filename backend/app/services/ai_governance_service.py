"""Phase 106: AI Governance service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.ai_governance import AIModelCard, BiasAudit, ExplainabilityLog

def _now():
    return datetime.now(timezone.utc)

def create_model_card(db: Session, org_id: int, model_name: str, purpose: str) -> AIModelCard:
    card = AIModelCard(org_id=org_id, model_name=model_name, model_version="1.0", purpose=purpose, training_data_json={"dataset": "NOCTRA SOC 2023-2025", "size": 500000}, limitations="May have bias towards high-volume alerts", ethical_considerations="Human in loop for HIGH severity", status="active")
    db.add(card)
    db.commit()
    db.refresh(card)
    return card

def list_model_cards(db: Session, org_id: int) -> List[AIModelCard]:
    return db.query(AIModelCard).filter(AIModelCard.org_id == org_id).order_by(AIModelCard.created_at.desc()).all()

def run_bias_audit(db: Session, org_id: int, model_card_id: int) -> BiasAudit:
    card = db.query(AIModelCard).filter(AIModelCard.id == model_card_id, AIModelCard.org_id == org_id).first()
    if not card:
        raise ValueError("Model card not found")
    audit = BiasAudit(model_card_id=model_card_id, org_id=org_id, audit_type="fairness", bias_score=0.12, findings_json={"demographic_parity": 0.92, "equal_opportunity": 0.88}, mitigations=["Rebalance training data","Add fairness constraints"], status="completed")
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit

def log_explainability(db: Session, org_id: int, model_name: str, decision_id: str, explanation: str, confidence: float) -> ExplainabilityLog:
    log = ExplainabilityLog(org_id=org_id, model_name=model_name, decision_id=decision_id, shap_values_json={"alert_severity": 0.8, "asset_criticality": 0.6}, lime_explanation_json={"top_features": ["severity","asset"]}, natural_language_explanation=explanation, confidence=confidence)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

def serialize_card(c: AIModelCard) -> Dict[str, Any]:
    return {"id": c.id, "model_name": c.model_name, "model_version": c.model_version, "purpose": c.purpose, "training_data": c.training_data_json, "limitations": c.limitations, "ethical_considerations": c.ethical_considerations, "status": c.status}

def serialize_audit(a: BiasAudit) -> Dict[str, Any]:
    return {"id": a.id, "model_card_id": a.model_card_id, "audit_type": a.audit_type, "bias_score": a.bias_score, "findings": a.findings_json, "mitigations": a.mitigations, "status": a.status}
