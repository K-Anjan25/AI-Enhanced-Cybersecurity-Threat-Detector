"""Phase 84: SOC TV Wall service."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.soc_tv import SOCWallConfig, SOCWallMetric
from app.models import SecurityAlert, Case


def _now():
    return datetime.now(timezone.utc)


def create_wall_config(db: Session, org_id: int, name: str, widgets: List[Dict[str, Any]], is_default: bool = False, created_by_user_id: int = None) -> SOCWallConfig:
    if is_default:
        # Unset other defaults
        db.query(SOCWallConfig).filter(SOCWallConfig.org_id == org_id, SOCWallConfig.is_default == True).update({SOCWallConfig.is_default: False})
    config = SOCWallConfig(org_id=org_id, name=name, widgets_json=widgets, is_default=is_default, created_by_user_id=created_by_user_id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def list_wall_configs(db: Session, org_id: int) -> List[SOCWallConfig]:
    return db.query(SOCWallConfig).filter(SOCWallConfig.org_id == org_id, SOCWallConfig.is_active == True).order_by(SOCWallConfig.is_default.desc()).all()


def seed_default_wall(db: Session, org_id: int) -> SOCWallConfig:
    existing = db.query(SOCWallConfig).filter(SOCWallConfig.org_id == org_id, SOCWallConfig.is_default == True).first()
    if existing:
        return existing
    widgets = [
        {"type": "alert_feed", "position": {"x": 0, "y": 0, "w": 6, "h": 4}, "config": {"limit": 20, "severity_filter": "HIGH,CRITICAL"}},
        {"type": "open_cases", "position": {"x": 6, "y": 0, "w": 3, "h": 2}, "config": {}},
        {"type": "risk_metrics", "position": {"x": 9, "y": 0, "w": 3, "h": 2}, "config": {}},
        {"type": "attack_heatmap", "position": {"x": 0, "y": 4, "w": 6, "h": 4}, "config": {}},
        {"type": "agent_status", "position": {"x": 6, "y": 2, "w": 6, "h": 2}, "config": {}},
        {"type": "world_map", "position": {"x": 6, "y": 4, "w": 6, "h": 4}, "config": {}},
    ]
    return create_wall_config(db, org_id, "Default SOC Wall", widgets, is_default=True)


def get_live_metrics(db: Session, org_id: int) -> Dict[str, Any]:
    """Get live metrics for TV wall - real-time."""
    now = _now()
    last_hour = now - timedelta(hours=1)
    last_24h = now - timedelta(hours=24)

    total_alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).count()
    alerts_last_hour = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id, SecurityAlert.created_at >= last_hour).count()
    alerts_last_24h = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id, SecurityAlert.created_at >= last_24h).count()
    open_cases = db.query(Case).filter(Case.org_id == org_id, Case.status != "closed").count()
    critical_alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id, SecurityAlert.severity == "CRITICAL").count()

    # Top sources
    top_sources = db.query(SecurityAlert.source, func.count(SecurityAlert.id).label("cnt")).filter(SecurityAlert.org_id == org_id).group_by(SecurityAlert.source).order_by(func.count(SecurityAlert.id).desc()).limit(5).all()

    # Severity breakdown
    severity_breakdown = {}
    for sev in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        cnt = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id, SecurityAlert.severity == sev).count()
        severity_breakdown[sev] = cnt

    # Recent alerts for feed
    recent_alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).order_by(SecurityAlert.created_at.desc()).limit(10).all()

    metrics = {
        "total_alerts": total_alerts,
        "alerts_last_hour": alerts_last_hour,
        "alerts_last_24h": alerts_last_24h,
        "open_cases": open_cases,
        "critical_alerts": critical_alerts,
        "alerts_per_minute": round(alerts_last_hour / 60, 2) if alerts_last_hour else 0,
        "top_sources": [{"source": s[0], "count": s[1]} for s in top_sources if s[0]],
        "severity_breakdown": severity_breakdown,
        "recent_alerts": [{"id": a.id, "severity": a.severity, "source": a.source, "message": (a.message or "")[:100], "created_at": a.created_at.isoformat() if a.created_at else None} for a in recent_alerts],
        "timestamp": now.isoformat(),
    }

    # Persist some metrics for history
    try:
        for name, value in [("alerts_per_minute", metrics["alerts_per_minute"]), ("open_cases", open_cases), ("critical_alerts", critical_alerts)]:
            m = SOCWallMetric(org_id=org_id, metric_name=name, metric_value=float(value))
            db.add(m)
        db.commit()
    except Exception:
        db.rollback()

    return metrics


def serialize_config(c: SOCWallConfig) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "widgets": c.widgets_json, "is_default": c.is_default, "is_active": c.is_active, "created_at": c.created_at.isoformat() if c.created_at else None}


def serialize_metric(m: SOCWallMetric) -> Dict[str, Any]:
    return {"id": m.id, "metric_name": m.metric_name, "metric_value": m.metric_value, "recorded_at": m.recorded_at.isoformat() if m.recorded_at else None}
