"""Phase 100: NOCTRA OS service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.noctra_os import NOCTRA_OS_Config, NOCTRA_OS_Metric, NOCTRA_OS_Log
from app.models import SecurityAlert, Case

def _now():
    return datetime.now(timezone.utc)

def get_or_create_config(db: Session, org_id: int) -> NOCTRA_OS_Config:
    cfg = db.query(NOCTRA_OS_Config).filter(NOCTRA_OS_Config.org_id == org_id, NOCTRA_OS_Config.is_active == True).first()
    if cfg:
        return cfg
    modules = [f"P{i}" for i in range(49, 91)]  # P49-90
    cfg = NOCTRA_OS_Config(org_id=org_id, name="NOCTRA OS Default", autonomy_level="supervised", modules_json=modules, policies_json={"auto_triage": True, "auto_contain": False, "auto_remediate": False, "auto_approve_low": False}, is_active=True)
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg

def list_configs(db: Session, org_id: int) -> List[NOCTRA_OS_Config]:
    return db.query(NOCTRA_OS_Config).filter(NOCTRA_OS_Config.org_id == org_id).all()

def update_autonomy(db: Session, org_id: int, level: str) -> NOCTRA_OS_Config:
    cfg = get_or_create_config(db, org_id)
    if level not in ("manual", "supervised", "autonomous", "fully_autonomous"):
        raise ValueError("Invalid autonomy level")
    cfg.autonomy_level = level
    db.commit()
    db.refresh(cfg)
    # Log
    log = NOCTRA_OS_Log(org_id=org_id, log_type="decision", title=f"Autonomy level changed to {level}", description=f"Changed from previous to {level}", decision_json={"autonomy_level": level, "changed_at": _now().isoformat()})
    db.add(log)
    db.commit()
    return cfg

# Median minutes a human analyst spends triaging one alert by hand. Used only
# to express saved effort in hours; the underlying count is real.
_MINUTES_PER_MANUAL_TRIAGE = 20


def get_os_metrics(db: Session, org_id: int) -> Dict[str, Any]:
    """Operating metrics, every one counted from real rows.

    Anything we cannot measure (uptime, for instance, which lives in the
    platform's monitoring rather than this database) is omitted rather than
    asserted — a made-up 99.9% is a promise the product cannot keep.
    """
    total_alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).count()
    open_cases = db.query(Case).filter(Case.org_id == org_id, Case.status != "closed").count()
    closed_cases = db.query(Case).filter(Case.org_id == org_id, Case.status == "closed").count()

    analyst_cases = db.query(Case).filter(Case.org_id == org_id, Case.kind == "analyst")
    total_analyst = analyst_cases.count()
    decided = analyst_cases.filter(Case.decision.in_(("approved", "declined", "reverted"))).count()
    approved = analyst_cases.filter(Case.decision == "approved").count()

    cfg = get_or_create_config(db, org_id)

    metrics: Dict[str, Any] = {
        "total_alerts": total_alerts,
        "open_cases": open_cases,
        "closed_cases": closed_cases,
        # Share of alerts NOCTRA turned into a reasoned case on its own.
        "auto_triage_rate": round((total_analyst / total_alerts) * 100.0, 1) if total_alerts else 0.0,
        # Of the cases it proposed, how many a human agreed with. This is the
        # trust metric: it is what justifies raising the autonomy level.
        "recommendation_accept_rate": round((approved / decided) * 100.0, 1) if decided else 0.0,
        "cases_awaiting_decision": total_analyst - decided,
        "analyst_hours_saved": round((total_analyst * _MINUTES_PER_MANUAL_TRIAGE) / 60.0, 1),
        "autonomy_level": cfg.autonomy_level,
        "modules_enabled": len(cfg.modules_json or []),
    }

    for name, value in metrics.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            db.add(NOCTRA_OS_Metric(org_id=org_id, metric_name=name, metric_value=float(value)))
    db.commit()

    return metrics

def list_logs(db: Session, org_id: int, limit: int = 50) -> List[NOCTRA_OS_Log]:
    return db.query(NOCTRA_OS_Log).filter(NOCTRA_OS_Log.org_id == org_id).order_by(NOCTRA_OS_Log.created_at.desc()).limit(limit).all()

def serialize_config(c: NOCTRA_OS_Config) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "autonomy_level": c.autonomy_level, "modules": c.modules_json, "policies": c.policies_json, "is_active": c.is_active, "created_at": c.created_at.isoformat() if c.created_at else None}

def serialize_log(l: NOCTRA_OS_Log) -> Dict[str, Any]:
    return {"id": l.id, "log_type": l.log_type, "title": l.title, "description": l.description, "decision": l.decision_json, "created_at": l.created_at.isoformat() if l.created_at else None}
