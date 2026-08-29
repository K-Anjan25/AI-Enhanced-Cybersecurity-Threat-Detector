"""Phase 55: ML feedback loop + drift detection."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, JSON, Float, Text
from app.core.database import Base


class MLFeedback(Base):
    __tablename__ = "ml_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    alert_id = Column(Integer, ForeignKey("security_alerts.id", ondelete="SET NULL"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Feedback: true_positive, false_positive, benign, etc
    feedback_type = Column(String(50), nullable=False)
    original_severity = Column(String(20), nullable=True)
    corrected_severity = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class MLModelVersion(Base):
    __tablename__ = "ml_model_versions"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)

    model_name = Column(String(100), nullable=False)  # network, log, email, dns
    version = Column(String(50), nullable=False)
    metrics = Column(JSON, nullable=True)  # accuracy, precision, recall, f1
    training_data_count = Column(Integer, nullable=True)
    feedback_count = Column(Integer, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class MLDriftLog(Base):
    __tablename__ = "ml_drift_logs"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)

    model_name = Column(String(100), nullable=False)
    drift_score = Column(Float, nullable=False)
    drift_type = Column(String(50), nullable=False)  # data_drift, concept_drift
    details = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
