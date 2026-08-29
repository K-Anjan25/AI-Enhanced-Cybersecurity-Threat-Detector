"""Phase 106: AI Governance & Trust - model cards, bias, explainability."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class AIModelCard(Base):
    __tablename__ = "ai_model_cards"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    model_name = Column(String(300), nullable=False)
    model_version = Column(String(50), default="1.0")
    purpose = Column(Text, nullable=True)
    training_data_json = Column(JSON, default=dict)
    limitations = Column(Text, nullable=True)
    ethical_considerations = Column(Text, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class BiasAudit(Base):
    __tablename__ = "bias_audits"
    id = Column(Integer, primary_key=True, index=True)
    model_card_id = Column(Integer, ForeignKey("ai_model_cards.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    audit_type = Column(String(50), default="fairness")  # fairness, drift, performance
    bias_score = Column(Float, default=0.0)
    findings_json = Column(JSON, default=dict)
    mitigations = Column(JSON, default=list)
    status = Column(String(20), default="completed")
    created_at = Column(DateTime(timezone=True), default=_now)

class ExplainabilityLog(Base):
    __tablename__ = "explainability_logs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    model_name = Column(String(200), nullable=False)
    decision_id = Column(String(200), nullable=True)
    shap_values_json = Column(JSON, default=dict)
    lime_explanation_json = Column(JSON, default=dict)
    natural_language_explanation = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
