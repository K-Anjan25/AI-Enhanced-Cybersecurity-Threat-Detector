"""Phase 116: Neural SOC Co-Pilot - BCI prep, cognitive load."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class NeuralProfile(Base):
    __tablename__ = "neural_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    profile_name = Column(String(300), nullable=False)
    cognitive_preferences_json = Column(JSON, default=dict)  # {learning_style, decision_style}
    baseline_metrics_json = Column(JSON, default=dict)  # baseline cognitive load
    bci_device = Column(String(100), nullable=True)  # none, emotiv, neuralink_mock
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class CoPilotSession(Base):
    __tablename__ = "copilot_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    session_name = Column(String(300), nullable=False)
    intent = Column(String(500), nullable=True)  # what user wants to do
    suggestions_json = Column(JSON, default=list)  # AI suggestions
    accepted_suggestions = Column(Integer, default=0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class CognitiveMetric(Base):
    __tablename__ = "cognitive_metrics"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("copilot_sessions.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    metric_type = Column(String(50), default="cognitive_load")  # cognitive_load, focus, fatigue
    value = Column(Float, default=0.0)
    context_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
