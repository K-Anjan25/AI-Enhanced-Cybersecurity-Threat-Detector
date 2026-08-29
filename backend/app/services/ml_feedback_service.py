"""Phase 55: ML feedback loop + drift detection."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.ml_feedback import MLFeedback, MLModelVersion, MLDriftLog
from app.models import SecurityAlert

_LOGGER = logging.getLogger(__name__)


def submit_feedback(
    db: Session,
    org_id: int,
    user_id: int,
    feedback_type: str,
    alert_id: int = None,
    case_id: int = None,
    original_severity: str = None,
    corrected_severity: str = None,
    notes: str = None,
) -> MLFeedback:
    if feedback_type not in ("true_positive", "false_positive", "benign", "malicious", "corrected_severity"):
        raise ValueError(f"Invalid feedback_type {feedback_type}")

    fb = MLFeedback(
        org_id=org_id,
        user_id=user_id,
        alert_id=alert_id,
        case_id=case_id,
        feedback_type=feedback_type,
        original_severity=original_severity,
        corrected_severity=corrected_severity,
        notes=notes,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)

    # Check drift
    try:
        check_drift(db, org_id=org_id)
    except Exception:
        pass

    return fb


def list_feedback(db: Session, org_id: int, limit: int = 100) -> List[MLFeedback]:
    return db.query(MLFeedback).filter(MLFeedback.org_id == org_id).order_by(MLFeedback.created_at.desc()).limit(limit).all()


def get_feedback_stats(db: Session, org_id: int) -> Dict[str, Any]:
    total = db.query(MLFeedback).filter(MLFeedback.org_id == org_id).count()
    tp = db.query(MLFeedback).filter(MLFeedback.org_id == org_id, MLFeedback.feedback_type == "true_positive").count()
    fp = db.query(MLFeedback).filter(MLFeedback.org_id == org_id, MLFeedback.feedback_type == "false_positive").count()
    benign = db.query(MLFeedback).filter(MLFeedback.org_id == org_id, MLFeedback.feedback_type == "benign").count()

    # Calculate precision from feedback
    precision = tp / (tp + fp) if (tp + fp) > 0 else None

    return {
        "total": total,
        "true_positive": tp,
        "false_positive": fp,
        "benign": benign,
        "precision_from_feedback": precision,
        "feedback_needed_for_retrain": max(0, 100 - total),  # need 100 feedbacks for retrain
    }


def check_drift(db: Session, org_id: int) -> Optional[MLDriftLog]:
    """Simple drift detection: compare recent alert severity distribution vs historical."""
    # Get last 100 alerts severity counts
    recent = (
        db.query(SecurityAlert.severity, func.count(SecurityAlert.id))
        .filter(SecurityAlert.org_id == org_id)
        .group_by(SecurityAlert.severity)
        .all()
    )
    if not recent:
        return None

    # Simple heuristic: if CRITICAL ratio > 30%, flag drift
    total = sum(c for _, c in recent)
    critical = next((c for sev, c in recent if sev == "CRITICAL"), 0)
    ratio = critical / total if total > 0 else 0

    drift_score = ratio
    if drift_score > 0.3:
        log = MLDriftLog(
            org_id=org_id,
            model_name="severity_distribution",
            drift_score=drift_score,
            drift_type="data_drift",
            details={"critical_ratio": ratio, "total": total, "recent_distribution": {sev: cnt for sev, cnt in recent}},
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    return None


def list_model_versions(db: Session, org_id: int = None) -> List[MLModelVersion]:
    q = db.query(MLModelVersion).order_by(MLModelVersion.created_at.desc())
    if org_id is not None:
        q = q.filter(MLModelVersion.org_id == org_id)
    return q.all()


def create_model_version(
    db: Session,
    model_name: str,
    version: str,
    metrics: Dict[str, Any] = None,
    org_id: int = None,
    training_data_count: int = None,
    feedback_count: int = None,
) -> MLModelVersion:
    mv = MLModelVersion(
        org_id=org_id,
        model_name=model_name,
        version=version,
        metrics=metrics or {},
        training_data_count=training_data_count,
        feedback_count=feedback_count,
        is_active=True,
    )
    db.add(mv)
    db.commit()
    db.refresh(mv)
    return mv


def serialize_feedback(fb: MLFeedback) -> Dict[str, Any]:
    return {
        "id": fb.id,
        "org_id": fb.org_id,
        "alert_id": fb.alert_id,
        "case_id": fb.case_id,
        "user_id": fb.user_id,
        "feedback_type": fb.feedback_type,
        "original_severity": fb.original_severity,
        "corrected_severity": fb.corrected_severity,
        "notes": fb.notes,
        "created_at": fb.created_at.isoformat() if fb.created_at else None,
    }
