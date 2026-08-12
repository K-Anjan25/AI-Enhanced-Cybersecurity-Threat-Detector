from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import AuditLog


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def severity_to_score(severity: str) -> float:
    """Map a human severity label to a numeric 0..1 score."""
    severity_map = {
        "CRITICAL": 0.95,
        "HIGH": 0.75,
        "MEDIUM": 0.5,
        "LOW": 0.2,
    }
    return severity_map.get(severity.upper(), 0.1)


def score_to_severity(score: float, model_type: str = "network") -> str:
    """Convert an anomaly score to a severity label.

    For IsolationForest (network), score >= 0 is normal and more negative
    means more anomalous. Log models return a 0..1 probability where higher
    is more suspicious.
    """
    score = float(score or 0.0)
    if model_type == "network":
        if score >= 0:
            return "LOW"
        if score > -0.15:
            return "MEDIUM"
        if score > -0.4:
            return "HIGH"
        return "CRITICAL"
    # Log / probability model
    if score < 0.4:
        return "LOW"
    if score < 0.7:
        return "MEDIUM"
    if score < 0.9:
        return "HIGH"
    return "CRITICAL"


def serialize_alert(alert: Any) -> dict:
    """Serialize a SecurityAlert ORM row into an API-friendly dict."""
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "source_ip": alert.source_ip,
        "source": alert.source,
        "severity": alert.severity,
        "score": alert.score,
        "message": alert.message,
        "mitre_tactic": getattr(alert, "mitre_tactic", None),
        "mitre_technique_id": getattr(alert, "mitre_technique_id", None),
        "mitre_technique": getattr(alert, "mitre_technique", None),
        "threat_intel": getattr(alert, "threat_intel", None),
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


def paginate(db: Session, query, page: int = 1, limit: int = 20):
    """Return (items, total) for a paginated query."""
    page = max(1, page)
    limit = min(max(1, limit), 100)
    total = query.count()
    items = query.offset((page - 1) * limit).limit(limit).all()
    return items, total


def create_audit_log(
    db: Session,
    action: str,
    actor: Optional[str] = None,
    resource: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Record an administrative action in the audit trail."""
    entry = AuditLog(
        action=action,
        actor=actor,
        resource=resource,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def require_field(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{key}' is required",
        )
    return value
